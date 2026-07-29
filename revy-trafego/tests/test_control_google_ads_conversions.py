"""Fase 4D — bindings e outbox de conversões (fakes only)."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.config import settings
from app.control.google_ads import (
    FakeGoogleAdsTokenExchanger,
    FakeGoogleDataManagerPort,
    GOOGLE_ADS_SCOPES,
    GoogleAdsConnectionControl,
    OAuthTokenBundle,
)
from app.control.google_ads_conversions import (
    EVENT_VENDA_CONFIRMADA,
    EnqueueConversion,
    GoogleAdsConversionsControl,
    OUTBOX_SENT,
    build_transaction_id,
    hash_user_value,
)
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore, StoreRef
from app.db import SessionLocal
from app.models import (
    GestorRevy,
    GoogleAdsConversionOutbox,
    GoogleAdsUploadAttempt,
)
from app.web import control as control_mod


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _create_store(slug: str) -> str:
    return StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Conv", slug=slug),
    ).id


def _connect_store(loja_id: str, customer_id: str = "1112223333") -> None:
    admin = _admin_actor()
    control = GoogleAdsConnectionControl(
        SessionLocal,
        client_id="cid",
        client_secret="sec",
        redirect_uri="https://control.revy.test/cb",
        token_exchanger=FakeGoogleAdsTokenExchanger(
            default_bundle=OAuthTokenBundle(
                refresh_token="rt-conv-secret",
                access_token="at",
                scopes=GOOGLE_ADS_SCOPES,
            )
        ),
    )
    started = control.start_oauth(admin, StoreRef(id=loja_id))
    control.complete_oauth(
        state=started.state,
        code="code-conv",
        customer_id=customer_id,
    )


def test_transaction_id_deterministico():
    a = build_transaction_id("loja-1", "venda_confirmada", "evt-9")
    b = build_transaction_id("loja-1", "venda_confirmada", "evt-9")
    c = build_transaction_id("loja-1", "venda_confirmada", "evt-10")
    assert a == "revy:loja-1:venda_confirmada:evt-9"
    assert a == b
    assert a != c


def test_enqueue_idempotent_e_process_reusa_transaction_id():
    loja_id = _create_store("loja-conv-outbox")
    _connect_store(loja_id)
    admin = _admin_actor()
    port = FakeGoogleDataManagerPort(next_request_id="req-100")
    control = GoogleAdsConversionsControl(
        SessionLocal,
        data_manager_port=port,
        now=lambda: datetime(2026, 7, 29, 16, 0, 0, tzinfo=timezone.utc),
    )

    control.bind_conversion_action(
        admin,
        StoreRef(id=loja_id),
        revy_event_type=EVENT_VENDA_CONFIRMADA,
        conversion_action_resource_name="customers/1112223333/conversionActions/7",
        customer_id="1112223333",
    )

    cmd = EnqueueConversion(
        loja_id=loja_id,
        event_type=EVENT_VENDA_CONFIRMADA,
        domain_event_id="venda-42",
        gclid="Cj0KCQjw-gclid",
        value=Decimal("15000.00"),
        currency="BRL",
        consent=False,
        email="cliente@example.com",
        phone="11999999999",
    )
    first = control.enqueue_conversion(cmd)
    second = control.enqueue_conversion(cmd)
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.transaction_id == build_transaction_id(
        loja_id, EVENT_VENDA_CONFIRMADA, "venda-42"
    )

    with SessionLocal() as db:
        count = (
            db.query(GoogleAdsConversionOutbox)
            .filter(GoogleAdsConversionOutbox.loja_id == loja_id)
            .count()
        )
        assert count == 1
        row = db.query(GoogleAdsConversionOutbox).one()
        payload = json.loads(row.payload_json)
        # sem consent → sem user_data enhanced
        assert "user_data" not in payload["event"]
        assert payload["event"]["consent"]["ad_user_data"] == "DENIED"
        assert payload["event"]["ad_identifiers"]["gclid"] == "Cj0KCQjw-gclid"
        assert payload["event"]["transaction_id"] == first.transaction_id

    sent = control.process_outbox_once(loja_id=loja_id)
    assert sent == 1
    assert len(port.ingests) == 1
    ingest = port.ingests[0]
    assert ingest["customer_id"] == "1112223333"
    assert ingest["events"][0]["transaction_id"] == first.transaction_id
    assert "user_data" not in ingest["events"][0]
    assert ingest["refresh_token"] == "rt-conv-secret"

    with SessionLocal() as db:
        row = db.query(GoogleAdsConversionOutbox).one()
        assert row.status == OUTBOX_SENT
        assert row.request_id == "req-100"
        attempts = db.query(GoogleAdsUploadAttempt).all()
        assert len(attempts) == 1
        assert attempts[0].request_id == "req-100"

    # process again: nothing pending (no duplicate ingest)
    assert control.process_outbox_once(loja_id=loja_id) == 0
    assert len(port.ingests) == 1


def test_retry_reuses_same_transaction_id_no_duplicate_outbox():
    loja_id = _create_store("loja-conv-retry")
    _connect_store(loja_id)
    admin = _admin_actor()

    class FlakyPort(FakeGoogleDataManagerPort):
        def __init__(self) -> None:
            super().__init__(next_request_id="req-retry")
            self.calls = 0

        def ingest(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary google failure")
            return super().ingest(**kwargs)

    port = FlakyPort()
    fixed = datetime(2026, 7, 29, 17, 0, 0, tzinfo=timezone.utc)
    control = GoogleAdsConversionsControl(
        SessionLocal,
        data_manager_port=port,
        now=lambda: fixed,
        max_attempts=5,
    )
    control.bind_conversion_action(
        admin,
        StoreRef(id=loja_id),
        revy_event_type=EVENT_VENDA_CONFIRMADA,
        conversion_action_resource_name="customers/1112223333/conversionActions/1",
        customer_id="1112223333",
    )
    tx = build_transaction_id(loja_id, EVENT_VENDA_CONFIRMADA, "evt-retry")
    view = control.enqueue_conversion(
        EnqueueConversion(
            loja_id=loja_id,
            event_type=EVENT_VENDA_CONFIRMADA,
            domain_event_id="evt-retry",
            gclid="GCLID-RETRY",
            value="100",
            consent=True,
            email="Com Consent@Example.COM",
            phone="11988887777",
        )
    )
    assert view is not None
    assert view.transaction_id == tx

    # 1ª tentativa falha
    assert control.process_outbox_once(loja_id=loja_id) == 0
    with SessionLocal() as db:
        row = db.query(GoogleAdsConversionOutbox).one()
        assert row.status == "failed"
        assert row.attempts == 1
        # libera retry imediato
        row.next_attempt_at = fixed
        db.commit()

    # 2ª tenta e envia — mesmo transaction_id no ingest
    assert control.process_outbox_once(loja_id=loja_id) == 1
    assert port.calls == 2
    assert len(port.ingests) == 1
    assert port.ingests[0]["events"][0]["transaction_id"] == tx

    # consent → user_data hasheado; email normalizado lower
    event = port.ingests[0]["events"][0]
    assert "user_data" in event
    assert event["user_data"]["email_hash"] == hash_user_value(
        "Com Consent@Example.COM"
    )
    assert event["user_data"]["phone_hash"] == hash_user_value("11988887777")

    with SessionLocal() as db:
        assert db.query(GoogleAdsConversionOutbox).count() == 1
        assert db.query(GoogleAdsUploadAttempt).count() == 2


def test_enqueue_sem_binding_ou_click_id_retorna_none():
    loja_id = _create_store("loja-conv-none")
    control = GoogleAdsConversionsControl(SessionLocal)
    assert (
        control.enqueue_conversion(
            EnqueueConversion(
                loja_id=loja_id,
                event_type=EVENT_VENDA_CONFIRMADA,
                domain_event_id="x",
                gclid="g",
            )
        )
        is None
    )
    assert (
        control.enqueue_conversion(
            EnqueueConversion(
                loja_id=loja_id,
                event_type=EVENT_VENDA_CONFIRMADA,
                domain_event_id="y",
            )
        )
        is None
    )


def test_enqueue_never_raises_to_caller():
    """Fire-and-forget: falhas internas não propagam."""
    loja_id = _create_store("loja-conv-safe")
    admin = _admin_actor()
    control = GoogleAdsConversionsControl(SessionLocal)
    control.bind_conversion_action(
        admin,
        StoreRef(id=loja_id),
        revy_event_type=EVENT_VENDA_CONFIRMADA,
        conversion_action_resource_name="customers/1/conversionActions/1",
        customer_id="1",
    )

    # força falha no session_factory
    broken = GoogleAdsConversionsControl(lambda: (_ for _ in ()).throw(RuntimeError("db")))
    assert (
        broken.enqueue_conversion(
            EnqueueConversion(
                loja_id=loja_id,
                event_type=EVENT_VENDA_CONFIRMADA,
                domain_event_id="z",
                gclid="gclid",
            )
        )
        is None
    )


def test_http_bind_conversion_under_flag(client, monkeypatch):
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=True,
            google_conversions_enabled=False,
            google_ads_sync_enabled=True,
            google_ads_oauth_client_id="c",
            google_ads_oauth_client_secret="s",
            google_ads_oauth_redirect_uri="https://x/cb",
        ),
    )
    r = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "L", "slug": "loja-conv-flag"},
    ).json()
    blocked = client.post(
        f"/control/v1/lojas/{store['id']}/google-ads/conversion-bindings",
        json={
            "revy_event_type": "venda_confirmada",
            "conversion_action_resource_name": "customers/1/conversionActions/1",
            "customer_id": "1112223333",
        },
    )
    assert blocked.status_code == 404

    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=True,
            google_conversions_enabled=True,
            google_ads_sync_enabled=True,
            google_ads_oauth_client_id="c",
            google_ads_oauth_client_secret="s",
            google_ads_oauth_redirect_uri="https://x/cb",
        ),
    )
    ok = client.post(
        f"/control/v1/lojas/{store['id']}/google-ads/conversion-bindings",
        json={
            "revy_event_type": "venda_confirmada",
            "conversion_action_resource_name": "customers/1112223333/conversionActions/9",
            "customer_id": "111-222-3333",
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["customer_id"] == "1112223333"
    assert body["revy_event_type"] == "venda_confirmada"
    assert "refresh" not in str(body).lower()

    listed = client.get(
        f"/control/v1/lojas/{store['id']}/google-ads/conversion-bindings"
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1
