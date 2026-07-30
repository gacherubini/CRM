"""Workers de produção Google Ads (conversions outbox + metrics sync)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from app.control.google_ads import (
    CONNECTION_STATUS_CONNECTED,
    FakeGoogleAdsReadPort,
    GoogleAdsMetricRow,
)
from app.control.google_ads_conversions import GoogleAdsConversionsControl
from app.control.google_ads_metrics import (
    GoogleAdsMetricsControl,
    SyncMetricsResult,
)
from app.control.google_ads_metrics_job import listar_lojas_para_metrics_sync
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore, StoreStatus
from app.cripto import cifrar
from app.db import SessionLocal
from app.models import (
    GoogleAdsAccount,
    GoogleAdsConnection,
    GestorRevy,
    Loja,
    novo_id,
)


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _create_store(slug: str, *, status: str | None = None) -> str:
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name=f"Loja {slug}", slug=slug),
    )
    target = status or StoreStatus.ACTIVE.value
    with SessionLocal() as db:
        loja = db.query(Loja).filter(Loja.id == store.id).one()
        loja.status = target
        db.commit()
    return store.id


def _seed_connected_store(
    loja_id: str,
    *,
    selected: bool = True,
    customer_id: str = "1112223333",
) -> None:
    with SessionLocal() as db:
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        db.add(
            GoogleAdsConnection(
                id=novo_id(),
                loja_id=loja_id,
                status=CONNECTION_STATUS_CONNECTED,
                customer_id=customer_id if selected else None,
                login_customer_id="9990001111",
                refresh_token_ciphertext=cifrar("rt-secret"),
                scopes="https://www.googleapis.com/auth/adwords",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            GoogleAdsAccount(
                id=novo_id(),
                loja_id=loja_id,
                customer_id=customer_id,
                login_customer_id="9990001111",
                is_manager=False,
                currency_code="BRL",
                time_zone="America/Sao_Paulo",
                descriptive_name="Conta Teste",
                selected=selected,
                status="ativo",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()


# ── conversions outbox worker ──────────────────────────────────────────────


def test_conversions_worker_run_once_with_fake_control(monkeypatch):
    from app.control import google_ads_conversions_job as job

    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "1")

    fake_control = MagicMock(spec=GoogleAdsConversionsControl)
    fake_control.process_outbox_once.return_value = 3

    w = job.GoogleAdsConversionsWorker(
        db_factory=SessionLocal,
        enabled=True,
        interval_seconds=60,
        initial_delay_seconds=0,
        control=fake_control,
        batch_limit=10,
    )
    payload = w.run_once()
    assert payload == {"ok": True, "sent": 3}
    assert w.last_result == payload
    fake_control.process_outbox_once.assert_called_once_with(limit=10)


def test_conversions_worker_skips_when_feature_off(monkeypatch):
    from app.control import google_ads_conversions_job as job

    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "0")
    fake_control = MagicMock(spec=GoogleAdsConversionsControl)

    w = job.GoogleAdsConversionsWorker(
        db_factory=SessionLocal,
        enabled=True,
        control=fake_control,
    )
    payload = w.run_once()
    assert payload["ok"] is True
    assert payload["skipped"] is True
    fake_control.process_outbox_once.assert_not_called()


def test_conversions_worker_start_skipped_when_disabled(monkeypatch):
    from app.control import google_ads_conversions_job as job

    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "1")
    w = job.GoogleAdsConversionsWorker(
        db_factory=SessionLocal,
        enabled=False,
        interval_seconds=1,
        initial_delay_seconds=0,
    )
    w.start()
    assert w._thread is None
    w.stop()


def test_conversions_worker_start_skipped_when_feature_off(monkeypatch):
    from app.control import google_ads_conversions_job as job

    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "0")
    w = job.GoogleAdsConversionsWorker(
        db_factory=SessionLocal,
        enabled=True,
        interval_seconds=1,
        initial_delay_seconds=0,
    )
    w.start()
    assert w._thread is None
    w.stop()


def test_conversions_worker_run_once_swallows_errors(monkeypatch):
    from app.control import google_ads_conversions_job as job

    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "1")
    fake_control = MagicMock(spec=GoogleAdsConversionsControl)
    fake_control.process_outbox_once.side_effect = RuntimeError("boom")

    w = job.GoogleAdsConversionsWorker(
        db_factory=SessionLocal,
        enabled=True,
        control=fake_control,
    )
    payload = w.run_once()
    assert payload == {"ok": False, "erro": "RuntimeError", "sent": 0}


def test_conversions_worker_default_follows_conversions_enabled(monkeypatch):
    from app.control.google_ads_conversions_job import GoogleAdsConversionsWorker

    monkeypatch.delenv("GOOGLE_CONVERSIONS_WORKER_ENABLED", raising=False)
    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "1")
    w = GoogleAdsConversionsWorker(db_factory=SessionLocal)
    assert w.enabled is True
    assert w.interval == 60.0
    assert w.initial_delay == 30.0

    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "0")
    w2 = GoogleAdsConversionsWorker(db_factory=SessionLocal)
    assert w2.enabled is False

    monkeypatch.setenv("GOOGLE_CONVERSIONS_WORKER_ENABLED", "0")
    monkeypatch.setenv("GOOGLE_CONVERSIONS_ENABLED", "1")
    w3 = GoogleAdsConversionsWorker(db_factory=SessionLocal)
    assert w3.enabled is False


# ── metrics sync worker ────────────────────────────────────────────────────


def test_metrics_worker_run_once_with_fake_control(monkeypatch):
    from app.control import google_ads_metrics_job as job

    loja_id = _create_store("metrics-job-ok")
    _seed_connected_store(loja_id)

    fake_control = MagicMock(spec=GoogleAdsMetricsControl)
    fake_control.sync_metrics_for_store_id.return_value = SyncMetricsResult(
        loja_id=loja_id,
        customer_id="1112223333",
        rows_upserted=2,
        date_from="2026-07-23",
        date_to="2026-07-29",
    )

    w = job.GoogleAdsMetricsSyncWorker(
        db_factory=SessionLocal,
        enabled=True,
        interval_seconds=86400,
        initial_delay_seconds=0,
        time_window_days=7,
        control=fake_control,
        today=lambda: date(2026, 7, 29),
    )
    payload = w.run_once()
    assert payload["ok"] is True
    assert payload["lojas"] == 1
    assert payload["status_ok"] == 1
    assert payload["rows_upserted"] == 2
    assert payload["date_from"] == "2026-07-23"
    assert payload["date_to"] == "2026-07-29"
    fake_control.sync_metrics_for_store_id.assert_called_once_with(
        loja_id,
        date_from="2026-07-23",
        date_to="2026-07-29",
    )


def test_metrics_worker_skips_suspended_store():
    from app.control import google_ads_metrics_job as job

    active_id = _create_store(
        "metrics-active", status=StoreStatus.ACTIVE.value
    )
    suspended_id = _create_store(
        "metrics-suspensa", status=StoreStatus.SUSPENDED.value
    )
    _seed_connected_store(active_id, customer_id="1000000001")
    _seed_connected_store(suspended_id, customer_id="1000000002")

    with SessionLocal() as db:
        listed = listar_lojas_para_metrics_sync(db)
    assert active_id in listed
    assert suspended_id not in listed

    fake_control = MagicMock(spec=GoogleAdsMetricsControl)
    fake_control.sync_metrics_for_store_id.return_value = SyncMetricsResult(
        loja_id=active_id,
        customer_id="1000000001",
        rows_upserted=1,
        date_from="2026-07-28",
        date_to="2026-07-29",
    )

    w = job.GoogleAdsMetricsSyncWorker(
        db_factory=SessionLocal,
        enabled=True,
        time_window_days=2,
        control=fake_control,
        today=lambda: date(2026, 7, 29),
    )
    payload = w.run_once()
    assert payload["ok"] is True
    assert payload["lojas"] == 1
    assert payload["status_ok"] == 1
    called_ids = [
        c.args[0] for c in fake_control.sync_metrics_for_store_id.call_args_list
    ]
    assert called_ids == [active_id]


def test_metrics_worker_run_once_swallows_errors():
    from app.control import google_ads_metrics_job as job

    loja_id = _create_store("metrics-boom")
    _seed_connected_store(loja_id)

    fake_control = MagicMock(spec=GoogleAdsMetricsControl)
    fake_control.sync_metrics_for_store_id.side_effect = RuntimeError("api-down")

    w = job.GoogleAdsMetricsSyncWorker(
        db_factory=SessionLocal,
        enabled=True,
        control=fake_control,
        today=lambda: date(2026, 7, 29),
    )
    payload = w.run_once()
    assert payload["ok"] is True
    assert payload["status_erro"] == 1
    assert payload["status_ok"] == 0


def test_metrics_worker_start_default_off():
    from app.control.google_ads_metrics_job import GoogleAdsMetricsSyncWorker

    w = GoogleAdsMetricsSyncWorker(
        db_factory=SessionLocal,
        interval_seconds=1,
        initial_delay_seconds=0,
    )
    assert w.enabled is False
    w.start()
    assert w._thread is None
    w.stop()


def test_sync_metrics_for_store_id_no_rbac():
    """Método interno não exige Actor e upserta via read_port fake."""
    loja_id = _create_store("metrics-internal")
    _seed_connected_store(loja_id, customer_id="5556667777")

    read_port = FakeGoogleAdsReadPort(
        metrics=[
            GoogleAdsMetricRow(
                customer_id="5556667777",
                campaign_id="c1",
                date="2026-07-28",
                impressions=100,
                clicks=10,
                cost_micros=1_500_000,
                conversions=1.0,
                conversions_value=50.0,
            )
        ]
    )
    control = GoogleAdsMetricsControl(SessionLocal, read_port=read_port)
    result = control.sync_metrics_for_store_id(
        loja_id,
        date_from="2026-07-28",
        date_to="2026-07-28",
    )
    assert result.loja_id == loja_id
    assert result.customer_id == "5556667777"
    assert result.rows_upserted == 1


# ── internal job endpoints ─────────────────────────────────────────────────


def test_job_endpoints_require_secret_and_token(client, monkeypatch):
    from app import config as config_mod
    from app.control import google_ads_conversions_job, google_ads_metrics_job

    monkeypatch.delenv("PORTAL_META_SPEND_JOB_SECRET", raising=False)

    monkeypatch.setattr(
        "app.main.settings",
        replace(config_mod.settings, job_secret=""),
    )
    for path in (
        "/internal/jobs/google-conversions-outbox",
        "/internal/jobs/google-ads-metrics-sync",
    ):
        r = client.post(path)
        assert r.status_code == 503, path

    monkeypatch.setattr(
        "app.main.settings",
        replace(config_mod.settings, job_secret="segredo-job-gads"),
    )

    for path in (
        "/internal/jobs/google-conversions-outbox",
        "/internal/jobs/google-ads-metrics-sync",
    ):
        r401 = client.post(path, headers={"X-Job-Token": "errado"})
        assert r401.status_code == 401, path

    class FakeConvWorker:
        def run_once(self):
            return {"ok": True, "sent": 1}

    class FakeMetricsWorker:
        def run_once(self):
            return {"ok": True, "lojas": 0}

    monkeypatch.setattr(
        google_ads_conversions_job, "get_worker", lambda: FakeConvWorker()
    )
    monkeypatch.setattr(
        google_ads_metrics_job, "get_worker", lambda: FakeMetricsWorker()
    )

    r_conv = client.post(
        "/internal/jobs/google-conversions-outbox",
        headers={"X-Job-Token": "segredo-job-gads"},
    )
    assert r_conv.status_code == 200
    assert r_conv.json()["sent"] == 1

    r_met = client.post(
        "/internal/jobs/google-ads-metrics-sync",
        headers={"X-Job-Token": "segredo-job-gads"},
    )
    assert r_met.status_code == 200
    assert r_met.json()["ok"] is True


def test_workers_not_running_during_suite():
    from app.control import google_ads_conversions_job, google_ads_metrics_job

    assert google_ads_conversions_job.get_worker() is None
    assert google_ads_metrics_job.get_worker() is None
