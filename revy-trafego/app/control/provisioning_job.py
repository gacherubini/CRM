"""Worker de entrega da outbox de provisionamento.

Ligado só com ``REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1``.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.control.provisioning_outbox import multi_destination_poster, process_pending

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class ProvisioningDeliveryWorker:
    """Thread daemon que processa a outbox de provisionamento."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        poster: Callable[[str, dict[str, Any]], None] | None = None,
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        enabled: bool | None = None,
        batch_limit: int = 20,
    ) -> None:
        self.db_factory = db_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else _env_float("REVY_CONTROL_PROVISIONING_INTERVAL_SECONDS", 30.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else _env_float(
                "REVY_CONTROL_PROVISIONING_INITIAL_DELAY_SECONDS", 15.0
            )
        )
        self.enabled = (
            enabled
            if enabled is not None
            else settings.revy_control_provisioning_delivery_enabled
        )
        self.batch_limit = batch_limit
        self.poster = poster or multi_destination_poster(
            chatbot_url=settings.chatbot_url,
            chatbot_token_for_slug=settings.chatbot_token_para,
            estoque_url=settings.estoque_url,
            estoque_token_for_slug=settings.estoque_token_para,
            portal_url=settings.portal_url,
            portal_service_token=settings.portal_service_token,
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info(
                "provisioning_job: desligado "
                "(REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED)"
            )
            return
        if self.interval <= 0:
            logger.info("provisioning_job: intervalo inválido, não inicia")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="control-provisioning-delivery",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "provisioning_job: iniciado interval=%ss delay=%ss",
            self.interval,
            self.initial_delay,
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict[str, Any]:
        try:
            with self.db_factory() as db:
                delivered = process_pending(
                    db, self.poster, limit=self.batch_limit
                )
                db.commit()
            payload = {"ok": True, "delivered": delivered}
            self.last_result = payload
            if delivered:
                logger.info("provisioning_job: delivered=%s", delivered)
            return payload
        except Exception as exc:
            logger.warning(
                "provisioning_job: falha tipo=%s", type(exc).__name__
            )
            payload = {"ok": False, "erro": type(exc).__name__}
            self.last_result = payload
            return payload

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: ProvisioningDeliveryWorker | None = None


def get_worker() -> ProvisioningDeliveryWorker | None:
    return _worker


def start_worker(
    db_factory: Callable[[], Session],
) -> ProvisioningDeliveryWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = ProvisioningDeliveryWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker(timeout: float = 5.0) -> None:
    global _worker
    if _worker is not None:
        _worker.stop(timeout=timeout)
        _worker = None
