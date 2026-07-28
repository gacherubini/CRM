"""Job em background: sincroniza gastos Meta de todas as lojas habilitadas.

Liga no lifespan do Portal. Desligado por padrão em testes
(``PORTAL_META_SPEND_SYNC_ENABLED=0``).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from sqlalchemy.orm import Session

from app.meta_ads_spend import sincronizar_todas_lojas

logger = logging.getLogger(__name__)


def env_flag(nome: str, default: bool = False) -> bool:
    raw = (os.getenv(nome) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_float(nome: str, default: float) -> float:
    try:
        return float(os.getenv(nome, str(default)))
    except (TypeError, ValueError):
        return default


def env_int(nome: str, default: int) -> int:
    try:
        return int(os.getenv(nome, str(default)))
    except (TypeError, ValueError):
        return default


class MetaSpendSyncWorker:
    """Thread daemon que roda ``sincronizar_todas_lojas`` em intervalo fixo."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        janela_dias: int | None = None,
        enabled: bool | None = None,
    ):
        self.db_factory = db_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else env_float("PORTAL_META_SPEND_SYNC_INTERVAL_SECONDS", 86400.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else env_float("PORTAL_META_SPEND_SYNC_INITIAL_DELAY_SECONDS", 120.0)
        )
        self.janela_dias = int(
            janela_dias
            if janela_dias is not None
            else env_int("PORTAL_META_SPEND_SYNC_JANELA_DIAS", 3)
        )
        self.enabled = (
            enabled
            if enabled is not None
            else env_flag("PORTAL_META_SPEND_SYNC_ENABLED", True)
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info("meta_spend_job: desligado (PORTAL_META_SPEND_SYNC_ENABLED)")
            return
        if self.interval <= 0:
            logger.info("meta_spend_job: intervalo inválido, não inicia")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="meta-spend-sync",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "meta_spend_job: iniciado interval=%ss delay=%ss janela=%sd",
            self.interval,
            self.initial_delay,
            self.janela_dias,
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict:
        """Execução síncrona (endpoint interno / testes)."""
        try:
            result = sincronizar_todas_lojas(
                self.db_factory,
                janela_dias=self.janela_dias,
            )
            payload = {
                "ok": True,
                "lojas": result.lojas,
                "status_ok": result.ok,
                "status_partial": result.partial,
                "status_erro": result.erro,
                "imported": result.imported,
                "updated": result.updated,
                "resumo": result.resumo(),
            }
            self.last_result = payload
            logger.info("meta_spend_job: %s", result.resumo())
            return payload
        except Exception as exc:
            logger.warning(
                "meta_spend_job: falha tipo=%s",
                type(exc).__name__,
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


_worker: MetaSpendSyncWorker | None = None


def get_worker() -> MetaSpendSyncWorker | None:
    return _worker


def start_worker(db_factory: Callable[[], Session]) -> MetaSpendSyncWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = MetaSpendSyncWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
