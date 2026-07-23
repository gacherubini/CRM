"""Worker de retry automático do outbox Meta CAPI."""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from sqlalchemy.orm import Session

from app.meta_capi import processar_outbox_automatico

logger = logging.getLogger(__name__)


def _flag(nome: str, default: bool) -> bool:
    raw = (os.getenv(nome) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _numero(nome: str, default: float) -> float:
    try:
        return float(os.getenv(nome, str(default)))
    except (TypeError, ValueError):
        return default


class MetaCapiRetryWorker:
    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        enabled: bool | None = None,
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        max_tentativas: int | None = None,
        backoff_base_seconds: float | None = None,
    ):
        self.db_factory = db_factory
        self.enabled = (
            enabled
            if enabled is not None
            else _flag("PORTAL_CAPI_RETRY_ENABLED", True)
        )
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else _numero("PORTAL_CAPI_RETRY_INTERVAL_SECONDS", 60)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else _numero("PORTAL_CAPI_RETRY_INITIAL_DELAY_SECONDS", 30)
        )
        self.max_tentativas = int(
            max_tentativas
            if max_tentativas is not None
            else _numero("PORTAL_CAPI_RETRY_MAX_ATTEMPTS", 8)
        )
        self.backoff_base = float(
            backoff_base_seconds
            if backoff_base_seconds is not None
            else _numero("PORTAL_CAPI_RETRY_BACKOFF_BASE_SECONDS", 60)
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, int] | None = None

    def start(self) -> None:
        if not self.enabled or self.interval <= 0:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="meta-capi-retry",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict[str, int]:
        try:
            self.last_result = processar_outbox_automatico(
                self.db_factory,
                max_tentativas=max(1, self.max_tentativas),
                backoff_base_seconds=max(1, self.backoff_base),
            )
        except Exception as exc:
            logger.warning("meta_capi_job: falha tipo=%s", type(exc).__name__)
            self.last_result = {
                "encontrados": 0,
                "processados": 0,
                "entregues": 0,
                "falharam": 1,
                "aguardando_backoff": 0,
                "esgotados": 0,
            }
        return self.last_result

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: MetaCapiRetryWorker | None = None


def start_worker(db_factory: Callable[[], Session]) -> MetaCapiRetryWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = MetaCapiRetryWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
