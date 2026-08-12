"""Job em background: apaga turno/conversa do Copiloto mais velhos que o
prazo de retenção (``settings.copiloto_retencao_dias`` /
``PORTAL_COPILOTO_RETENCAO_DIAS``, default 30 dias).

Molde estrutural: mesma família de ``copiloto_turnos_job.py`` e
``copiloto_sinais_job.py`` — thread daemon + ``Event`` + ``run_once``
síncrono, mesma dupla de gates (``enabled`` snapshot de processo no boot +
``REVY_LOJA_COPILOTO_ENABLED`` de produto relido a cada ciclo).

O QUE APAGA, E O QUE NÃO APAGA (decisão central deste job)
------------------------------------------------------------
Apaga ``copiloto_turno`` e, quando fica sem nenhum turno restante,
``copiloto_conversa`` — isto é, o CONTEÚDO da conversa. É exatamente o que o
prazo de retenção promete descartar.

NÃO apaga ``copiloto_acao`` nem ``loja_operacao_auditoria``, de propósito.
Essas duas tabelas são registro de ALTERAÇÃO COMERCIAL — quem mudou o preço
de qual veículo, de quanto para quanto, e quando — não são conversa. É
registro financeiro/auditoria, e sai (se um dia sair) por outra política, ou
por nenhuma; nunca pela mesma vassourada da retenção de chat. Apagar
auditoria junto com conversa destruiria a única resposta a "por que esse
preço mudou?".

``CopilotoAcao.turno_id`` não tem chave estrangeira — nem no model
(``app/models.py``), nem na migration que criou a tabela (``0021``). É só uma
referência textual solta, sem ``ON DELETE`` de banco para reagir. Quando o
turno de origem é purgado, a linha de ação FICA, com ``turno_id`` apontando
para um turno que não existe mais: preservar a linha de auditoria vale mais
do que preservar a referência íntegra.

Como apaga
----------
- Sempre escopado por loja: nunca um DELETE que dependa só da data.
- Em lotes, com um teto total de turnos removidos por execução
  (``PORTAL_COPILOTO_PURGE_LOTE``) — para não segurar transação longa nem
  travar tabela. Se uma loja tem mais turnos elegíveis do que o teto, o
  resto fica para o próximo ciclo.
- Turno ``pendente`` ou ``executando`` nunca é removido por idade, por mais
  velho que esteja: se está velho e travado, é sintoma de outro problema
  (ver ``copiloto_turnos_job.expirar_orfaos``), e apagar esconderia a
  evidência.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.config import revy_loja_copiloto_enabled, settings
from app.meta_ads_spend_job import env_flag, env_float, env_int
from app.models import CopilotoConversa, CopilotoTurno

logger = logging.getLogger(__name__)

# Turno "em voo" nunca é removido por idade, mesmo velho: ver docstring do
# módulo e o mesmo conceito em copiloto_turnos_job.expirar_orfaos.
ESTADOS_EM_VOO = ("pendente", "executando")


def lojas_com_turnos_elegiveis(db: Session, corte: datetime) -> list[str]:
    """Lojas com pelo menos um turno concluído mais velho que ``corte``."""
    linhas = (
        db.query(CopilotoTurno.loja_slug)
        .filter(
            CopilotoTurno.estado.notin_(ESTADOS_EM_VOO),
            CopilotoTurno.criado_em < corte,
        )
        .distinct()
        .all()
    )
    return sorted({linha[0] for linha in linhas})


def purgar_loja(
    db: Session, loja_slug: str, *, corte: datetime, lote: int
) -> dict[str, int]:
    """Apaga até ``lote`` turnos elegíveis desta loja e as conversas órfãs.

    Sempre filtra por ``loja_slug`` — nunca um DELETE que dependa só da
    data. Uma conversa só é removida quando não sobra nenhum turno dela
    (``atualizada_em < corte`` é defesa extra contra apagar uma conversa
    recém-criada cujo primeiro turno ainda não commitou; na prática as duas
    linhas nascem na mesma transação em ``criar_turno``, então isto nunca
    deveria disparar sozinho).
    """
    ids_turnos = [
        linha[0]
        for linha in db.query(CopilotoTurno.id)
        .filter(
            CopilotoTurno.loja_slug == loja_slug,
            CopilotoTurno.estado.notin_(ESTADOS_EM_VOO),
            CopilotoTurno.criado_em < corte,
        )
        .order_by(CopilotoTurno.criado_em.asc())
        .limit(max(1, lote))
        .all()
    ]

    turnos_removidos = 0
    if ids_turnos:
        turnos_removidos = (
            db.query(CopilotoTurno)
            .filter(CopilotoTurno.id.in_(ids_turnos))
            .delete(synchronize_session=False)
        )

    turnos_restantes = (
        db.query(CopilotoTurno.id)
        .filter(CopilotoTurno.conversa_id == CopilotoConversa.id)
        .exists()
    )
    conversas_removidas = (
        db.query(CopilotoConversa)
        .filter(
            CopilotoConversa.loja_slug == loja_slug,
            CopilotoConversa.atualizada_em < corte,
            ~turnos_restantes,
        )
        .delete(synchronize_session=False)
    )

    db.commit()
    return {"turnos": turnos_removidos, "conversas": conversas_removidas}


class CopilotoPurgeWorker:
    """Thread daemon que aplica a retenção do Copiloto em intervalo fixo."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        enabled: bool | None = None,
        lote: int | None = None,
        retencao_dias: int | None = None,
        agora: Callable[[], datetime] | None = None,
    ):
        self.db_factory = db_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else env_float("PORTAL_COPILOTO_PURGE_INTERVAL_SECONDS", 21600.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else env_float("PORTAL_COPILOTO_PURGE_INITIAL_DELAY_SECONDS", 300.0)
        )
        # Teto de turnos removidos POR EXECUÇÃO (soma entre todas as lojas):
        # transação curta, sem travar tabela. Sobra fica para o próximo ciclo.
        self.lote = int(
            lote if lote is not None else env_int("PORTAL_COPILOTO_PURGE_LOTE", 500)
        )
        self._retencao_dias = retencao_dias
        # Duas chaves diferentes, de propósito (mesmo raciocínio dos outros
        # workers do Copiloto):
        #  - `enabled` é o interruptor do PROCESSO (roda worker aqui?), snapshot no boot;
        #  - a flag de produto `REVY_LOJA_COPILOTO_ENABLED` é lida A CADA CICLO. Se o
        #    produto está desligado, o job não roda — retenção de um produto fora do
        #    ar não é urgência.
        # `enabled=` explícito é decisão já tomada pelo chamador (testes): vale sozinho.
        self._gate_flag = enabled is None
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = env_flag("PORTAL_COPILOTO_PURGE_ENABLED", True)
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    def _corte(self) -> datetime:
        dias = (
            self._retencao_dias
            if self._retencao_dias is not None
            else settings.copiloto_retencao_dias
        )
        return self._agora() - timedelta(days=max(1, dias))

    def start(self) -> None:
        if not self.enabled:
            logger.info("copiloto_purge_job: desligado (PORTAL_COPILOTO_PURGE_ENABLED)")
            return
        if self.interval <= 0 or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="copiloto-purge", daemon=True
        )
        self._thread.start()
        logger.info(
            "copiloto_purge_job: iniciado interval=%ss lote=%s", self.interval, self.lote
        )

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
            payload = {"ok": False, "motivo": "desligado", "turnos": 0, "conversas": 0}
            self.last_result = payload
            return payload

        corte = self._corte()
        db = self.db_factory()
        turnos_total = 0
        conversas_total = 0
        lojas_processadas = 0
        try:
            for loja_slug in lojas_com_turnos_elegiveis(db, corte):
                orcamento = self.lote - turnos_total
                if orcamento <= 0:
                    break
                resultado = purgar_loja(db, loja_slug, corte=corte, lote=orcamento)
                turnos_total += resultado["turnos"]
                conversas_total += resultado["conversas"]
                lojas_processadas += 1
                if resultado["turnos"] or resultado["conversas"]:
                    logger.info(
                        "copiloto_purge_job loja=%s turnos=%s conversas=%s",
                        loja_slug,
                        resultado["turnos"],
                        resultado["conversas"],
                    )
            payload = {
                "ok": True,
                "turnos": turnos_total,
                "conversas": conversas_total,
                "lojas": lojas_processadas,
            }
        except Exception as exc:
            db.rollback()
            payload = {
                "ok": False,
                "erro": type(exc).__name__,
                "turnos": turnos_total,
                "conversas": conversas_total,
            }
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


_worker: CopilotoPurgeWorker | None = None


def get_worker() -> CopilotoPurgeWorker | None:
    return _worker


def start_worker(db_factory: Callable[[], Session]) -> CopilotoPurgeWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = CopilotoPurgeWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
