"""Worker de retry do outbox Portal -> Revy Trafego."""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from sqlalchemy.orm import Session

from app.revy_trafego_outbox import processar_pendentes

logger = logging.getLogger(__name__)


def _numero(nome: str, default: float) -> float:
    try:
        return float(os.getenv(nome, str(default)))
    except (TypeError, ValueError):
        return default


class RevyTrafegoOutboxWorker:
    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        enabled: bool,
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
    ):
        self.db_factory = db_factory
        self.enabled = enabled
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else _numero("PORTAL_REVY_TRAFEGO_RETRY_INTERVAL_SECONDS", 60)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else _numero("PORTAL_REVY_TRAFEGO_RETRY_INITIAL_DELAY_SECONDS", 15)
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled or self.interval <= 0:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="revy-trafego-outbox-retry",
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
            return processar_pendentes(self.db_factory)
        except Exception as exc:
            logger.warning(
                "revy_trafego_outbox_job: falha tipo=%s", type(exc).__name__
            )
            return {"encontrados": 0, "entregues": 0, "falharam": 1}

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: RevyTrafegoOutboxWorker | None = None


def start_worker(
    db_factory: Callable[[], Session], *, enabled: bool
) -> RevyTrafegoOutboxWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = RevyTrafegoOutboxWorker(db_factory=db_factory, enabled=enabled)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
