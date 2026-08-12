"""Motor proativo do Copiloto: roda as regras por loja e grava os sinais.

Molde estrutural: ``app/meta_ads_spend_job.py`` (thread daemon + Event +
``run_once`` síncrono). Nada de LLM aqui — é regra determinística, e é isso que
mantém o alerta funcionando com o provedor de IA fora do ar.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from decimal import Decimal
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
from app.loja.copiloto.fipe import STATUS_OK, consultar_fipe_do_veiculo
from app.loja.copiloto.periodo import janela_do_periodo
from app.loja.copiloto.sinais import (
    SinalCandidato,
    regra_atribuicao_baixa,
    regra_cadastro_incompleto,
    regra_estoque_parado,
    regra_lead_sem_resposta,
    regra_margem_incompleta,
    regra_meta_em_risco,
    regra_preco_fora_da_faixa,
)
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.estoque_overview import montar_estoque_overview
from app.loja.types import Module
from app.meta_ads_spend_job import env_flag, env_float, env_int
from app.models import LojaOperacionalProjecao

logger = logging.getLogger(__name__)

DIAS_ESTOQUE_PARADO = 60
HORAS_LEAD_SEM_RESPOSTA = 4

# Regra 7 (preço fora da faixa da FIPE): os três limiares abaixo são
# CALIBRAGEM DE MERCADO, não de engenharia — o dono quer ajustar com o
# estoque real na mão. Estes defaults são só o ponto de partida (nunca
# tratar como recomendação); como vêm de env, calibrar não exige deploy.
FIPE_FOLGA_ALTA_DEFAULT = 0.30  # 30% acima da FIPE já destoa sozinho
FIPE_FOLGA_BASE_DEFAULT = 0.15  # 15% acima só soma sinal se também parado
FIPE_DIAS_PARADO_DEFAULT = 60  # mesmo piso de "encalhado" da regra 1
# Teto de consultas à FIPE por ciclo — API comunitária sem SLA; consultar o
# estoque inteiro por rodada é abuso e queima rate limit para todo mundo.
FIPE_POR_CICLO_DEFAULT = 10


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


# Formato documentado da resposta real da FIPE (client.valor()["Valor"]):
# "R$ 27.500,00" — moeda BR, "." separador de milhar, "," separador decimal.
# Qualquer coisa fora deste formato é rejeitada, não "consertada": um regex
# de limpeza que só remove caracteres indesejados (em vez de VALIDAR o
# formato inteiro) é exatamente o tipo de parser que transforma dado externo
# estranho em número plausível — a classe de defeito que esta fase inteira
# existe para evitar.
_RE_VALOR_FIPE = re.compile(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}$")


def _parse_valor_fipe(bruto: str | None) -> Decimal | None:
    """``"R$ 27.500,00"`` -> ``Decimal("27500.00")``. Qualquer coisa que não
    seja esse formato positivo bem-formado vira ``None`` — nunca um valor
    aproximado. Em particular, sinal negativo é REJEITADO, não descartado:
    ``"-27.500,00"`` não vira ``27500.00`` — vira ``None``, porque um "Valor"
    negativo não é um preço malformado que dá para consertar, é sinal de que
    aquela resposta da FIPE não deve ser usada."""
    if not bruto:
        return None
    texto = str(bruto).strip()
    if not _RE_VALOR_FIPE.fullmatch(texto):
        return None
    limpo = texto.split("R$", 1)[1].strip().replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except (ArithmeticError, ValueError):
        return None
    return valor if valor > 0 else None


def _veiculos_com_fipe(
    estoque,
    fipe,
    ctx: CopilotoContexto,
    ref: datetime,
    *,
    teto: int,
) -> list[tuple]:
    """Até ``teto`` pares ``(veiculo, valor_fipe)`` para a regra 7.

    Prioriza quem está parado há mais tempo (``estoque_parado`` já devolve
    ordenado por ``-dias_parado``) e se apoia no cache de 6h de marca/modelo
    da Fase 3 — a FIPE é API comunitária sem SLA, consultar o estoque inteiro
    por ciclo é abuso. ``dias_min=0`` para não deixar de fora um veículo
    recém-cadastrado com preço muito acima (caso 1 não exige estar parado).

    Só entram pares com match CONFIRMADO (``status == ok``): ambíguo, não
    encontrado ou indisponível ficam de fora silenciosamente — a Fase 3 é
    categórica que a FIPE nunca adivinha, e um sinal proativo é lugar pior
    para adivinhar do que uma resposta de chat, porque ninguém perguntou
    nada.

    ``fipe is None`` sai cedo, sem tocar no estoque: o chamador
    (``avaliar_loja``) já filtra isso antes de chamar esta função, mas o
    guard fica também aqui — defesa que não depende de quem chama, e que
    evita gastar um ``estoque_parado()`` (mais um ``estoque.obter()`` por
    item) só para falhar no primeiro ``fipe.marcas()``. O ``except``
    por-veículo abaixo continua como rede para falhas genuinamente
    inesperadas, não como o mecanismo principal para este caso previsível.
    """
    if fipe is None:
        return []
    candidatos = estoque_parado(estoque, ctx, dias_min=0, limite=max(1, teto), agora=ref)
    pares: list[tuple] = []
    for item in candidatos.itens:
        try:
            resultado = consultar_fipe_do_veiculo(fipe, estoque, ctx, veiculo_id=item.id)
        except Exception:
            # Mesma lógica das outras degradações deste arquivo: pula o
            # veículo (não inventa dado), mas loga porque isto não é uma das
            # falhas esperadas do cliente FIPE (essas já viram ResultadoFipe
            # com status "indisponivel" dentro de consultar_fipe_do_veiculo).
            logger.warning(
                "copiloto_sinais_job: falha inesperada em consultar_fipe_do_veiculo veiculo=%s",
                item.id,
                exc_info=True,
            )
            continue
        if resultado.status != STATUS_OK:
            continue
        valor = _parse_valor_fipe(resultado.valor)
        if valor is None:
            continue
        pares.append((item, valor))
    return pares


def avaliar_loja(
    db: Session,
    loja_slug: str,
    *,
    estoque,
    chatbot,
    fipe=None,
    agora: datetime | None = None,
) -> list[SinalCandidato]:
    """Roda as 7 regras da loja e devolve os candidatos desta passada.

    ``fipe`` é opcional: sem client (ex.: testes das outras 6 regras), a
    regra 7 é simplesmente pulada — mesma lógica de degradação das demais
    dependências externas deste arquivo (estoque/chatbot indisponíveis
    tampouco derrubam o ciclo).
    """
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

    if fipe is not None:
        try:
            pares_fipe = _veiculos_com_fipe(
                estoque,
                fipe,
                ctx,
                ref,
                teto=env_int("PORTAL_COPILOTO_FIPE_POR_CICLO", FIPE_POR_CICLO_DEFAULT),
            )
        except EstoqueIndisponivel:
            pares_fipe = []
        except Exception:
            logger.warning(
                "copiloto_sinais_job: falha inesperada montando pares FIPE loja=%s",
                loja_slug,
                exc_info=True,
            )
            pares_fipe = []
        candidatos.extend(
            regra_preco_fora_da_faixa(
                pares_fipe,
                folga_alta=env_float(
                    "PORTAL_COPILOTO_FIPE_FOLGA_ALTA", FIPE_FOLGA_ALTA_DEFAULT
                ),
                folga_base=env_float(
                    "PORTAL_COPILOTO_FIPE_FOLGA_BASE", FIPE_FOLGA_BASE_DEFAULT
                ),
                dias_parado_min=env_int(
                    "PORTAL_COPILOTO_FIPE_DIAS_PARADO", FIPE_DIAS_PARADO_DEFAULT
                ),
            )
        )

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
        fipe_factory: Callable[[], object] | None = None,
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
        self._fipe_factory = fipe_factory
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    def _clients(self):
        if self._estoque_factory and self._chatbot_factory:
            fipe = self._fipe_factory() if self._fipe_factory else None
            return self._estoque_factory(), self._chatbot_factory(), fipe
        # Construção direta (mesmos um-liners de app.main.get_estoque_client /
        # get_chatbot_client), sem importar app.main: o worker não pode depender
        # do módulo que o inicia, senão o boot vira um ciclo.
        from app.clients.chatbot import ChatbotClient
        from app.clients.estoque import EstoqueClient
        from app.clients.fipe import FipeClient
        from app.config import settings

        estoque = EstoqueClient(
            settings.estoque_url, settings.estoque_token, settings.request_timeout
        )
        chatbot = ChatbotClient(
            settings.chatbot_url, settings.chatbot_token, settings.request_timeout
        )
        fipe = FipeClient(
            settings.copiloto_fipe_url, timeout=settings.copiloto_fipe_timeout
        )
        return estoque, chatbot, fipe

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
            estoque, chatbot, fipe = self._clients()
            for loja_slug in lojas_ativas(db):
                try:
                    candidatos = avaliar_loja(
                        db,
                        loja_slug,
                        estoque=estoque,
                        chatbot=chatbot,
                        fipe=fipe,
                        agora=ref,
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
