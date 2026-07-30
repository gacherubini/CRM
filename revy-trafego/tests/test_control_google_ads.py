"""Fase 4A — fundação Google Ads: ports, OAuth state e conexão cifrada."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.auth import hash_senha
from app.config import settings
from app.control.google_ads import (
    CONNECTION_STATUS_CONNECTED,
    CONNECTION_STATUS_REVOKED,
    FakeGoogleAdsReadPort,
    FakeGoogleDataManagerPort,
    FakeGoogleAdsTokenExchanger,
    GOOGLE_ADS_SCOPES,
    GoogleAdsAccount,
    GoogleAdsConnectionControl,
    GoogleAdsConnectionNotFound,
    GoogleAdsMetricRow,
    GoogleAdsOAuthStateInvalid,
    OAuthTokenBundle,
)
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    CreateStore,
    StoreNotFound,
    StoreRef,
)
from app.cripto import decifrar
from app.db import SessionLocal
from app.models import (
    GestorRevy,
    GoogleAdsConnection,
    GoogleAdsOAuthState,
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


def _control(
    *,
    exchanger: FakeGoogleAdsTokenExchanger | None = None,
    now: datetime | None = None,
) -> GoogleAdsConnectionControl:
    clock = now or datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
    return GoogleAdsConnectionControl(
        SessionLocal,
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="https://control.revy.test/control/v1/google-ads/oauth/callback",
        token_exchanger=exchanger
        or FakeGoogleAdsTokenExchanger(
            default_bundle=OAuthTokenBundle(
                refresh_token="rt-secret-value",
                access_token="at-value",
                scopes=GOOGLE_ADS_SCOPES,
            )
        ),
        now=lambda: clock,
    )


def _create_store(slug: str = "loja-google-ads") -> str:
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Google", slug=slug),
    )
    return store.id


def test_fake_read_port_list_accounts_and_metrics_stub():
    port = FakeGoogleAdsReadPort(
        accounts=[
            GoogleAdsAccount(
                customer_id="1234567890",
                descriptive_name="Loja Anunciante",
                is_manager=False,
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
            ),
            GoogleAdsMetricRow(
                customer_id="1234567890",
                campaign_id="99",
                date="2026-08-01",
                impressions=1,
            ),
        ],
    )
    accounts = port.list_accounts("rt")
    assert len(accounts) == 1
    assert accounts[0].customer_id == "1234567890"
    assert accounts[0].is_manager is False

    rows = port.fetch_metrics(
        refresh_token="rt",
        customer_id="1234567890",
        login_customer_id=None,
        date_from="2026-07-01",
        date_to="2026-07-31",
    )
    assert len(rows) == 1
    assert rows[0].cost_micros == 1_500_000
    assert port.list_accounts_calls == ["rt"]


def test_fake_data_manager_ingest_stub():
    port = FakeGoogleDataManagerPort(next_request_id="req-42")
    result = port.ingest(
        refresh_token="rt",
        customer_id="123",
        events=[{"transaction_id": "revy:1:venda:a"}],
    )
    assert result.request_id == "req-42"
    assert result.accepted == 1
    assert result.rejected == 0
    assert port.ingests[0]["customer_id"] == "123"


def test_start_oauth_gera_state_e_auth_url_offline():
    loja_id = _create_store()
    admin = _admin_actor()
    control = _control()

    result = control.start_oauth(admin, StoreRef(id=loja_id))

    assert result.state
    assert "accounts.google.com" in result.auth_url
    parsed = urlparse(result.auth_url)
    query = parse_qs(parsed.query)
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["response_type"] == ["code"]
    assert query["state"] == [result.state]
    assert "adwords" in query["scope"][0]
    assert "datamanager" in query["scope"][0]
    assert query["client_id"] == ["test-client-id"]

    with SessionLocal() as db:
        row = (
            db.query(GoogleAdsOAuthState)
            .filter(GoogleAdsOAuthState.state == result.state)
            .one()
        )
        assert row.loja_id == loja_id
        assert row.actor_id == admin.id


def test_complete_oauth_cifra_refresh_token_e_nao_expoe_em_view():
    loja_id = _create_store("loja-oauth-complete")
    admin = _admin_actor()
    control = _control()
    started = control.start_oauth(admin, StoreRef(id=loja_id))

    view = control.complete_oauth(
        state=started.state,
        code="auth-code-1",
        customer_id="111-222-3333",
        login_customer_id="9998887777",
    )

    assert view.status == CONNECTION_STATUS_CONNECTED
    assert view.customer_id == "1112223333"
    assert view.login_customer_id == "9998887777"
    assert view.has_refresh_token is True
    assert "rt-secret-value" not in view.__dict__.values()
    payload = view.__dict__
    assert "refresh_token" not in payload
    assert "refresh_token_ciphertext" not in payload

    with SessionLocal() as db:
        row = (
            db.query(GoogleAdsConnection)
            .filter(GoogleAdsConnection.loja_id == loja_id)
            .one()
        )
        assert row.refresh_token_ciphertext
        assert "rt-secret-value" not in row.refresh_token_ciphertext
        assert decifrar(row.refresh_token_ciphertext) == "rt-secret-value"
        # state consumido (one-time)
        assert (
            db.query(GoogleAdsOAuthState)
            .filter(GoogleAdsOAuthState.state == started.state)
            .count()
            == 0
        )

    plain = control.decrypt_refresh_token(view.id)
    assert plain == "rt-secret-value"


def test_complete_oauth_rejeita_state_invalido_e_expirado():
    loja_id = _create_store("loja-oauth-invalid")
    admin = _admin_actor()
    fixed = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
    control = _control(now=fixed)

    with pytest.raises(GoogleAdsOAuthStateInvalid):
        control.complete_oauth(state="nao-existe", code="x")

    started = control.start_oauth(admin, StoreRef(id=loja_id))
    expired_control = GoogleAdsConnectionControl(
        SessionLocal,
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="https://control.revy.test/callback",
        token_exchanger=FakeGoogleAdsTokenExchanger(
            default_bundle=OAuthTokenBundle(
                refresh_token="rt",
                access_token="at",
            )
        ),
        now=lambda: fixed + timedelta(hours=1),
    )
    with pytest.raises(GoogleAdsOAuthStateInvalid):
        expired_control.complete_oauth(state=started.state, code="code")


def test_disconnect_revoga_e_apaga_token():
    loja_id = _create_store("loja-oauth-disconnect")
    admin = _admin_actor()
    control = _control()
    started = control.start_oauth(admin, StoreRef(id=loja_id))
    control.complete_oauth(state=started.state, code="c1")

    view = control.disconnect(admin, StoreRef(id=loja_id))
    assert view.status == CONNECTION_STATUS_REVOKED
    assert view.has_refresh_token is False
    assert control.decrypt_refresh_token(view.id) is None

    with SessionLocal() as db:
        row = (
            db.query(GoogleAdsConnection)
            .filter(GoogleAdsConnection.loja_id == loja_id)
            .one()
        )
        assert row.refresh_token_ciphertext is None
        assert row.status == CONNECTION_STATUS_REVOKED


def test_get_inexistente_e_colaborador_nao_desconecta():
    loja_id = _create_store("loja-oauth-rbac")
    admin = _admin_actor()
    control = _control()

    with pytest.raises(GoogleAdsConnectionNotFound):
        control.get(admin, StoreRef(id=loja_id))

    with SessionLocal() as db:
        collab = GestorRevy(
            email="colab-gads@revy.local",
            nome="Colaborador",
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

    started = control.start_oauth(admin, StoreRef(id=loja_id))
    control.complete_oauth(state=started.state, code="c-rbac")

    collab_actor = Actor(
        id=collab_id,
        email="colab-gads@revy.local",
        name="Colaborador",
        role="gestor",
    )
    # colaborador pode ver
    seen = control.get(collab_actor, StoreRef(id=loja_id))
    assert seen.has_refresh_token is True
    # mas não desconecta
    with pytest.raises(AccessDenied):
        control.disconnect(collab_actor, StoreRef(id=loja_id))


def test_gestor_sem_vinculo_nao_ve_conexao():
    loja_id = _create_store("loja-oauth-isolation")
    admin = _admin_actor()
    control = _control()
    started = control.start_oauth(admin, StoreRef(id=loja_id))
    control.complete_oauth(state=started.state, code="c-iso")

    with SessionLocal() as db:
        outsider = GestorRevy(
            email="outsider-gads@revy.local",
            nome="Outsider",
            senha_hash=hash_senha("secret-teste"),
            papel="gestor",
            ativo=True,
        )
        db.add(outsider)
        db.commit()
        outsider_id = outsider.id

    outsider_actor = Actor(
        id=outsider_id,
        email="outsider-gads@revy.local",
        name="Outsider",
        role="gestor",
    )
    with pytest.raises(StoreNotFound):
        control.get(outsider_actor, StoreRef(id=loja_id))


def test_ports_nao_tem_mutate():
    """Contrato de fronteira: ports de leitura/ingest não expõem Mutate."""
    from app.control.google_ads_http import (
        HttpGoogleAdsReadPort,
        HttpGoogleDataManagerPort,
    )

    for cls in (
        FakeGoogleAdsReadPort,
        FakeGoogleDataManagerPort,
        HttpGoogleAdsReadPort,
        HttpGoogleDataManagerPort,
    ):
        methods = {name for name in dir(cls) if not name.startswith("_")}
        assert not any("mutate" in name.lower() for name in methods)


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


def _http_create_store(client, slug: str) -> dict:
    response = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja HTTP Google", "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


def test_http_oauth_flow_e_flags(client, monkeypatch):
    _enable_flags(monkeypatch, control=True, google=False)
    _login_admin(client)
    store = _http_create_store(client, "loja-gads-flag-off")
    blocked = client.post(
        f"/control/v1/lojas/{store['id']}/google-ads/oauth/start",
    )
    assert blocked.status_code == 404

    _enable_flags(monkeypatch, control=True, google=True)
    started = client.post(
        f"/control/v1/lojas/{store['id']}/google-ads/oauth/start",
    )
    assert started.status_code == 200
    body = started.json()
    assert body["state"]
    assert "accounts.google.com" in body["auth_url"]
    assert "offline" in body["auth_url"]

    missing = client.get(
        f"/control/v1/lojas/{store['id']}/google-ads/connection",
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "google_ads_connection_not_found"

    callback = client.get(
        "/control/v1/google-ads/oauth/callback",
        params={"state": body["state"], "code": "http-auth-code"},
    )
    assert callback.status_code == 200
    conn = callback.json()
    assert conn["status"] == CONNECTION_STATUS_CONNECTED
    assert conn["has_refresh_token"] is True
    assert "refresh_token" not in conn
    assert "ciphertext" not in str(conn).lower()
    assert "test-refresh-token" not in str(conn)

    listed = client.get(
        f"/control/v1/lojas/{store['id']}/google-ads/connection",
    )
    assert listed.status_code == 200
    assert listed.json()["id"] == conn["id"]
    assert listed.json()["has_refresh_token"] is True

    # state inválido / reutilizado
    again = client.get(
        "/control/v1/google-ads/oauth/callback",
        params={"state": body["state"], "code": "other"},
    )
    assert again.status_code == 400
    assert again.json()["detail"]["code"] == "google_ads_oauth_state_invalid"

    bogus = client.get(
        "/control/v1/google-ads/oauth/callback",
        params={"state": "zzz-invalido", "code": "x"},
    )
    assert bogus.status_code == 400

    deleted = client.delete(
        f"/control/v1/lojas/{store['id']}/google-ads/connection",
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == CONNECTION_STATUS_REVOKED
    assert deleted.json()["has_refresh_token"] is False


def test_http_exige_autenticacao_nas_rotas_protegidas(client, monkeypatch):
    _enable_flags(monkeypatch)
    response = client.post(
        "/control/v1/lojas/qualquer/google-ads/oauth/start",
    )
    assert response.status_code == 401
