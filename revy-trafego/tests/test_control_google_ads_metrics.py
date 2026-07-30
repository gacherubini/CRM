"""Fase 4B — sync de contas, métricas diárias e derivados money-safe."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.auth import hash_senha
from app.config import settings
from app.control.google_ads import (
    FakeGoogleAdsReadPort,
    FakeGoogleAdsTokenExchanger,
    GOOGLE_ADS_SCOPES,
    GoogleAdsAccount as AccountDTO,
    GoogleAdsConnectionControl,
    GoogleAdsConversionAction,
    GoogleAdsMetricRow,
    OAuthTokenBundle,
)
from app.control.google_ads_metrics import (
    GoogleAdsManagerAccountNotSelectable,
    GoogleAdsMetricsControl,
    compute_cpl,
    compute_cpc,
    compute_ctr,
    compute_roas,
    cost_from_micros,
)
from app import config as config_mod
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    CreateStore,
    StoreNotFound,
    StoreRef,
)
from app.db import SessionLocal
from app.models import (
    GestorRevy,
    GoogleAdsAccount,
    GoogleAdsCampaignDaily,
    GoogleAdsConnection,
    VinculoTrafego,
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
        CreateStore(name="Loja Metrics", slug=slug),
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
                refresh_token="rt-metrics-secret",
                access_token="at",
                scopes=GOOGLE_ADS_SCOPES,
            )
        ),
    )
    started = control.start_oauth(admin, StoreRef(id=loja_id))
    control.complete_oauth(
        state=started.state,
        code="code-metrics",
        customer_id=customer_id,
        login_customer_id="9990001111",
    )


def _metrics_control(
    read_port: FakeGoogleAdsReadPort | None = None,
) -> GoogleAdsMetricsControl:
    return GoogleAdsMetricsControl(
        SessionLocal,
        read_port=read_port or FakeGoogleAdsReadPort(),
        now=lambda: datetime(2026, 7, 29, 15, 0, 0, tzinfo=timezone.utc),
    )


def test_cost_micros_math_money_safe():
    assert cost_from_micros(1_500_000) == Decimal("1.50")
    assert cost_from_micros(1) == Decimal("0.00")
    assert cost_from_micros(500) == Decimal("0.00")
    assert cost_from_micros(5_000) == Decimal("0.01")  # 0.005 → 0.01 half up
    assert cost_from_micros(0) == Decimal("0.00")
    assert compute_ctr(1000, 25) == Decimal("0.0250")
    assert compute_ctr(0, 1) is None
    assert compute_cpc(1_500_000, 2) == Decimal("0.75")
    assert compute_cpc(1_000_000, 0) is None
    # CPL = cost / conversions Google
    assert compute_cpl(3_000_000, Decimal("2")) == Decimal("1.50")
    assert compute_cpl(1_000_000, 0) is None
    assert compute_cpl(1_000_000, Decimal("0")) is None
    # ROAS = conversions_value / cost (Google only)
    assert compute_roas(2_000_000, Decimal("10")) == Decimal("5.00")
    assert compute_roas(0, Decimal("10")) is None
    assert compute_roas(1_000_000, Decimal("0")) is None
    assert compute_roas(1_000_000, 0) is None


def test_sync_accounts_e_select_rejeita_manager():
    loja_id = _create_store("loja-metrics-accounts")
    _connect_store(loja_id)
    admin = _admin_actor()
    port = FakeGoogleAdsReadPort(
        accounts=[
            AccountDTO(
                customer_id="1112223333",
                descriptive_name="Anunciante",
                is_manager=False,
                currency_code="BRL",
                time_zone="America/Sao_Paulo",
                login_customer_id="9990001111",
            ),
            AccountDTO(
                customer_id="5556667777",
                descriptive_name="Manager MCC",
                is_manager=True,
                currency_code="BRL",
                login_customer_id=None,
            ),
        ]
    )
    control = _metrics_control(port)

    views = control.sync_accounts(admin, StoreRef(id=loja_id))
    assert len(views) == 2
    assert {v.customer_id for v in views} == {"1112223333", "5556667777"}

    with pytest.raises(GoogleAdsManagerAccountNotSelectable):
        control.select_account(admin, StoreRef(id=loja_id), "5556667777")

    selected = control.select_account(admin, StoreRef(id=loja_id), "1112223333")
    assert selected.selected is True
    assert selected.is_manager is False

    with SessionLocal() as db:
        mgr = (
            db.query(GoogleAdsAccount)
            .filter(
                GoogleAdsAccount.loja_id == loja_id,
                GoogleAdsAccount.customer_id == "5556667777",
            )
            .one()
        )
        assert mgr.selected is False
        ann = (
            db.query(GoogleAdsAccount)
            .filter(
                GoogleAdsAccount.loja_id == loja_id,
                GoogleAdsAccount.customer_id == "1112223333",
            )
            .one()
        )
        assert ann.selected is True


def test_sync_metrics_upsert_idempotent():
    loja_id = _create_store("loja-metrics-upsert")
    _connect_store(loja_id, customer_id="1234567890")
    admin = _admin_actor()
    port = FakeGoogleAdsReadPort(
        accounts=[
            AccountDTO(
                customer_id="1234567890",
                descriptive_name="Loja",
                is_manager=False,
                currency_code="BRL",
            )
        ],
        metrics=[
            GoogleAdsMetricRow(
                customer_id="1234567890",
                campaign_id="99",
                date="2026-07-01",
                impressions=10,
                clicks=2,
                cost_micros=1_500_000,
                conversions=1.0,
                conversions_value=100.0,
            ),
        ],
    )
    control = _metrics_control(port)
    control.sync_accounts(admin, StoreRef(id=loja_id))
    control.select_account(admin, StoreRef(id=loja_id), "1234567890")

    first = control.sync_metrics(
        admin,
        StoreRef(id=loja_id),
        date_from="2026-07-01",
        date_to="2026-07-31",
    )
    assert first.rows_upserted == 1

    # atualiza fonte e re-sync — ainda 1 linha
    port.metrics = [
        GoogleAdsMetricRow(
            customer_id="1234567890",
            campaign_id="99",
            date="2026-07-01",
            impressions=20,
            clicks=4,
            cost_micros=3_000_000,
            conversions=2.0,
            conversions_value=200.0,
        ),
    ]
    second = control.sync_metrics(
        admin,
        StoreRef(id=loja_id),
        date_from="2026-07-01",
        date_to="2026-07-31",
    )
    assert second.rows_upserted == 1

    with SessionLocal() as db:
        rows = (
            db.query(GoogleAdsCampaignDaily)
            .filter(GoogleAdsCampaignDaily.loja_id == loja_id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].impressions == 20
        assert rows[0].clicks == 4
        assert rows[0].cost_micros == 3_000_000
        assert Decimal(str(rows[0].conversions)) == Decimal("2.0")

    summary = control.metrics_summary(
        admin,
        StoreRef(id=loja_id),
        date_from="2026-07-01",
        date_to="2026-07-31",
    )
    assert summary.impressions == 20
    assert summary.clicks == 4
    assert summary.cost == Decimal("3.00")
    assert summary.cost_micros == 3_000_000
    assert summary.ctr == Decimal("0.2000")
    assert summary.cpc == Decimal("0.75")
    assert summary.conversions == Decimal("2.0")
    assert summary.conversions_value == Decimal("200.0")
    # cost 3.00 / 2 conv = 1.50; value 200 / cost 3 = 66.67
    assert summary.cpl == Decimal("1.50")
    assert summary.cost_per_conversion == Decimal("1.50")
    assert summary.roas == Decimal("66.67")


def test_colaborador_le_metricas_mas_nao_sincroniza():
    loja_id = _create_store("loja-metrics-rbac")
    _connect_store(loja_id)
    admin = _admin_actor()

    with SessionLocal() as db:
        collab = GestorRevy(
            email="colab-metrics@revy.local",
            nome="Colab Metrics",
            senha_hash=hash_senha("secret-teste"),
            papel="gestor",
            ativo=True,
        )
        db.add(collab)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=loja_id,
                gestor_id=collab.id,
                tipo="colaborador",
            )
        )
        db.commit()
        collab_id = collab.id

    collab_actor = Actor(
        id=collab_id,
        email="colab-metrics@revy.local",
        name="Colab Metrics",
        role="gestor",
    )
    port = FakeGoogleAdsReadPort(
        accounts=[
            AccountDTO(
                customer_id="1112223333",
                descriptive_name="X",
                is_manager=False,
                currency_code="BRL",
            )
        ],
        metrics=[
            GoogleAdsMetricRow(
                customer_id="1112223333",
                campaign_id="1",
                date="2026-07-10",
                impressions=5,
                clicks=1,
                cost_micros=100_000,
            )
        ],
    )
    control = _metrics_control(port)
    control.sync_accounts(admin, StoreRef(id=loja_id))
    control.select_account(admin, StoreRef(id=loja_id), "1112223333")
    control.sync_metrics(
        admin,
        StoreRef(id=loja_id),
        date_from="2026-07-01",
        date_to="2026-07-31",
    )

    # colaborador lê
    summary = control.metrics_summary(
        collab_actor,
        StoreRef(id=loja_id),
        date_from="2026-07-01",
        date_to="2026-07-31",
    )
    assert summary.impressions == 5
    accounts = control.list_accounts(collab_actor, StoreRef(id=loja_id))
    assert len(accounts) == 1

    # colaborador não sincroniza nem seleciona
    with pytest.raises(AccessDenied):
        control.sync_metrics(
            collab_actor,
            StoreRef(id=loja_id),
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
    with pytest.raises(AccessDenied):
        control.select_account(
            collab_actor, StoreRef(id=loja_id), "1112223333"
        )


def test_gestor_sem_vinculo_nao_ve_metricas():
    loja_id = _create_store("loja-metrics-iso")
    _connect_store(loja_id)
    admin = _admin_actor()
    control = _metrics_control()
    with SessionLocal() as db:
        outsider = GestorRevy(
            email="out-metrics@revy.local",
            nome="Out",
            senha_hash=hash_senha("secret-teste"),
            papel="gestor",
            ativo=True,
        )
        db.add(outsider)
        db.commit()
        oid = outsider.id
    outsider_actor = Actor(
        id=oid, email="out-metrics@revy.local", name="Out", role="gestor"
    )
    with pytest.raises(StoreNotFound):
        control.metrics_summary(
            outsider_actor,
            StoreRef(id=loja_id),
            date_from="2026-07-01",
            date_to="2026-07-31",
        )
    with pytest.raises(StoreNotFound):
        control.list_accounts(outsider_actor, StoreRef(id=loja_id))
    # silencia unused
    assert admin.id


# --- HTTP ---


def _enable_flags(monkeypatch, *, control: bool = True, google: bool = True) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=control,
            google_ads_sync_enabled=google,
            google_ads_oauth_client_id="http-client-id",
            google_ads_oauth_client_secret="http-client-secret",
            google_ads_oauth_redirect_uri=(
                "https://control.revy.test/control/v1/google-ads/oauth/callback"
            ),
        ),
    )


def _login_admin(client) -> None:
    response = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_http_metrics_summary_sem_secrets(client, monkeypatch):
    _enable_flags(monkeypatch)
    _login_admin(client)
    created = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja HTTP Metrics", "slug": "loja-http-metrics"},
    )
    assert created.status_code == 201
    loja_id = created.json()["id"]

    start = client.post(f"/control/v1/lojas/{loja_id}/google-ads/oauth/start")
    assert start.status_code == 200
    cb = client.get(
        "/control/v1/google-ads/oauth/callback",
        params={"state": start.json()["state"], "code": "c"},
    )
    assert cb.status_code == 200

    # seed daily row
    with SessionLocal() as db:
        db.add(
            GoogleAdsCampaignDaily(
                loja_id=loja_id,
                customer_id="1112223333",
                campaign_id="c1",
                date=datetime(2026, 7, 5).date(),
                impressions=100,
                clicks=10,
                cost_micros=2_500_000,
                conversions=Decimal("1"),
                conversions_value=Decimal("50"),
                currency_code="BRL",
            )
        )
        db.commit()

    summary = client.get(
        f"/control/v1/lojas/{loja_id}/google-ads/metrics/summary",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["impressions"] == 100
    assert body["cost"] == "2.50"
    assert body["cost_micros"] == 2_500_000
    assert body["cpl"] == "2.50"  # 2.50 / 1 conv
    assert body["cost_per_conversion"] == "2.50"
    assert body["roas"] == "20.00"  # 50 / 2.50
    assert "refresh_token" not in str(body).lower()
    assert "ciphertext" not in str(body).lower()
    assert "secret" not in str(body).lower()

    accounts = client.get(f"/control/v1/lojas/{loja_id}/google-ads/accounts")
    assert accounts.status_code == 200
    assert "items" in accounts.json()


def test_list_conversion_actions_fake_port_e_http():
    loja_id = _create_store("loja-metrics-conv-actions")
    _connect_store(loja_id, customer_id="1112223333")
    admin = _admin_actor()
    actions = [
        GoogleAdsConversionAction(
            resource_name="customers/1112223333/conversionActions/7",
            id="7",
            name="Compra",
            type="UPLOAD_CLICKS",
            status="ENABLED",
            category="PURCHASE",
            primary_for_goal=True,
        )
    ]
    port = FakeGoogleAdsReadPort(
        accounts=[
            AccountDTO(
                customer_id="1112223333",
                descriptive_name="Anunciante",
                is_manager=False,
                currency_code="BRL",
            )
        ],
        conversion_actions=actions,
    )
    control = _metrics_control(port)
    control.sync_accounts(admin, StoreRef(id=loja_id))
    control.select_account(admin, StoreRef(id=loja_id), "1112223333")

    listed = control.list_conversion_actions(admin, StoreRef(id=loja_id))
    assert len(listed) == 1
    assert listed[0].resource_name.endswith("/conversionActions/7")
    assert listed[0].name == "Compra"
    assert port.list_conversion_actions_calls
    assert port.list_conversion_actions_calls[0]["customer_id"] == "1112223333"


def test_http_conversion_actions_endpoint(client, monkeypatch):
    _enable_flags(monkeypatch)
    _login_admin(client)
    created = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Conv Actions", "slug": "loja-http-conv-actions"},
    )
    assert created.status_code == 201
    loja_id = created.json()["id"]

    start = client.post(f"/control/v1/lojas/{loja_id}/google-ads/oauth/start")
    assert start.status_code == 200
    cb = client.get(
        "/control/v1/google-ads/oauth/callback",
        params={"state": start.json()["state"], "code": "c"},
    )
    assert cb.status_code == 200

    # fake port default tem conversion_actions vazio — list retorna items []
    with SessionLocal() as db:
        conn = (
            db.query(GoogleAdsConnection)
            .filter(GoogleAdsConnection.loja_id == loja_id)
            .one()
        )
        conn.customer_id = "1112223333"
        row = (
            db.query(GoogleAdsAccount)
            .filter(GoogleAdsAccount.loja_id == loja_id)
            .first()
        )
        if row is None:
            db.add(
                GoogleAdsAccount(
                    loja_id=loja_id,
                    customer_id="1112223333",
                    is_manager=False,
                    selected=True,
                    status="ativo",
                )
            )
        else:
            row.selected = True
            row.is_manager = False
        db.commit()

    response = client.get(
        f"/control/v1/lojas/{loja_id}/google-ads/conversion-actions"
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_service_aquisicao_resumo(client, monkeypatch):
    _enable_flags(monkeypatch)
    token = "svc-aquisicao-tok"
    monkeypatch.setattr(
        config_mod,
        "settings",
        replace(config_mod.settings, service_token=token),
    )
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=True,
            google_ads_sync_enabled=True,
            service_token=token,
            google_ads_oauth_client_id="http-client-id",
            google_ads_oauth_client_secret="http-client-secret",
            google_ads_oauth_redirect_uri=(
                "https://control.revy.test/control/v1/google-ads/oauth/callback"
            ),
        ),
    )
    headers = {"X-Service-Token": token}

    # sem token
    r = client.get(
        "/control/v1/internal/lojas/x/aquisicao-resumo",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )
    assert r.status_code == 401

    # loja inexistente
    missing = client.get(
        "/control/v1/internal/lojas/nao-existe/aquisicao-resumo",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
        headers=headers,
    )
    assert missing.status_code == 404

    _login_admin(client)
    created = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Aquisicao", "slug": "loja-aquisicao-svc"},
    )
    assert created.status_code == 201
    loja_id = created.json()["id"]

    # sem Google: disponivel false, sem inventar zeros
    empty = client.get(
        f"/control/v1/internal/lojas/{loja_id}/aquisicao-resumo",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
        headers=headers,
    )
    assert empty.status_code == 200
    body = empty.json()
    assert body["loja_id"] == loja_id
    assert body["google_disponivel"] is False
    assert body["google"] is None
    assert "refresh_token" not in str(body).lower()

    # conecta + seed métricas
    start = client.post(f"/control/v1/lojas/{loja_id}/google-ads/oauth/start")
    assert start.status_code == 200
    cb = client.get(
        "/control/v1/google-ads/oauth/callback",
        params={"state": start.json()["state"], "code": "c"},
    )
    assert cb.status_code == 200

    with SessionLocal() as db:
        conn = (
            db.query(GoogleAdsConnection)
            .filter(GoogleAdsConnection.loja_id == loja_id)
            .one()
        )
        conn.customer_id = "1112223333"
        db.add(
            GoogleAdsCampaignDaily(
                loja_id=loja_id,
                customer_id="1112223333",
                campaign_id="c1",
                date=datetime(2026, 7, 5).date(),
                impressions=200,
                clicks=20,
                cost_micros=4_000_000,
                conversions=Decimal("2"),
                conversions_value=Decimal("80"),
                currency_code="BRL",
            )
        )
        acct = (
            db.query(GoogleAdsAccount)
            .filter(GoogleAdsAccount.loja_id == loja_id)
            .first()
        )
        if acct is not None:
            acct.selected = True
            acct.is_manager = False
        db.commit()

    ok = client.get(
        f"/control/v1/internal/lojas/{loja_id}/aquisicao-resumo",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
        headers=headers,
    )
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["google_disponivel"] is True
    assert payload["google"] is not None
    assert payload["google"]["cost"] == "4.00"
    assert payload["google"]["cpl"] == "2.00"
    assert payload["google"]["roas"] == "20.00"
    assert "secret" not in str(payload).lower()
    assert "ciphertext" not in str(payload).lower()
