"""Worker que executa os turnos do chat.

O turno NÃO roda na requisição HTTP: o Portal não tem streaming em lugar
nenhum e prender worker por 30s derruba a Revy Loja inteira. A rota grava e
volta; este worker executa; a tela faz polling.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app import provisioning
from app.config import (
    revy_loja_copiloto_enabled,
    revy_loja_entitlements_enabled,
    settings,
)
from app.loja.copiloto.conversas import (
    atualizar_progresso,
    concluir_turno,
    falhar_turno,
    listar_turnos,
)
from app.loja.copiloto.historico import selecionar_historico
from app.loja.copiloto.runner import executar_turno
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.copiloto.tools import RecursosTools
from app.loja.types import Module
from app.meta_ads_spend_job import env_flag, env_float, env_int
from app.models import CopilotoTurno, Usuario

logger = logging.getLogger("portal.copiloto.turnos")


def _copiloto_permitido(db: Session, loja_slug: str) -> bool:
    """Mesmo gate por loja do motor de sinais (`copiloto_sinais_job._copiloto_permitido`).

    Um turno pode ficar `pendente` na fila por um tempo (lote, intervalo do
    worker); nesse intervalo a loja pode ser desativada ou perder o
    entitlement do módulo Copiloto. Sem recheckar aqui, o worker processaria
    — e cobraria custo real de LLM por — uma loja que já não tem mais
    acesso. Isto NÃO é vazamento entre lojas (o turno já pertence à própria
    loja, e a rota de leitura tem seu próprio gate), é integridade de
    autorização/custo: só quem ainda tem acesso pode gerar a despesa.
    """
    modulo = Module.COPILOTO.value if revy_loja_entitlements_enabled() else None
    return provisioning.allows_processing(db, loja_slug, modulo)


def _historico(
    db: Session, turno: CopilotoTurno, orcamento_tokens: int | None = None
) -> list[tuple[str, str]]:
    orcamento = (
        settings.copiloto_historico_tokens
        if orcamento_tokens is None
        else orcamento_tokens
    )
    pares: list[tuple[str, str]] = []
    for anterior in listar_turnos(db, turno.loja_slug, turno.conversa_id):
        if anterior.id == turno.id:
            break
        if anterior.estado == "pronto" and anterior.resposta:
            pares.append((anterior.pergunta, anterior.resposta))
    return selecionar_historico(pares, orcamento)


def _papel_do_ator(db: Session, turno: CopilotoTurno) -> str:
    usuario = db.get(Usuario, turno.usuario_id)
    return (usuario.papel if usuario else "dono") or "dono"


def processar_turno(
    db: Session,
    turno: CopilotoTurno,
    *,
    llm,
    estoque,
    chatbot,
    agora: datetime | None = None,
) -> None:
    """Executa um turno e grava o resultado. Nunca levanta para o chamador.

    Cancelar roda numa sessão HTTP separada desta (a rota flipa `estado` na
    sessão do request; este worker tem a sua própria). `db.refresh` força a
    releitura do valor comitado por aquela outra sessão — sem isso, os
    `atualizar_progresso`/`concluir_turno`/`falhar_turno` abaixo escreveriam
    por cima de um cancelamento (blind write): na pior hipótese,
    ressuscitando o turno como `pronto` depois que a tela já parou de fazer
    polling em `cancelado`.
    """
    ref = agora or datetime.now(timezone.utc)

    db.refresh(turno)
    if turno.estado == "cancelado":
        logger.info(
            "copiloto_turno turno=%s já cancelado antes de iniciar — não chama "
            "o provedor",
            turno.id,
        )
        return

    atualizar_progresso(db, turno, estado="executando", passos=[])

    ctx = CopilotoContexto(
        loja_slug=turno.loja_slug,
        papel=_papel_do_ator(db, turno),
        ator_email="",
        hoje=ref.date(),
    )
    recursos = RecursosTools(
        db=db, estoque=estoque, chatbot=chatbot, ctx=ctx, agora=ref
    )

    def _on_passo(passos: list[dict]) -> None:
        atualizar_progresso(db, turno, passos=passos)

    try:
        resultado = executar_turno(
            pergunta=turno.pergunta,
            historico=_historico(db, turno),
            llm=llm,
            recursos=recursos,
            deadline_segundos=env_float(
                "PORTAL_COPILOTO_TURNO_DEADLINE_SECONDS", 45.0
            ),
            on_passo=_on_passo,
            agora=ref,
        )
    except Exception as exc:  # rede de segurança: turno nunca fica pendurado
        logger.warning("copiloto_turno erro inesperado tipo=%s", type(exc).__name__)
        db.refresh(turno)
        if turno.estado == "cancelado":
            logger.info(
                "copiloto_turno turno=%s cancelado durante a execução — mantém "
                "estado apesar do erro interno",
                turno.id,
            )
            return
        falhar_turno(db, turno, erro_code="interno")
        return

    db.refresh(turno)
    if turno.estado == "cancelado":
        logger.info(
            "copiloto_turno turno=%s cancelado durante a execução — descarta o "
            "resultado do provedor (in=%s out=%s) e mantém o estado",
            turno.id,
            resultado.tokens_entrada,
            resultado.tokens_saida,
        )
        return

    if resultado.estado == "pronto" and resultado.texto:
        concluir_turno(
            db,
            turno,
            resposta=resultado.texto,
            passos=resultado.passos_dict(),
            tokens_entrada=resultado.tokens_entrada,
            tokens_saida=resultado.tokens_saida,
            custo_estimado=str(resultado.custo),
        )
        return

    atualizar_progresso(db, turno, passos=resultado.passos_dict())
    turno.texto_parcial = resultado.texto
    falhar_turno(
        db,
        turno,
        erro_code=resultado.erro_code or "sem_resposta",
        tokens_entrada=resultado.tokens_entrada,
        tokens_saida=resultado.tokens_saida,
    )


def _llm_padrao():
    from app.clients.deepseek import DeepSeekClient

    return DeepSeekClient(
        settings.copiloto_llm_url,
        settings.copiloto_llm_key,
        settings.copiloto_llm_model,
        timeout=settings.copiloto_llm_timeout,
        retries=settings.copiloto_llm_retries,
    )


class CopilotoTurnosWorker:
    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        interval_seconds: float | None = None,
        enabled: bool | None = None,
        lote: int | None = None,
        llm_factory: Callable[[], object] | None = None,
        estoque_factory: Callable[[], object] | None = None,
        chatbot_factory: Callable[[], object] | None = None,
    ):
        self.db_factory = db_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else env_float("PORTAL_COPILOTO_TURNOS_INTERVAL_SECONDS", 1.0)
        )
        self.lote = int(
            lote if lote is not None else env_int("PORTAL_COPILOTO_TURNOS_LOTE", 3)
        )
        self.ttl_executando = float(
            env_float("PORTAL_COPILOTO_TURNO_TTL_SECONDS", 180.0)
        )
        # Duas chaves diferentes, de propósito:
        #  - `enabled` é o interruptor do PROCESSO (roda worker aqui?), snapshot no boot;
        #  - a flag de produto `REVY_LOJA_COPILOTO_ENABLED` é lida A CADA CICLO, igual às
        #    rotas. Snapshotá-la aqui criaria o descasamento "rota abre, worker dorme" —
        #    toda pergunta ficaria `pendente` para sempre.
        # `enabled=` explícito é decisão já tomada pelo chamador (testes): vale sozinho.
        self._gate_flag = enabled is None
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = env_flag("PORTAL_COPILOTO_TURNOS_ENABLED", True)
        self._llm_factory = llm_factory or _llm_padrao
        self._estoque_factory = estoque_factory
        self._chatbot_factory = chatbot_factory
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

        estoque = EstoqueClient(
            settings.estoque_url, settings.estoque_token, settings.request_timeout
        )
        chatbot = ChatbotClient(
            settings.chatbot_url, settings.chatbot_token, settings.request_timeout
        )
        return estoque, chatbot

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="copiloto-turnos", daemon=True
        )
        self._thread.start()
        logger.info("copiloto_turnos_job: iniciado interval=%ss", self.interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def expirar_orfaos(self, db: Session) -> int:
        """Fecha turno preso em `executando` — o processo morreu no meio dele.

        Sem isto, todo ``fly deploy`` no meio de uma pergunta deixa um turno
        `executando` para sempre: a tela faz polling eterno e, pior, a guarda de
        runaway da rota (que conta `pendente|executando` por usuário) trava o dono
        num 429 permanente depois de dois deploys infelizes. O deadline do runner
        é in-process — não sobrevive à morte do processo. Este é o único lugar que
        varre isso.
        """
        limite = datetime.now(timezone.utc) - timedelta(seconds=self.ttl_executando)
        orfaos = (
            db.query(CopilotoTurno)
            .filter(
                CopilotoTurno.estado == "executando",
                CopilotoTurno.iniciado_em.isnot(None),
                CopilotoTurno.iniciado_em < limite,
            )
            .all()
        )
        for turno in orfaos:
            falhar_turno(db, turno, erro_code="interrompido")
        if orfaos:
            logger.warning("copiloto_turnos_job: %s turno(s) órfão(s)", len(orfaos))
        return len(orfaos)

    def _ligado(self) -> bool:
        if not self.enabled:
            return False
        return revy_loja_copiloto_enabled() if self._gate_flag else True

    def run_once(self) -> dict:
        if not self._ligado():
            payload = {"ok": False, "processados": 0}
            self.last_result = payload
            return payload
        db = self.db_factory()
        processados = 0
        try:
            self.expirar_orfaos(db)
            pendentes = (
                db.query(CopilotoTurno)
                .filter(CopilotoTurno.estado == "pendente")
                .order_by(CopilotoTurno.criado_em.asc())
                .limit(max(1, self.lote))
                .all()
            )
            permitidos = []
            for turno in pendentes:
                if _copiloto_permitido(db, turno.loja_slug):
                    permitidos.append(turno)
                else:
                    # Falha terminal SEM chamar o provedor: turno enfileirado
                    # antes de a loja perder o entitlement (ou ser
                    # desativada) não pode gerar custo de LLM, e não pode
                    # ficar `pendente` para sempre — isso recriaria o mesmo
                    # problema de órfão/429 permanente que expirar_orfaos()
                    # existe para evitar.
                    logger.warning(
                        "copiloto_turnos_job: turno=%s loja=%s sem acesso ao "
                        "Copiloto — falhando sem chamar o provedor",
                        turno.id,
                        turno.loja_slug,
                    )
                    falhar_turno(db, turno, erro_code="sem_acesso")
            if permitidos:
                estoque, chatbot = self._clients()
                llm = self._llm_factory()
                for turno in permitidos:
                    processar_turno(
                        db, turno, llm=llm, estoque=estoque, chatbot=chatbot
                    )
                    processados += 1
            payload = {"ok": True, "processados": processados}
        except Exception as exc:
            db.rollback()
            payload = {
                "ok": False,
                "erro": type(exc).__name__,
                "processados": processados,
            }
        finally:
            db.close()
        self.last_result = payload
        return payload

    def _run(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: CopilotoTurnosWorker | None = None


def get_worker() -> CopilotoTurnosWorker | None:
    return _worker


def start_worker(db_factory: Callable[[], Session]) -> CopilotoTurnosWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = CopilotoTurnosWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
