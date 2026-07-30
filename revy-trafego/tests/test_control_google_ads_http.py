"""Adapters HTTP Google Ads / Data Manager — mocks httpx, sem rede real."""
from __future__ import annotations

from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings, settings
from app.control.google_ads import (
    FakeGoogleAdsReadPort,
    FakeGoogleAdsTokenExchanger,
    FakeGoogleDataManagerPort,
    GoogleAdsTokenExchangeError,
)
from app.control.google_ads_http import (
    GoogleAdsApiError,
    GoogleDataManagerApiError,
    HttpGoogleAdsReadPort,
    HttpGoogleAdsTokenExchanger,
    HttpGoogleDataManagerPort,
    build_data_manager_ingest_request,
    build_google_ads_ports,
    google_ads_credentials_configured,
)


def _settings_with(
    *,
    client_id: str = "cid",
    client_secret: str = "csecret",
    developer_token: str = "devtok",
    redirect_uri: str = "https://control.revy.test/cb",
    **extra: object,
) -> Settings:
    return replace(
        settings,
        google_ads_oauth_client_id=client_id,
        google_ads_oauth_client_secret=client_secret,
        google_ads_oauth_redirect_uri=redirect_uri,
        google_ads_developer_token=developer_token,
        **extra,
    )


# --- factory ---------------------------------------------------------------


def test_factory_sem_credenciais_usa_fakes():
    ports = build_google_ads_ports(
        _settings_with(client_id="", client_secret="", developer_token="")
    )
    assert ports.using_http is False
    assert isinstance(ports.token_exchanger, FakeGoogleAdsTokenExchanger)
    assert isinstance(ports.read_port, FakeGoogleAdsReadPort)
    assert isinstance(ports.data_manager_port, FakeGoogleDataManagerPort)


def test_factory_sem_developer_token_usa_fakes():
    ports = build_google_ads_ports(
        _settings_with(developer_token="")
    )
    assert ports.using_http is False


def test_factory_com_credenciais_usa_http():
    ports = build_google_ads_ports(_settings_with())
    assert ports.using_http is True
    assert isinstance(ports.token_exchanger, HttpGoogleAdsTokenExchanger)
    assert isinstance(ports.read_port, HttpGoogleAdsReadPort)
    assert isinstance(ports.data_manager_port, HttpGoogleDataManagerPort)


def test_factory_force_fake_ignora_credenciais():
    ports = build_google_ads_ports(_settings_with(), force_fake=True)
    assert ports.using_http is False


def test_credentials_configured_helper():
    assert google_ads_credentials_configured(
        client_id="a", client_secret="b", developer_token="c"
    )
    assert not google_ads_credentials_configured(
        client_id="a", client_secret="", developer_token="c"
    )


def test_http_ports_nao_tem_mutate():
    for cls in (
        HttpGoogleAdsReadPort,
        HttpGoogleDataManagerPort,
        HttpGoogleAdsTokenExchanger,
    ):
        methods = {name for name in dir(cls) if not name.startswith("_")}
        assert not any("mutate" in name.lower() for name in methods)


# --- token exchanger -------------------------------------------------------


def test_token_exchanger_sucesso():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        body = parse_qs(request.content.decode())
        captured["body"] = {k: v[0] for k, v in body.items()}
        # não vazar secrets nos asserts de log — só validamos presença
        assert body["grant_type"] == ["authorization_code"]
        assert body["code"] == ["auth-code-1"]
        return httpx.Response(
            200,
            json={
                "refresh_token": "rt-real",
                "access_token": "at-real",
                "expires_in": 3600,
                "scope": (
                    "https://www.googleapis.com/auth/adwords "
                    "https://www.googleapis.com/auth/datamanager"
                ),
            },
        )

    exchanger = HttpGoogleAdsTokenExchanger(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="https://control.revy.test/cb",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    bundle = exchanger.exchange("auth-code-1")
    assert bundle.refresh_token == "rt-real"
    assert bundle.access_token == "at-real"
    assert bundle.expires_in == 3600
    assert captured["body"]["client_id"] == "cid"


def test_token_exchanger_http_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    exchanger = HttpGoogleAdsTokenExchanger(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="https://control.revy.test/cb",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(GoogleAdsTokenExchangeError):
        exchanger.exchange("bad-code")


def test_token_exchanger_sem_refresh_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "only-access"})

    exchanger = HttpGoogleAdsTokenExchanger(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="https://control.revy.test/cb",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(GoogleAdsTokenExchangeError, match="refresh token"):
        exchanger.exchange("code")


# --- read port -------------------------------------------------------------


def _read_port(transport: httpx.BaseTransport) -> HttpGoogleAdsReadPort:
    return HttpGoogleAdsReadPort(
        client_id="cid",
        client_secret="csecret",
        developer_token="devtok",
        api_version="v19",
        ads_base_url="https://googleads.test",
        token_url="https://oauth.test/token",
        transport=transport,
    )


def test_read_port_list_accounts_e_hierarchy():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(f"{request.method} {path}")
        # secrets nunca no path
        assert "rt-secret" not in path
        assert "devtok" not in path

        if path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at-1"})

        if path.endswith("customers:listAccessibleCustomers"):
            assert request.headers.get("developer-token") == "devtok"
            assert request.headers.get("Authorization") == "Bearer at-1"
            return httpx.Response(
                200,
                json={"resourceNames": ["customers/5556667777"]},
            )

        if "googleAds:search" in path and "5556667777" in path:
            import json

            payload = json.loads(request.content.decode() or "{}")
            query = payload.get("query") or ""
            if "customer_client" in query:
                assert request.headers.get("login-customer-id") == "5556667777"
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "customerClient": {
                                    "id": "1112223333",
                                    "descriptiveName": "Loja Anunciante",
                                    "manager": False,
                                    "currencyCode": "BRL",
                                    "timeZone": "America/Sao_Paulo",
                                    "clientCustomer": "customers/1112223333",
                                    "status": "ENABLED",
                                }
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "customer": {
                                "id": "5556667777",
                                "descriptiveName": "Manager Revy",
                                "manager": True,
                                "currencyCode": "BRL",
                                "timeZone": "America/Sao_Paulo",
                            }
                        }
                    ]
                },
            )

        return httpx.Response(404, json={"error": "unexpected " + path})

    port = _read_port(httpx.MockTransport(handler))
    accounts = port.list_accounts("rt-secret")
    by_id = {a.customer_id: a for a in accounts}
    assert "5556667777" in by_id
    assert by_id["5556667777"].is_manager is True
    assert "1112223333" in by_id
    assert by_id["1112223333"].is_manager is False
    assert by_id["1112223333"].login_customer_id == "5556667777"
    assert by_id["1112223333"].currency_code == "BRL"
    # token exchange + list + manager detail + hierarchy
    assert any("listAccessibleCustomers" in c for c in calls)


def test_read_port_fetch_metrics_sucesso():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at-m"})
        if "googleAds:search" in request.url.path:
            assert request.headers.get("login-customer-id") == "5556667777"
            assert "1112223333" in request.url.path
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "campaign": {"id": "99", "name": "Camp A"},
                            "segments": {"date": "2026-07-05"},
                            "metrics": {
                                "impressions": "1000",
                                "clicks": "50",
                                "costMicros": "2500000",
                                "conversions": 3.5,
                                "conversionsValue": 120.0,
                            },
                        }
                    ]
                },
            )
        return httpx.Response(500, json={})

    port = _read_port(httpx.MockTransport(handler))
    rows = port.fetch_metrics(
        refresh_token="rt",
        customer_id="111-222-3333",
        login_customer_id="555-666-7777",
        date_from="2026-07-01",
        date_to="2026-07-31",
    )
    assert len(rows) == 1
    assert rows[0].customer_id == "1112223333"
    assert rows[0].campaign_id == "99"
    assert rows[0].impressions == 1000
    assert rows[0].cost_micros == 2_500_000
    assert rows[0].conversions == 3.5


def test_read_port_list_conversion_actions_sucesso():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at-ca"})
        if "googleAds:search" in request.url.path:
            body = request.read().decode("utf-8")
            assert "conversion_action" in body
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "conversionAction": {
                                "resourceName": (
                                    "customers/1112223333/conversionActions/42"
                                ),
                                "id": "42",
                                "name": "Lead form",
                                "type": "WEBPAGE",
                                "status": "ENABLED",
                                "category": "SUBMIT_LEAD_FORM",
                                "primaryForGoal": True,
                            }
                        }
                    ]
                },
            )
        return httpx.Response(500, json={})

    port = _read_port(httpx.MockTransport(handler))
    actions = port.list_conversion_actions(
        refresh_token="rt",
        customer_id="1112223333",
        login_customer_id="5556667777",
    )
    assert len(actions) == 1
    assert actions[0].id == "42"
    assert actions[0].name == "Lead form"
    assert actions[0].resource_name.endswith("/conversionActions/42")
    assert actions[0].primary_for_goal is True


def test_read_port_401_no_access_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    port = _read_port(httpx.MockTransport(handler))
    with pytest.raises(GoogleAdsApiError, match="401"):
        port.list_accounts("rt-expired")


def test_read_port_401_list_accessible():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at"})
        return httpx.Response(401, json={"error": "unauthorized"})

    port = _read_port(httpx.MockTransport(handler))
    with pytest.raises(GoogleAdsApiError, match="401"):
        port.list_accounts("rt")


# --- data manager ----------------------------------------------------------


def test_build_data_manager_ingest_request_shape():
    body = build_data_manager_ingest_request(
        customer_id="1112223333",
        events=[
            {
                "transaction_id": "revy:loja:venda:1",
                "event_source": "OTHER",
                "event_timestamp": "2026-07-29T12:00:00+00:00",
                "conversion_action": "customers/1112223333/conversionActions/987",
                "ad_identifiers": {"gclid": "GCLID_X"},
                "currency": "BRL",
                "conversion_value": "150.50",
                "consent": {"ad_user_data": "GRANTED"},
                "user_data": {
                    "email_hash": "abc123",
                    "phone_hash": "def456",
                },
            }
        ],
        validate_only=True,
    )
    assert body["validateOnly"] is True
    assert body["encoding"] == "HEX"
    assert len(body["destinations"]) == 1
    dest = body["destinations"][0]
    assert dest["operatingAccount"]["accountId"] == "1112223333"
    assert dest["productDestinationId"] == "987"
    assert dest["reference"] == "dest_0"
    ev = body["events"][0]
    assert ev["transactionId"] == "revy:loja:venda:1"
    assert ev["adIdentifiers"]["gclid"] == "GCLID_X"
    assert ev["conversionValue"] == 150.5
    assert ev["destinationReferences"] == ["dest_0"]
    assert ev["userData"]["userIdentifiers"][0]["emailAddress"] == "abc123"
    assert ev["consent"]["adUserData"] == "GRANTED"


def test_data_manager_ingest_sucesso():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at-dm"})
        if request.url.path.endswith("/v1/events:ingest"):
            import json

            captured["body"] = json.loads(request.content.decode())
            assert request.headers.get("Authorization") == "Bearer at-dm"
            # developer-token NÃO é exigido pela Data Manager API
            assert "developer-token" not in {
                k.lower() for k in request.headers.keys()
            }
            return httpx.Response(200, json={"requestId": "req-dm-1"})
        return httpx.Response(404, json={})

    port = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    result = port.ingest(
        refresh_token="rt",
        customer_id="1112223333",
        events=[
            {
                "transaction_id": "tx-1",
                "event_source": "OTHER",
                "event_timestamp": "2026-07-29T12:00:00+00:00",
                "conversion_action": "customers/1112223333/conversionActions/1",
                "ad_identifiers": {"gclid": "G"},
                "currency": "BRL",
            }
        ],
    )
    assert result.request_id == "req-dm-1"
    assert result.accepted == 1
    assert result.rejected == 0
    assert captured["body"]["events"][0]["transactionId"] == "tx-1"


def test_data_manager_ingest_401():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at"})
        return httpx.Response(401, json={"error": "unauthorized"})

    port = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(GoogleDataManagerApiError, match="401"):
        port.ingest(
            refresh_token="rt",
            customer_id="1",
            events=[{"transaction_id": "t", "conversion_action": "1"}],
        )


def test_data_manager_empty_events():
    port = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    result = port.ingest(refresh_token="rt", customer_id="1", events=[])
    assert result.accepted == 0
    assert result.request_id == ""


def test_data_manager_retrieve_status_success():
    from app.control.google_ads import DM_STATUS_SUCCESS

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at-status"})
        if "requestStatus:retrieve" in str(request.url):
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            qs = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
            assert qs.get("requestId") == ["req-xyz"]
            assert request.method == "GET"
            # developer-token NÃO deve aparecer
            assert "developer-token" not in {
                k.lower() for k in request.headers.keys()
            }
            return httpx.Response(
                200,
                json={
                    "requestStatusPerDestination": [
                        {"requestStatus": "SUCCESS"}
                    ]
                },
            )
        return httpx.Response(404, json={})

    port = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    result = port.retrieve_status(
        refresh_token="rt-secret-never-log",
        request_id="req-xyz",
    )
    assert result.status == DM_STATUS_SUCCESS
    assert result.request_id == "req-xyz"
    assert captured["auth"] == "Bearer at-status"
    assert "requestStatus:retrieve" in str(captured["url"])


def test_data_manager_retrieve_status_failed_and_pending():
    from app.control.google_ads import (
        DM_STATUS_FAILURE,
        DM_STATUS_PENDING,
    )

    def make_handler(api_status: str, extra: dict | None = None):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "at"})
            body: dict = {
                "requestStatusPerDestination": [
                    {
                        "requestStatus": api_status,
                        **(extra or {}),
                    }
                ]
            }
            return httpx.Response(200, json=body)

        return handler

    port_fail = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(
            make_handler(
                "FAILED",
                {
                    "errorInfo": {
                        "errorCounts": [
                            {
                                "reason": "PROCESSING_ERROR_REASON_INVALID_GCLID",
                                "recordCount": "1",
                            }
                        ]
                    }
                },
            )
        ),
    )
    failed = port_fail.retrieve_status(refresh_token="rt", request_id="r1")
    assert failed.status == DM_STATUS_FAILURE
    assert "INVALID_GCLID" in (failed.error_summary or "")

    port_pend = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(make_handler("PROCESSING")),
    )
    pending = port_pend.retrieve_status(refresh_token="rt", request_id="r2")
    assert pending.status == DM_STATUS_PENDING


def test_data_manager_retrieve_status_soft_fail_unknown():
    from app.control.google_ads import DM_STATUS_UNKNOWN

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at"})
        return httpx.Response(503, json={"error": "unavailable"})

    port = HttpGoogleDataManagerPort(
        client_id="cid",
        client_secret="csecret",
        base_url="https://datamanager.test",
        token_url="https://oauth.test/token",
        transport=httpx.MockTransport(handler),
    )
    result = port.retrieve_status(refresh_token="rt", request_id="req-soft")
    assert result.status == DM_STATUS_UNKNOWN
    assert result.request_id == "req-soft"
    assert "503" in (result.error_summary or "")
