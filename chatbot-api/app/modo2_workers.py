"""Ciclo de vida dos workers do Modo 2 (rodízio e follow-up).

Os dois têm timer próprio por decisão da spec (§5.3: "worker no chatbot-api,
não Wait do n8n"). Sem subir aqui, `run_once` só roda em teste — e foi
exatamente o que aconteceu: o prazo de 10 min nunca disparava e o cutucão de
silêncio nunca acontecia, com a suíte inteira verde.

Mesmo formato do ``notificacoes_outbox_job``: thread daemon, ``start``/``stop``
idempotentes, intervalo por env.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from app import config
from app.cloud_canal import loja_id_do_phone_number_id

logger = logging.getLogger("chatbot.modo2_workers")

_workers: dict[str, "_Periodico"] = {}


def _numero(nome: str, default: float) -> float:
    try:
        return float(os.getenv(nome, "") or default)
    except ValueError:
        return default


class _Periodico:
    """Roda ``run_once(db)`` em intervalo fixo, numa sessão por ciclo."""

    def __init__(
        self,
        nome: str,
        alvo: Callable[[Any], Any],
        *,
        db_factory: Callable[[], Any],
        interval_seconds: float,
    ) -> None:
        self.nome = nome
        self.alvo = alvo
        self.db_factory = db_factory
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.interval <= 0:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"modo2-{self.nome}", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            db = self.db_factory()
            try:
                self.alvo(db)
            except Exception:  # noqa: BLE001
                # Um ciclo que falha não pode derrubar a thread: o próximo
                # tenta de novo. Sem isto, um erro transitório de rede mataria
                # o rodízio até o restart da VM.
                logger.exception("ciclo do worker %s falhou", self.nome)
            finally:
                fechar = getattr(db, "close", None)
                if callable(fechar):
                    fechar()
            self._stop.wait(self.interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None


def start_workers(
    db_factory: Callable[[], Any], *, enabled: bool
) -> dict[str, "_Periodico"]:
    """Sobe rodízio e follow-up. Devolve o que subiu (vazio = nada subiu).

    Respeita a flag de rollout: com ``MODO2_ENABLED`` desligada nem thread
    nasce, que é o que "flag default OFF" tem que significar de verdade.
    """
    global _workers
    if _workers:
        return _workers
    if not enabled or not config.MODO2_ENABLED:
        return {}

    from app.cloud_retry import CloudRetryWorker
    from app.followup_job import FollowupWorker
    from app.rodizio_job import RodizioWorker
    from app.whatsapp_outbound import outbound_para_loja

    rodizio = RodizioWorker()
    followup = FollowupWorker()
    cloud_retry = CloudRetryWorker()

    def _ciclo_rodizio(db: Any) -> None:
        # Sem outbound aqui, a reoferta vira só uma linha no banco: o worker
        # passa o lead ao vendedor 2 e o celular dele nunca toca (spec §5.3).
        rodizio.run_once(db, outbound=_OutboundPorLoja(db, outbound_para_loja))

    def _ciclo_cloud_retry(db: Any) -> None:
        cloud_retry.run_once(db)

    def _ciclo_followup(db: Any) -> None:
        # O follow-up precisa de um outbound e ele é por loja; o worker resolve
        # por conversa, então passa o resolvedor e não uma instância fixa.
        followup.run_once(db, outbound=_OutboundPorLoja(db, outbound_para_loja))

    _workers = {
        "rodizio": _Periodico(
            "rodizio",
            _ciclo_rodizio,
            db_factory=db_factory,
            # Metade do menor prazo (10 min) para a oferta não passar do ponto.
            interval_seconds=_numero("CHATBOT_MODO2_RODIZIO_INTERVAL_SECONDS", 300),
        ),
        "followup": _Periodico(
            "followup",
            _ciclo_followup,
            db_factory=db_factory,
            interval_seconds=_numero("CHATBOT_MODO2_FOLLOWUP_INTERVAL_SECONDS", 300),
        ),
        # A outra metade da §6.1: respondemos 200 na hora, então quem falhou
        # tem que ser retomado por aqui — senão "processar depois" nunca
        # acontece e o lead se perde com uma linha de log.
        "cloud_retry": _Periodico(
            "cloud_retry",
            _ciclo_cloud_retry,
            db_factory=db_factory,
            interval_seconds=_numero("CHATBOT_MODO2_RETRY_INTERVAL_SECONDS", 60),
        ),
    }
    for worker in _workers.values():
        worker.start()
    return _workers


def stop_workers() -> None:
    global _workers
    for worker in _workers.values():
        worker.stop()
    _workers = {}


class _OutboundPorLoja:
    """Adapta o resolvedor por loja à interface de envio que os workers usam.

    Rodízio e follow-up varrem lojas diferentes num ciclo só, então o outbound
    não pode ser fixado antes — é resolvido no envio.

    O ``instance`` que chega aqui é o ``phone_number_id`` do canal, **não** o id
    da loja. Sem traduzir um no outro, o resolvedor pergunta "a loja <pnid> é
    Modo 2?", ouve não e devolve o adapter do Modo 1 — que nem tem
    ``send_template_button``.
    """

    def __init__(self, db: Any, resolvedor: Callable[[Any, str], Any]) -> None:
        self._db = db
        self._resolvedor = resolvedor
        self._cache: dict[str, Any] = {}

    def _loja_de(self, instance: str) -> str:
        # Número não cadastrado cai no comportamento antigo (a chave crua), que
        # é o que o resolvedor sabe recusar sozinho.
        return loja_id_do_phone_number_id(self._db, instance) or instance

    def _para(self, instance: str) -> Any:
        if instance not in self._cache:
            self._cache[instance] = self._resolvedor(self._db, self._loja_de(instance))
        return self._cache[instance]

    def send_text(self, *, instance: str, number: str, text: str) -> Any:
        return self._para(instance).send_text(
            instance=instance, number=number, text=text
        )

    def send_template_button(self, *, instance: str, **kwargs: Any) -> Any:
        """Oferta com a janela de 24 h do vendedor fechada (``enviar_oferta``)."""
        return self._para(instance).send_template_button(instance=instance, **kwargs)

    def send_interactive_button(self, *, instance: str, **kwargs: Any) -> Any:
        """Oferta com a janela aberta — mesmo significado, de graça."""
        return self._para(instance).send_interactive_button(
            instance=instance, **kwargs
        )
