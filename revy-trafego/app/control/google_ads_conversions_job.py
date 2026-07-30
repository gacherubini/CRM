"""Worker de retry automático do outbox Google Ads conversions.

Liga no lifespan quando ``GOOGLE_CONVERSIONS_ENABLED`` (ou worker flag) está on.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.control.google_ads_conversions import (
    DEFAULT_MAX_ATTEMPTS,
    GoogleAdsConversionsControl,
)
from app.control.google_ads_http import build_google_ads_ports

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _numero(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _conversions_feature_enabled() -> bool:
    # Lê env em runtime (testes monkeypatcham; settings é frozen no import).
    return _flag(
        "GOOGLE_CONVERSIONS_ENABLED",
        bool(settings.google_conversions_enabled),
    )


def _worker_enabled_default() -> bool:
    """Explicit WORKER flag, else follow GOOGLE_CONVERSIONS_ENABLED."""
    raw = (os.getenv("GOOGLE_CONVERSIONS_WORKER_ENABLED") or "").strip()
    if raw:
        return raw.lower() in {"1", "true", "yes", "on"}
    return _conversions_feature_enabled()


class GoogleAdsConversionsWorker:
    """Thread daemon que processa a outbox de conversões Google Ads."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        enabled: bool | None = None,
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        max_attempts: int | None = None,
        batch_limit: int | None = None,
        control: GoogleAdsConversionsControl | None = None,
    ) -> None:
        self.db_factory = db_factory
        self.enabled = (
            enabled if enabled is not None else _worker_enabled_default()
        )
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else _numero("GOOGLE_CONVERSIONS_WORKER_INTERVAL_SECONDS", 60.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else _numero(
                "GOOGLE_CONVERSIONS_WORKER_INITIAL_DELAY_SECONDS", 30.0
            )
        )
        self.max_attempts = int(
            max_attempts
            if max_attempts is not None
            else _numero(
                "GOOGLE_CONVERSIONS_WORKER_MAX_ATTEMPTS",
                DEFAULT_MAX_ATTEMPTS,
            )
        )
        self.batch_limit = int(
            batch_limit
            if batch_limit is not None
            else _numero("GOOGLE_CONVERSIONS_WORKER_BATCH_LIMIT", 20)
        )
        self._control = control
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None

    def _build_control(self) -> GoogleAdsConversionsControl:
        if self._control is not None:
            return self._control
        ports = build_google_ads_ports(settings)
        return GoogleAdsConversionsControl(
            self.db_factory,
            data_manager_port=ports.data_manager_port,
            max_attempts=max(1, self.max_attempts),
        )

    def start(self) -> None:
        if not _conversions_feature_enabled():
            logger.info(
                "google_ads_conversions_job: skip "
                "(GOOGLE_CONVERSIONS_ENABLED off)"
            )
            return
        if not self.enabled:
            logger.info(
                "google_ads_conversions_job: desligado "
                "(GOOGLE_CONVERSIONS_WORKER_ENABLED)"
            )
            return
        if self.interval <= 0:
            logger.info(
                "google_ads_conversions_job: intervalo inválido, não inicia"
            )
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="google-ads-conversions-outbox",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "google_ads_conversions_job: iniciado interval=%ss delay=%ss",
            self.interval,
            self.initial_delay,
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict[str, Any]:
        """Execução síncrona (endpoint interno / testes)."""
        if not _conversions_feature_enabled():
            payload = {
                "ok": True,
                "skipped": True,
                "reason": "GOOGLE_CONVERSIONS_ENABLED_off",
                "sent": 0,
            }
            self.last_result = payload
            return payload
        try:
            control = self._build_control()
            sent = control.process_outbox_once(
                limit=max(1, self.batch_limit)
            )
            payload = {"ok": True, "sent": int(sent)}
            self.last_result = payload
            if sent:
                logger.info("google_ads_conversions_job: sent=%s", sent)
            return payload
        except Exception as exc:
            logger.warning(
                "google_ads_conversions_job: falha tipo=%s",
                type(exc).__name__,
            )
            payload = {"ok": False, "erro": type(exc).__name__, "sent": 0}
            self.last_result = payload
            return payload

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: GoogleAdsConversionsWorker | None = None


def get_worker() -> GoogleAdsConversionsWorker | None:
    return _worker


def start_worker(
    db_factory: Callable[[], Session],
) -> GoogleAdsConversionsWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = GoogleAdsConversionsWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker(timeout: float = 5.0) -> None:
    global _worker
    if _worker is not None:
        _worker.stop(timeout=timeout)
        _worker = None
