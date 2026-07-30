"""Worker de sincronização diária de métricas Google Ads.

Default off; no lifespan liga quando ``GOOGLE_ADS_SYNC_ENABLED`` (ou
``GOOGLE_ADS_METRICS_WORKER_ENABLED``) está on — padrão do meta spend.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.control.google_ads import CONNECTION_STATUS_CONNECTED
from app.control.google_ads_http import build_google_ads_ports
from app.control.google_ads_metrics import (
    GoogleAdsMetricsControl,
    GoogleAdsNoSelectedAccount,
    GoogleAdsNotConnected,
    SyncMetricsResult,
)
from app.control.stores import store_blocks_traffic_jobs
from app.models import GoogleAdsAccount, GoogleAdsConnection

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _numero(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def listar_lojas_para_metrics_sync(db: Session) -> list[str]:
    """Lojas com conexão ativa + conta selecionada, não suspensas."""
    rows = (
        db.query(GoogleAdsConnection.loja_id)
        .filter(
            GoogleAdsConnection.status == CONNECTION_STATUS_CONNECTED,
            GoogleAdsConnection.refresh_token_ciphertext.isnot(None),
        )
        .all()
    )
    loja_ids: list[str] = []
    for (loja_id,) in rows:
        if store_blocks_traffic_jobs(db, loja_id=loja_id):
            continue
        selected = (
            db.query(GoogleAdsAccount.id)
            .filter(
                GoogleAdsAccount.loja_id == loja_id,
                GoogleAdsAccount.selected.is_(True),
                GoogleAdsAccount.is_manager.is_(False),
            )
            .first()
        )
        if selected is None:
            # fallback: connection.customer_id preenchido
            conn = (
                db.query(GoogleAdsConnection.customer_id)
                .filter(GoogleAdsConnection.loja_id == loja_id)
                .first()
            )
            if not conn or not conn[0]:
                continue
        loja_ids.append(loja_id)
    return loja_ids


class GoogleAdsMetricsSyncWorker:
    """Thread daemon que sincroniza métricas de todas as lojas elegíveis."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        enabled: bool | None = None,
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        time_window_days: int | None = None,
        control: GoogleAdsMetricsControl | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self.db_factory = db_factory
        self.enabled = (
            enabled
            if enabled is not None
            else _flag("GOOGLE_ADS_METRICS_WORKER_ENABLED", False)
        )
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else _numero("GOOGLE_ADS_METRICS_WORKER_INTERVAL_SECONDS", 86400.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else _numero(
                "GOOGLE_ADS_METRICS_WORKER_INITIAL_DELAY_SECONDS", 120.0
            )
        )
        self.time_window_days = int(
            time_window_days
            if time_window_days is not None
            else _numero("GOOGLE_ADS_METRICS_WORKER_TIME_WINDOW_DAYS", 7)
        )
        self._control = control
        self._today = today or (lambda: date.today())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None

    def _build_control(self) -> GoogleAdsMetricsControl:
        if self._control is not None:
            return self._control
        ports = build_google_ads_ports(settings)
        return GoogleAdsMetricsControl(
            self.db_factory,
            read_port=ports.read_port,
        )

    def start(self) -> None:
        if not self.enabled:
            logger.info(
                "google_ads_metrics_job: desligado "
                "(GOOGLE_ADS_METRICS_WORKER_ENABLED)"
            )
            return
        if self.interval <= 0:
            logger.info(
                "google_ads_metrics_job: intervalo inválido, não inicia"
            )
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="google-ads-metrics-sync",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "google_ads_metrics_job: iniciado interval=%ss delay=%ss window=%sd",
            self.interval,
            self.initial_delay,
            self.time_window_days,
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict[str, Any]:
        """Execução síncrona (endpoint interno / testes)."""
        try:
            control = self._build_control()
            days = max(1, self.time_window_days)
            d_to = self._today()
            d_from = d_to - timedelta(days=days - 1)
            date_from = d_from.isoformat()
            date_to = d_to.isoformat()

            db = self.db_factory()
            try:
                loja_ids = listar_lojas_para_metrics_sync(db)
            finally:
                db.close()

            ok = 0
            skipped = 0
            erro = 0
            rows_upserted = 0
            details: list[dict[str, Any]] = []

            for loja_id in loja_ids:
                try:
                    # re-check suspension per loja (race-safe)
                    with self.db_factory() as check_db:
                        if store_blocks_traffic_jobs(check_db, loja_id=loja_id):
                            skipped += 1
                            details.append(
                                {
                                    "loja_id": loja_id,
                                    "status": "skipped",
                                    "reason": "store_blocked",
                                }
                            )
                            continue
                    result: SyncMetricsResult = control.sync_metrics_for_store_id(
                        loja_id,
                        date_from=date_from,
                        date_to=date_to,
                    )
                    ok += 1
                    rows_upserted += int(result.rows_upserted)
                    details.append(
                        {
                            "loja_id": loja_id,
                            "status": "ok",
                            "customer_id": result.customer_id,
                            "rows_upserted": result.rows_upserted,
                        }
                    )
                except (GoogleAdsNotConnected, GoogleAdsNoSelectedAccount) as exc:
                    skipped += 1
                    details.append(
                        {
                            "loja_id": loja_id,
                            "status": "skipped",
                            "reason": type(exc).__name__,
                        }
                    )
                except Exception as exc:
                    erro += 1
                    logger.warning(
                        "google_ads_metrics_job: loja=%s falha tipo=%s",
                        loja_id,
                        type(exc).__name__,
                    )
                    details.append(
                        {
                            "loja_id": loja_id,
                            "status": "erro",
                            "reason": type(exc).__name__,
                        }
                    )

            payload = {
                "ok": True,
                "lojas": len(loja_ids),
                "status_ok": ok,
                "status_skipped": skipped,
                "status_erro": erro,
                "rows_upserted": rows_upserted,
                "date_from": date_from,
                "date_to": date_to,
                "details": details,
            }
            self.last_result = payload
            logger.info(
                "google_ads_metrics_job: lojas=%s ok=%s skip=%s erro=%s rows=%s",
                len(loja_ids),
                ok,
                skipped,
                erro,
                rows_upserted,
            )
            return payload
        except Exception as exc:
            logger.warning(
                "google_ads_metrics_job: falha tipo=%s",
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


_worker: GoogleAdsMetricsSyncWorker | None = None


def get_worker() -> GoogleAdsMetricsSyncWorker | None:
    return _worker


def start_worker(
    db_factory: Callable[[], Session],
) -> GoogleAdsMetricsSyncWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = GoogleAdsMetricsSyncWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker(timeout: float = 5.0) -> None:
    global _worker
    if _worker is not None:
        _worker.stop(timeout=timeout)
        _worker = None
