"""Motor proativo do Copiloto: roda as regras por loja e grava os sinais.

Molde estrutural: ``app/meta_ads_spend_job.py`` (thread daemon + Event +
``run_once`` síncrono). Nada de LLM aqui — é regra determinística, e é isso que
mantém o alerta funcionando com o provedor de IA fora do ar.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app import provisioning
from app.clients.chatbot import ChatbotIndisponivel
from app.clients.estoque import EstoqueIndisponivel
from app.config import revy_loja_copiloto_enabled, revy_loja_entitlements_enabled
from app.loja.copiloto.consultas_estoque import estoque_parado
from app.loja.copiloto.consultas_leads import leads_status
from app.loja.copiloto.consultas_origem import venda_origem_periodo
from app.loja.copiloto.consultas_vendas import vendas_resumo
from app.loja.copiloto.periodo import janela_do_periodo
from app.loja.copiloto.sinais import (
    SinalCandidato,
    regra_atribuicao_baixa,
    regra_cadastro_incompleto,
    regra_estoque_parado,
    regra_lead_sem_resposta,
    regra_margem_incompleta,
    regra_meta_em_risco,
)
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.estoque_overview import montar_estoque_overview
from app.loja.types import Module
from app.meta_ads_spend_job import env_flag, env_float
from app.models import LojaOperacionalProjecao

logger = logging.getLogger(__name__)

DIAS_ESTOQUE_PARADO = 60
HORAS_LEAD_SEM_RESPOSTA = 4


def _copiloto_permitido(db: Session, loja_slug: str) -> bool:
    """Gate duplo por loja: mesmo mecanismo usado pelas rotas (``allows_processing``).

    Com ``REVY_LOJA_ENTITLEMENTS_ENABLED`` desligado (default hoje, single-tenant),
    ``allows_processing`` recebe ``module=None`` e só confere a loja ativa — é o
    fail-open que preserva o comportamento atual. Ligado, exige o módulo Copiloto
    contratado e ativo (``LojaOperacionalProjecao`` do aggregate ``copiloto``), do
    jeito que ``check_module_access``/``resolve_entitlements`` já fazem nas rotas.
    """
    modulo = Module.COPILOTO.value if revy_loja_entitlements_enabled() else None
    return provisioning.allows_processing(db, loja_slug, modulo)


def lojas_ativas(db: Session) -> list[str]:
    linhas = (
        db.query(LojaOperacionalProjecao.loja_slug)
        .filter(
            LojaOperacionalProjecao.aggregate == "loja",
            LojaOperacionalProjecao.state == "ativa",
        )
        .all()
    )
    slugs = sorted({linha[0] for linha in linhas})
    return [slug for slug in slugs if _copiloto_permitido(db, slug)]


def avaliar_loja(
    db: Session,
    loja_slug: str,
    *,
    estoque,
    chatbot,
    agora: datetime | None = None,
) -> list[SinalCandidato]:
    """Roda as 6 regras da loja e devolve os candidatos desta passada."""
    ref = agora or datetime.now(timezone.utc)
    ctx = CopilotoContexto(
        loja_slug=loja_slug,
        papel="dono",  # motor roda no escopo da loja, não de uma pessoa
        ator_email="sistema@copiloto",
        hoje=ref.date(),
    )
    janela = janela_do_periodo(None, None)

    candidatos: list[SinalCandidato] = []

    parado = estoque_parado(
        estoque, ctx, dias_min=DIAS_ESTOQUE_PARADO, agora=ref, limite=50
    )
    candidatos.extend(regra_estoque_parado(parado))

    try:
        veiculos = estoque.listar()
    except EstoqueIndisponivel:
        veiculos = None
    except Exception:
        # Degrada igual ao offline conhecido (regra pulada, nunca inventa
        # dado), mas isto não é o sinal esperado — é bug real e tem que
        # aparecer no log.
        logger.warning(
            "copiloto_sinais_job: falha inesperada em estoque.listar loja=%s",
            loja_slug,
            exc_info=True,
        )
        veiculos = None
    if veiculos is not None:
        candidatos.extend(
            regra_cadastro_incompleto(montar_estoque_overview(veiculos, agora=ref))
        )

    vendas = vendas_resumo(db, ctx, inicio=None, fim=None)
    candidatos.extend(regra_margem_incompleta(vendas))

    from app.financeiro_calc import metas_view_periodo
    from decimal import Decimal

    metas = metas_view_periodo(
        db,
        loja_slug,
        janela.inicio,
        janela.fim,
        {
            "quantidade": Decimal(vendas.qtd_vendas),
            "faturamento": vendas.receita,
            "lucro_bruto": vendas.margem or Decimal("0"),
        },
        vendas.cobertura_margem.completa,
    )
    candidatos.extend(regra_meta_em_risco(metas, janela, hoje=ref.date()))

    origem = venda_origem_periodo(db, ctx, inicio=None, fim=None)
    candidatos.extend(regra_atribuicao_baixa(origem))

    from app.loja.sales_overview import build_sales_overview

    try:
        overview = build_sales_overview(
            db, loja_slug=loja_slug, papel="dono", chatbot=chatbot
        )
    except (EstoqueIndisponivel, ChatbotIndisponivel):
        overview = None
    except Exception:
        # Mesma lógica: degrada a regra (pulada), mas loga — build_sales_overview
        # já absorve as falhas esperadas internamente, então qualquer exceção
        # que escape daqui é inesperada por definição.
        logger.warning(
            "copiloto_sinais_job: falha inesperada em build_sales_overview loja=%s",
            loja_slug,
            exc_info=True,
        )
        overview = None
    if overview is not None:
        candidatos.extend(
            regra_lead_sem_resposta(
                leads_status(
                    overview,
                    chatbot,
                    ctx=ctx,
                    agora=ref,
                    horas_sem_resposta=HORAS_LEAD_SEM_RESPOSTA,
                )
            )
        )

    return candidatos


class CopilotoSinaisWorker:
    """Thread daemon que avalia as regras por loja em intervalo fixo."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        enabled: bool | None = None,
        estoque_factory: Callable[[], object] | None = None,
        chatbot_factory: Callable[[], object] | None = None,
        agora: Callable[[], datetime] | None = None,
    ):
        self.db_factory = db_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else env_float("PORTAL_COPILOTO_SINAIS_INTERVAL_SECONDS", 1800.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else env_float("PORTAL_COPILOTO_SINAIS_INITIAL_DELAY_SECONDS", 60.0)
        )
        # Duas chaves diferentes, de propósito:
        #  - `enabled` é o interruptor do PROCESSO (roda worker aqui?), snapshot no boot;
        #  - a flag de produto `REVY_LOJA_COPILOTO_ENABLED` é lida A CADA CICLO, igual às
        #    rotas. Snapshotá-la aqui criaria o descasamento "rota abre, worker dorme".
        # `enabled=` explícito é decisão já tomada pelo chamador (testes): vale sozinho.
        self._gate_flag = enabled is None
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = env_flag("PORTAL_COPILOTO_SINAIS_ENABLED", True)
        self._estoque_factory = estoque_factory
        self._chatbot_factory = chatbot_factory
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    def _clients(self):
        if self._estoque_factory and self._chatbot_factory:
            return self._estoque_factory(), self._chatbot_factory()
        # Construção direta (mesmos um-liners de app.main.get_estoque_client /
        # get_chatbot_client), sem importar app.main: o worker não pode depender
        # do módulo que o inicia, senão o boot vira um ciclo.
        from app.clients.chatbot import ChatbotClient
        from app.clients.estoque import EstoqueClient
        from app.config import settings

        estoque = EstoqueClient(
            settings.estoque_url, settings.estoque_token, settings.request_timeout
        )
        chatbot = ChatbotClient(
            settings.chatbot_url, settings.chatbot_token, settings.request_timeout
        )
        return estoque, chatbot

    def start(self) -> None:
        if not self.enabled:
            logger.info("copiloto_sinais_job: desligado")
            return
        if self.interval <= 0 or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="copiloto-sinais", daemon=True
        )
        self._thread.start()
        logger.info("copiloto_sinais_job: iniciado interval=%ss", self.interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def _ligado(self) -> bool:
        if not self.enabled:
            return False
        return revy_loja_copiloto_enabled() if self._gate_flag else True

    def run_once(self) -> dict:
        if not self._ligado():
            payload = {"ok": False, "motivo": "desligado", "lojas": 0, "erros": 0}
            self.last_result = payload
            return payload

        ref = self._agora()
        db = self.db_factory()
        lojas = 0
        erros = 0
        try:
            estoque, chatbot = self._clients()
            for loja_slug in lojas_ativas(db):
                try:
                    candidatos = avaliar_loja(
                        db, loja_slug, estoque=estoque, chatbot=chatbot, agora=ref
                    )
                    resultado = sincronizar_sinais(
                        db, loja_slug, candidatos, agora=ref
                    )
                    lojas += 1
                    logger.info(
                        "copiloto_sinais_job loja=%s %s", loja_slug, resultado.resumo()
                    )
                except Exception as exc:
                    # Uma loja quebrada não pode derrubar o ciclo das outras.
                    db.rollback()
                    erros += 1
                    logger.warning(
                        "copiloto_sinais_job: falha loja=%s tipo=%s",
                        loja_slug,
                        type(exc).__name__,
                    )
            payload = {"ok": True, "lojas": lojas, "erros": erros}
        except Exception as exc:
            payload = {"ok": False, "erro": type(exc).__name__, "lojas": lojas, "erros": erros}
        finally:
            db.close()
        self.last_result = payload
        return payload

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: CopilotoSinaisWorker | None = None


def get_worker() -> CopilotoSinaisWorker | None:
    return _worker


def start_worker(db_factory: Callable[[], Session]) -> CopilotoSinaisWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = CopilotoSinaisWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
