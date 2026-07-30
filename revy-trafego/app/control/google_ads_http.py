"""HTTP adapters reais para Google Ads API + Data Manager API (somente leitura/ingest).

Sem Mutate de campanhas. Tokens e developer token nunca devem ser logados.
Fakes continuam o default em testes / quando credenciais env faltam.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from app.control.google_ads import (
    FakeGoogleAdsReadPort,
    FakeGoogleAdsTokenExchanger,
    FakeGoogleDataManagerPort,
    GoogleAdsAccount,
    GoogleAdsMetricRow,
    GoogleAdsTokenExchangeError,
    GoogleDataManagerIngestResult,
    GoogleDataManagerStatusResult,
    GoogleAdsReadPort,
    GoogleAdsTokenExchanger,
    GoogleDataManagerPort,
    OAuthTokenBundle,
    GOOGLE_ADS_SCOPES,
    DM_STATUS_FAILURE,
    DM_STATUS_PARTIAL_SUCCESS,
    DM_STATUS_PENDING,
    DM_STATUS_SUCCESS,
    DM_STATUS_UNKNOWN,
    _normalize_customer_id,
)
from app.control.types import ControlError

logger = logging.getLogger(__name__)

GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ADS_API_BASE = "https://googleads.googleapis.com"
DATA_MANAGER_API_BASE = "https://datamanager.googleapis.com"
DEFAULT_GOOGLE_ADS_API_VERSION = "v19"

_RESOURCE_CUSTOMER_RE = re.compile(r"customers/(\d+)", re.IGNORECASE)
_CONVERSION_ACTION_ID_RE = re.compile(
    r"conversionActions/(\d+)", re.IGNORECASE
)


class GoogleAdsApiError(ControlError):
    """Falha HTTP/API na Google Ads API (leitura)."""


class GoogleDataManagerApiError(ControlError):
    """Falha HTTP/API na Data Manager API (ingest)."""


@dataclass(frozen=True)
class GoogleAdsPorts:
    """Pacote de ports injetáveis + flag se adapters HTTP reais estão ativos."""

    token_exchanger: GoogleAdsTokenExchanger
    read_port: GoogleAdsReadPort
    data_manager_port: GoogleDataManagerPort
    using_http: bool


def google_ads_credentials_configured(
    *,
    client_id: str,
    client_secret: str,
    developer_token: str,
) -> bool:
    return bool(
        (client_id or "").strip()
        and (client_secret or "").strip()
        and (developer_token or "").strip()
    )


def build_google_ads_ports(
    settings: Any,
    *,
    force_fake: bool = False,
    timeout: float = 30.0,
) -> GoogleAdsPorts:
    """Monta ports HTTP quando OAuth + developer token existem; senão Fake*.

    Em testes (force_fake=True ou credenciais ausentes) retorna fakes.
    Flags GOOGLE_ADS_SYNC_ENABLED / GOOGLE_CONVERSIONS_ENABLED controlam
    rotas/jobs no web layer — este factory só decide o transporte.
    """
    client_id = str(
        getattr(settings, "google_ads_oauth_client_id", "") or ""
    ).strip()
    client_secret = str(
        getattr(settings, "google_ads_oauth_client_secret", "") or ""
    ).strip()
    redirect_uri = str(
        getattr(settings, "google_ads_oauth_redirect_uri", "") or ""
    ).strip()
    developer_token = str(
        getattr(settings, "google_ads_developer_token", "") or ""
    ).strip()
    api_version = str(
        getattr(settings, "google_ads_api_version", "") or DEFAULT_GOOGLE_ADS_API_VERSION
    ).strip() or DEFAULT_GOOGLE_ADS_API_VERSION
    data_manager_base = str(
        getattr(settings, "google_data_manager_base_url", "") or DATA_MANAGER_API_BASE
    ).strip() or DATA_MANAGER_API_BASE
    ads_base = str(
        getattr(settings, "google_ads_api_base_url", "") or GOOGLE_ADS_API_BASE
    ).strip() or GOOGLE_ADS_API_BASE
    token_url = str(
        getattr(settings, "google_oauth_token_url", "") or GOOGLE_OAUTH_TOKEN_URL
    ).strip() or GOOGLE_OAUTH_TOKEN_URL

    if force_fake or not google_ads_credentials_configured(
        client_id=client_id,
        client_secret=client_secret,
        developer_token=developer_token,
    ):
        return GoogleAdsPorts(
            token_exchanger=FakeGoogleAdsTokenExchanger(
                default_bundle=OAuthTokenBundle(
                    refresh_token="fake-refresh-token",
                    access_token="fake-access-token",
                    scopes=GOOGLE_ADS_SCOPES,
                )
            ),
            read_port=FakeGoogleAdsReadPort(),
            data_manager_port=FakeGoogleDataManagerPort(),
            using_http=False,
        )

    exchanger = HttpGoogleAdsTokenExchanger(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        token_url=token_url,
        timeout=timeout,
    )
    read_port = HttpGoogleAdsReadPort(
        client_id=client_id,
        client_secret=client_secret,
        developer_token=developer_token,
        api_version=api_version,
        ads_base_url=ads_base,
        token_url=token_url,
        timeout=timeout,
    )
    data_manager = HttpGoogleDataManagerPort(
        client_id=client_id,
        client_secret=client_secret,
        base_url=data_manager_base,
        token_url=token_url,
        timeout=timeout,
    )
    return GoogleAdsPorts(
        token_exchanger=exchanger,
        read_port=read_port,
        data_manager_port=data_manager,
        using_http=True,
    )


@dataclass
class HttpGoogleAdsTokenExchanger:
    """Troca authorization code por tokens via OAuth2 token endpoint."""

    client_id: str
    client_secret: str
    redirect_uri: str
    token_url: str = GOOGLE_OAUTH_TOKEN_URL
    timeout: float = 30.0
    transport: httpx.BaseTransport | None = None

    def exchange(self, code: str) -> OAuthTokenBundle:
        code_value = (code or "").strip()
        if not code_value:
            raise GoogleAdsTokenExchangeError("authorization code ausente")

        data = {
            "grant_type": "authorization_code",
            "code": code_value,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.post(self.token_url, data=data)
        except httpx.HTTPError as exc:
            logger.warning("google_ads oauth token exchange request failed")
            raise GoogleAdsTokenExchangeError(
                "falha de rede ao trocar authorization code"
            ) from exc

        if response.status_code >= 400:
            # Nunca logar body (pode conter code/token/secret).
            logger.warning(
                "google_ads oauth token exchange HTTP %s",
                response.status_code,
            )
            raise GoogleAdsTokenExchangeError(
                f"troca OAuth rejeitada (HTTP {response.status_code})"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleAdsTokenExchangeError(
                "resposta OAuth inválida (não JSON)"
            ) from exc

        refresh = str(payload.get("refresh_token") or "").strip()
        access = str(payload.get("access_token") or "").strip()
        if not refresh:
            raise GoogleAdsTokenExchangeError(
                "resposta OAuth sem refresh token"
            )
        if not access:
            raise GoogleAdsTokenExchangeError(
                "resposta OAuth sem access token"
            )

        scope_raw = str(payload.get("scope") or "").strip()
        scopes = (
            tuple(s for s in scope_raw.split() if s)
            if scope_raw
            else GOOGLE_ADS_SCOPES
        )
        expires_in = payload.get("expires_in")
        expires: int | None
        try:
            expires = int(expires_in) if expires_in is not None else None
        except (TypeError, ValueError):
            expires = None

        return OAuthTokenBundle(
            refresh_token=refresh,
            access_token=access,
            scopes=scopes,
            expires_in=expires,
        )


@dataclass
class HttpGoogleAdsReadPort:
    """Leitura Google Ads API REST (ListAccessibleCustomers + GAQL Search).

    Sem métodos Mutate. Usa developer-token e opcionalmente login-customer-id.
    """

    client_id: str
    client_secret: str
    developer_token: str
    api_version: str = DEFAULT_GOOGLE_ADS_API_VERSION
    ads_base_url: str = GOOGLE_ADS_API_BASE
    token_url: str = GOOGLE_OAUTH_TOKEN_URL
    timeout: float = 30.0
    transport: httpx.BaseTransport | None = None
    page_size: int = 1000

    def list_accounts(self, refresh_token: str) -> Sequence[GoogleAdsAccount]:
        access = self._access_token(refresh_token)
        resource_names = self._list_accessible_customer_resource_names(access)
        accounts: list[GoogleAdsAccount] = []
        seen: set[str] = set()

        for resource in resource_names:
            customer_id = _customer_id_from_resource(resource)
            if not customer_id:
                continue
            detail = self._fetch_customer_detail(
                access_token=access,
                customer_id=customer_id,
                login_customer_id=None,
            )
            if detail is None:
                # Conta inacessível sem login-customer-id; registra mínima.
                detail = GoogleAdsAccount(
                    customer_id=customer_id,
                    descriptive_name=customer_id,
                    is_manager=False,
                    login_customer_id=None,
                )
            if customer_id not in seen:
                accounts.append(detail)
                seen.add(customer_id)

            if detail.is_manager:
                children = self._list_customer_clients(
                    access_token=access,
                    manager_customer_id=customer_id,
                )
                for child in children:
                    if child.customer_id in seen:
                        continue
                    accounts.append(child)
                    seen.add(child.customer_id)

        return tuple(accounts)

    def fetch_metrics(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str | None,
        date_from: str,
        date_to: str,
    ) -> Sequence[GoogleAdsMetricRow]:
        cid = _normalize_customer_id(customer_id) or customer_id
        login = _normalize_customer_id(login_customer_id)
        access = self._access_token(refresh_token)
        query = (
            "SELECT "
            "segments.date, "
            "campaign.id, "
            "campaign.name, "
            "campaign.status, "
            "metrics.impressions, "
            "metrics.clicks, "
            "metrics.cost_micros, "
            "metrics.conversions, "
            "metrics.conversions_value "
            "FROM campaign "
            f"WHERE segments.date BETWEEN '{_safe_date(date_from)}' "
            f"AND '{_safe_date(date_to)}' "
            "AND campaign.status != 'REMOVED'"
        )
        rows_raw = self._search(
            access_token=access,
            customer_id=cid,
            login_customer_id=login,
            query=query,
        )
        out: list[GoogleAdsMetricRow] = []
        for item in rows_raw:
            campaign = item.get("campaign") or {}
            metrics = item.get("metrics") or {}
            segments = item.get("segments") or {}
            campaign_id = str(campaign.get("id") or "").strip()
            day = str(segments.get("date") or "").strip()
            if not campaign_id or not day:
                continue
            out.append(
                GoogleAdsMetricRow(
                    customer_id=cid,
                    campaign_id=campaign_id,
                    date=day,
                    impressions=_as_int(metrics.get("impressions")),
                    clicks=_as_int(metrics.get("clicks")),
                    cost_micros=_as_int(metrics.get("costMicros") or metrics.get("cost_micros")),
                    conversions=_as_float(
                        metrics.get("conversions")
                    ),
                    conversions_value=_as_float(
                        metrics.get("conversionsValue")
                        or metrics.get("conversions_value")
                    ),
                )
            )
        return tuple(out)

    # --- internals ---------------------------------------------------------

    def _access_token(self, refresh_token: str) -> str:
        token = (refresh_token or "").strip()
        if not token:
            raise GoogleAdsApiError("refresh token ausente")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.post(self.token_url, data=data)
        except httpx.HTTPError as exc:
            logger.warning("google_ads access_token request failed")
            raise GoogleAdsApiError(
                "falha de rede ao renovar access token"
            ) from exc
        if response.status_code == 401:
            raise GoogleAdsApiError("OAuth rejeitado (401) ao renovar token")
        if response.status_code >= 400:
            logger.warning(
                "google_ads access_token HTTP %s", response.status_code
            )
            raise GoogleAdsApiError(
                f"renovação de access token falhou (HTTP {response.status_code})"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleAdsApiError(
                "resposta de access token inválida"
            ) from exc
        access = str(payload.get("access_token") or "").strip()
        if not access:
            raise GoogleAdsApiError("resposta sem access_token")
        return access

    def _headers(
        self,
        access_token: str,
        *,
        login_customer_id: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        login = _normalize_customer_id(login_customer_id)
        if login:
            headers["login-customer-id"] = login
        return headers

    def _api_url(self, path: str) -> str:
        base = self.ads_base_url.rstrip("/") + "/"
        version = self.api_version.strip("/")
        rel = f"{version}/{path.lstrip('/')}"
        return urljoin(base, rel)

    def _list_accessible_customer_resource_names(
        self, access_token: str
    ) -> list[str]:
        url = self._api_url("customers:listAccessibleCustomers")
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.get(
                    url, headers=self._headers(access_token)
                )
        except httpx.HTTPError as exc:
            logger.warning("google_ads listAccessibleCustomers request failed")
            raise GoogleAdsApiError(
                "falha de rede em listAccessibleCustomers"
            ) from exc
        if response.status_code == 401:
            raise GoogleAdsApiError(
                "Google Ads API não autorizada (401)"
            )
        if response.status_code >= 400:
            logger.warning(
                "google_ads listAccessibleCustomers HTTP %s",
                response.status_code,
            )
            raise GoogleAdsApiError(
                f"listAccessibleCustomers falhou (HTTP {response.status_code})"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleAdsApiError(
                "listAccessibleCustomers resposta inválida"
            ) from exc
        names = payload.get("resourceNames") or payload.get("resource_names") or []
        return [str(n) for n in names if n]

    def _search(
        self,
        *,
        access_token: str,
        customer_id: str,
        login_customer_id: str | None,
        query: str,
    ) -> list[dict[str, Any]]:
        cid = _normalize_customer_id(customer_id) or customer_id
        url = self._api_url(f"customers/{cid}/googleAds:search")
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "query": query,
                "pageSize": self.page_size,
            }
            if page_token:
                body["pageToken"] = page_token
            try:
                with httpx.Client(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                    response = client.post(
                        url,
                        headers=self._headers(
                            access_token,
                            login_customer_id=login_customer_id,
                        ),
                        json=body,
                    )
            except httpx.HTTPError as exc:
                logger.warning("google_ads search request failed")
                raise GoogleAdsApiError(
                    "falha de rede em googleAds:search"
                ) from exc
            if response.status_code == 401:
                raise GoogleAdsApiError(
                    "Google Ads API não autorizada (401) em search"
                )
            if response.status_code >= 400:
                logger.warning(
                    "google_ads search HTTP %s customer_id=%s",
                    response.status_code,
                    cid,
                )
                raise GoogleAdsApiError(
                    f"googleAds:search falhou (HTTP {response.status_code})"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise GoogleAdsApiError(
                    "googleAds:search resposta inválida"
                ) from exc
            batch = payload.get("results") or []
            results.extend(item for item in batch if isinstance(item, dict))
            page_token = (
                str(payload.get("nextPageToken") or payload.get("next_page_token") or "")
                .strip()
                or None
            )
            if not page_token:
                break
        return results

    def _fetch_customer_detail(
        self,
        *,
        access_token: str,
        customer_id: str,
        login_customer_id: str | None,
    ) -> GoogleAdsAccount | None:
        query = (
            "SELECT "
            "customer.id, "
            "customer.descriptive_name, "
            "customer.manager, "
            "customer.currency_code, "
            "customer.time_zone "
            "FROM customer "
            "LIMIT 1"
        )
        try:
            rows = self._search(
                access_token=access_token,
                customer_id=customer_id,
                login_customer_id=login_customer_id,
                query=query,
            )
        except GoogleAdsApiError:
            return None
        if not rows:
            return None
        customer = rows[0].get("customer") or {}
        cid = _normalize_customer_id(
            str(customer.get("id") or customer_id)
        ) or customer_id
        return GoogleAdsAccount(
            customer_id=cid,
            descriptive_name=str(
                customer.get("descriptiveName")
                or customer.get("descriptive_name")
                or cid
            ),
            is_manager=bool(
                customer.get("manager") is True
                or customer.get("manager") == "true"
            ),
            currency_code=_optional_str(
                customer.get("currencyCode") or customer.get("currency_code")
            ),
            time_zone=_optional_str(
                customer.get("timeZone") or customer.get("time_zone")
            ),
            login_customer_id=_normalize_customer_id(login_customer_id),
        )

    def _list_customer_clients(
        self,
        *,
        access_token: str,
        manager_customer_id: str,
    ) -> list[GoogleAdsAccount]:
        query = (
            "SELECT "
            "customer_client.client_customer, "
            "customer_client.id, "
            "customer_client.descriptive_name, "
            "customer_client.manager, "
            "customer_client.currency_code, "
            "customer_client.time_zone, "
            "customer_client.status "
            "FROM customer_client "
            "WHERE customer_client.status != 'CANCELED'"
        )
        try:
            rows = self._search(
                access_token=access_token,
                customer_id=manager_customer_id,
                login_customer_id=manager_customer_id,
                query=query,
            )
        except GoogleAdsApiError:
            logger.warning(
                "google_ads customer_client hierarchy failed manager=%s",
                manager_customer_id,
            )
            return []

        out: list[GoogleAdsAccount] = []
        for item in rows:
            client = item.get("customerClient") or item.get("customer_client") or {}
            cid = _normalize_customer_id(
                str(
                    client.get("id")
                    or _customer_id_from_resource(
                        str(client.get("clientCustomer") or client.get("client_customer") or "")
                    )
                    or ""
                )
            )
            if not cid or cid == manager_customer_id:
                continue
            out.append(
                GoogleAdsAccount(
                    customer_id=cid,
                    descriptive_name=str(
                        client.get("descriptiveName")
                        or client.get("descriptive_name")
                        or cid
                    ),
                    is_manager=bool(
                        client.get("manager") is True
                        or client.get("manager") == "true"
                    ),
                    currency_code=_optional_str(
                        client.get("currencyCode")
                        or client.get("currency_code")
                    ),
                    time_zone=_optional_str(
                        client.get("timeZone") or client.get("time_zone")
                    ),
                    login_customer_id=manager_customer_id,
                )
            )
        return out


@dataclass
class HttpGoogleDataManagerPort:
    """IngestEvents na Data Manager API (conversões offline / ECL).

    Constrói o body a partir do shape canônico da outbox Revy (snake_case)
    e aceita base_url injetável para testes.
    """

    client_id: str
    client_secret: str
    base_url: str = DATA_MANAGER_API_BASE
    token_url: str = GOOGLE_OAUTH_TOKEN_URL
    timeout: float = 30.0
    transport: httpx.BaseTransport | None = None
    validate_only: bool = False
    encoding: str = "HEX"

    def ingest(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        events: Sequence[dict[str, Any]],
    ) -> GoogleDataManagerIngestResult:
        cid = _normalize_customer_id(customer_id) or (customer_id or "").strip()
        if not cid:
            raise GoogleDataManagerApiError("customer_id ausente")
        if not events:
            return GoogleDataManagerIngestResult(
                request_id="",
                accepted=0,
                rejected=0,
            )

        access = self._access_token(refresh_token)
        body = build_data_manager_ingest_request(
            customer_id=cid,
            events=events,
            validate_only=self.validate_only,
            encoding=self.encoding,
        )
        url = self.base_url.rstrip("/") + "/v1/events:ingest"
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {access}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            logger.warning("google_data_manager ingest request failed")
            raise GoogleDataManagerApiError(
                "falha de rede em events:ingest"
            ) from exc

        if response.status_code == 401:
            raise GoogleDataManagerApiError(
                "Data Manager API não autorizada (401)"
            )
        if response.status_code >= 400:
            logger.warning(
                "google_data_manager ingest HTTP %s customer_id=%s",
                response.status_code,
                cid,
            )
            raise GoogleDataManagerApiError(
                f"events:ingest falhou (HTTP {response.status_code})"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleDataManagerApiError(
                "events:ingest resposta inválida"
            ) from exc

        request_id = str(
            payload.get("requestId") or payload.get("request_id") or ""
        ).strip()
        # Aceite síncrono: request_id presente = lote aceito para processamento.
        return GoogleDataManagerIngestResult(
            request_id=request_id or "unknown",
            accepted=len(events),
            rejected=0,
        )

    def retrieve_status(
        self,
        *,
        refresh_token: str,
        request_id: str,
    ) -> GoogleDataManagerStatusResult:
        """GET /v1/requestStatus:retrieve?requestId=...

        Soft-fail: erros de rede/HTTP/parse → UNKNOWN (não interrompe worker).
        Tokens nunca são logados.
        """
        rid = (request_id or "").strip()
        if not rid:
            return GoogleDataManagerStatusResult(
                request_id="",
                status=DM_STATUS_UNKNOWN,
                raw_status=None,
                error_summary="request_id ausente",
            )

        try:
            access = self._access_token(refresh_token)
        except GoogleDataManagerApiError as exc:
            logger.warning(
                "google_data_manager retrieve_status token failed request_id=%s",
                rid,
            )
            return GoogleDataManagerStatusResult(
                request_id=rid,
                status=DM_STATUS_UNKNOWN,
                raw_status=None,
                error_summary=str(exc)[:200],
            )

        # Documentado: GET https://datamanager.googleapis.com/v1/requestStatus:retrieve
        url = self.base_url.rstrip("/") + "/v1/requestStatus:retrieve"
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.get(
                    url,
                    params={"requestId": rid},
                    headers={"Authorization": f"Bearer {access}"},
                )
        except httpx.HTTPError:
            logger.warning(
                "google_data_manager retrieve_status network failed request_id=%s",
                rid,
            )
            return GoogleDataManagerStatusResult(
                request_id=rid,
                status=DM_STATUS_UNKNOWN,
                raw_status=None,
                error_summary="falha de rede em requestStatus:retrieve",
            )

        if response.status_code >= 400:
            logger.warning(
                "google_data_manager retrieve_status HTTP %s request_id=%s",
                response.status_code,
                rid,
            )
            return GoogleDataManagerStatusResult(
                request_id=rid,
                status=DM_STATUS_UNKNOWN,
                raw_status=None,
                error_summary=f"requestStatus:retrieve HTTP {response.status_code}",
            )

        try:
            payload = response.json()
        except ValueError:
            logger.warning(
                "google_data_manager retrieve_status invalid json request_id=%s",
                rid,
            )
            return GoogleDataManagerStatusResult(
                request_id=rid,
                status=DM_STATUS_UNKNOWN,
                raw_status=None,
                error_summary="requestStatus:retrieve resposta inválida",
            )

        return _parse_request_status_response(rid, payload)

    def _access_token(self, refresh_token: str) -> str:
        token = (refresh_token or "").strip()
        if not token:
            raise GoogleDataManagerApiError("refresh token ausente")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = client.post(self.token_url, data=data)
        except httpx.HTTPError as exc:
            logger.warning("google_data_manager access_token request failed")
            raise GoogleDataManagerApiError(
                "falha de rede ao renovar access token"
            ) from exc
        if response.status_code == 401:
            raise GoogleDataManagerApiError(
                "OAuth rejeitado (401) ao renovar token"
            )
        if response.status_code >= 400:
            logger.warning(
                "google_data_manager access_token HTTP %s",
                response.status_code,
            )
            raise GoogleDataManagerApiError(
                f"renovação de access token falhou (HTTP {response.status_code})"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleDataManagerApiError(
                "resposta de access token inválida"
            ) from exc
        access = str(payload.get("access_token") or "").strip()
        if not access:
            raise GoogleDataManagerApiError("resposta sem access_token")
        return access


def _map_dm_request_status(raw: str | None) -> str:
    """Mapeia RequestStatus da API → status canônico Revy."""
    value = (raw or "").strip().upper()
    if value in {"SUCCESS"}:
        return DM_STATUS_SUCCESS
    if value in {"PARTIAL_SUCCESS"}:
        return DM_STATUS_PARTIAL_SUCCESS
    if value in {"FAILED", "FAILURE"}:
        return DM_STATUS_FAILURE
    if value in {"PROCESSING", "PENDING"}:
        return DM_STATUS_PENDING
    if value in {"REQUEST_STATUS_UNKNOWN", "UNKNOWN", ""}:
        return DM_STATUS_UNKNOWN
    return DM_STATUS_UNKNOWN


def _error_summary_from_status_payload(payload: dict[str, Any]) -> str | None:
    """Extrai resumo curto de erros por destino (sem PII/tokens)."""
    destinations = payload.get("requestStatusPerDestination") or payload.get(
        "request_status_per_destination"
    )
    if not isinstance(destinations, list):
        return None
    parts: list[str] = []
    for dest in destinations:
        if not isinstance(dest, dict):
            continue
        err = dest.get("errorInfo") or dest.get("error_info") or {}
        counts = err.get("errorCounts") or err.get("error_counts") or []
        if not isinstance(counts, list):
            continue
        for item in counts:
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or "").strip()
            record_count = item.get("recordCount") or item.get("record_count")
            if reason:
                if record_count is not None:
                    parts.append(f"{reason}:{record_count}")
                else:
                    parts.append(reason)
            if len(parts) >= 5:
                break
        if len(parts) >= 5:
            break
    if not parts:
        return None
    return ";".join(parts)[:300]


def _parse_request_status_response(
    request_id: str,
    payload: dict[str, Any],
) -> GoogleDataManagerStatusResult:
    """Agrega requestStatusPerDestination[] em um status canônico.

    Precedência: FAILURE > PARTIAL_SUCCESS > PENDING > SUCCESS > UNKNOWN.
    """
    destinations = payload.get("requestStatusPerDestination") or payload.get(
        "request_status_per_destination"
    )
    raw_statuses: list[str] = []
    if isinstance(destinations, list) and destinations:
        for dest in destinations:
            if not isinstance(dest, dict):
                continue
            raw = dest.get("requestStatus") or dest.get("request_status")
            if raw is not None:
                raw_statuses.append(str(raw))
    else:
        # fallback: campo de topo (se API/mock devolver assim)
        top = payload.get("requestStatus") or payload.get("request_status")
        if top is not None:
            raw_statuses.append(str(top))

    if not raw_statuses:
        return GoogleDataManagerStatusResult(
            request_id=request_id,
            status=DM_STATUS_UNKNOWN,
            raw_status=None,
            error_summary=_error_summary_from_status_payload(payload),
        )

    mapped = [_map_dm_request_status(s) for s in raw_statuses]
    if DM_STATUS_FAILURE in mapped:
        status = DM_STATUS_FAILURE
    elif DM_STATUS_PARTIAL_SUCCESS in mapped:
        status = DM_STATUS_PARTIAL_SUCCESS
    elif DM_STATUS_PENDING in mapped:
        status = DM_STATUS_PENDING
    elif DM_STATUS_SUCCESS in mapped and all(
        m == DM_STATUS_SUCCESS for m in mapped
    ):
        status = DM_STATUS_SUCCESS
    elif DM_STATUS_SUCCESS in mapped:
        # mistura SUCCESS + UNKNOWN → SUCCESS se não houver falha/pending
        status = DM_STATUS_SUCCESS
    else:
        status = DM_STATUS_UNKNOWN

    return GoogleDataManagerStatusResult(
        request_id=request_id,
        status=status,
        raw_status=",".join(raw_statuses)[:200],
        error_summary=_error_summary_from_status_payload(payload),
    )


def build_data_manager_ingest_request(
    *,
    customer_id: str,
    events: Sequence[dict[str, Any]],
    validate_only: bool = False,
    encoding: str = "HEX",
    login_customer_id: str | None = None,
) -> dict[str, Any]:
    """Monta body IngestEvents a partir do payload canônico da outbox Revy.

    Shape de entrada (por evento), alinhado a google_ads_conversions._build_event_payload:
    - transaction_id, event_source, event_timestamp
    - conversion_action (resource name ou ID)
    - ad_identifiers {gclid,gbraid,wbraid}
    - currency, conversion_value
    - user_data {email_hash, phone_hash} opcional
    - consent {ad_user_data: GRANTED|DENIED}
    """
    cid = _normalize_customer_id(customer_id) or customer_id
    destinations: list[dict[str, Any]] = []
    dest_key_to_ref: dict[str, str] = {}
    api_events: list[dict[str, Any]] = []

    for raw in events:
        event = dict(raw or {})
        # Aceita envelope {"event": {...}} ou o evento plano.
        if isinstance(event.get("event"), dict) and "transaction_id" not in event:
            event = {**event["event"], **{
                k: v for k, v in event.items() if k != "event"
            }}

        action = str(
            event.get("conversion_action")
            or event.get("conversion_action_resource_name")
            or ""
        ).strip()
        product_id = _conversion_action_product_id(action)
        if not product_id:
            # Sem action ID explícito — usa resource name cru se numérico.
            product_id = "".join(ch for ch in action if ch.isdigit()) or action
        dest_key = f"{cid}:{product_id}"
        if dest_key not in dest_key_to_ref:
            ref = f"dest_{len(destinations)}"
            dest_key_to_ref[dest_key] = ref
            destination: dict[str, Any] = {
                "reference": ref,
                "operatingAccount": {
                    "accountType": "GOOGLE_ADS",
                    "accountId": cid,
                },
                "productDestinationId": product_id,
            }
            login = _normalize_customer_id(
                login_customer_id
                or event.get("login_customer_id")  # type: ignore[arg-type]
            )
            if login:
                destination["loginAccount"] = {
                    "accountType": "GOOGLE_ADS",
                    "accountId": login,
                }
            destinations.append(destination)

        api_event = _map_outbox_event_to_data_manager(
            event,
            destination_reference=dest_key_to_ref[dest_key],
        )
        api_events.append(api_event)

    body: dict[str, Any] = {
        "destinations": destinations,
        "events": api_events,
        "encoding": encoding,
    }
    if validate_only:
        body["validateOnly"] = True
    return body


def _map_outbox_event_to_data_manager(
    event: dict[str, Any],
    *,
    destination_reference: str,
) -> dict[str, Any]:
    ad_ids_in = event.get("ad_identifiers") or event.get("adIdentifiers") or {}
    if not isinstance(ad_ids_in, dict):
        ad_ids_in = {}
    ad_identifiers: dict[str, str] = {}
    for key in ("gclid", "gbraid", "wbraid"):
        val = ad_ids_in.get(key)
        if val:
            ad_identifiers[key] = str(val)

    api: dict[str, Any] = {
        "destinationReferences": [destination_reference],
        "transactionId": str(
            event.get("transaction_id") or event.get("transactionId") or ""
        ),
        "eventTimestamp": str(
            event.get("event_timestamp") or event.get("eventTimestamp") or ""
        ),
        "eventSource": str(
            event.get("event_source") or event.get("eventSource") or "OTHER"
        ),
    }
    if ad_identifiers:
        api["adIdentifiers"] = ad_identifiers

    currency = event.get("currency")
    if currency:
        api["currency"] = str(currency).upper()

    value = event.get("conversion_value") or event.get("conversionValue")
    if value is not None and str(value) != "":
        try:
            api["conversionValue"] = float(value)
        except (TypeError, ValueError):
            api["conversionValue"] = str(value)

    consent_in = event.get("consent") or {}
    if isinstance(consent_in, dict) and consent_in:
        consent_out: dict[str, str] = {}
        ad_user = consent_in.get("ad_user_data") or consent_in.get("adUserData")
        if ad_user:
            consent_out["adUserData"] = str(ad_user)
        ad_pers = consent_in.get("ad_personalization") or consent_in.get(
            "adPersonalization"
        )
        if ad_pers:
            consent_out["adPersonalization"] = str(ad_pers)
        if consent_out:
            api["consent"] = consent_out

    user_in = event.get("user_data") or event.get("userData") or {}
    if isinstance(user_in, dict) and user_in:
        identifiers: list[dict[str, Any]] = []
        email_hash = user_in.get("email_hash") or user_in.get("emailAddress")
        phone_hash = user_in.get("phone_hash") or user_in.get("phoneNumber")
        if email_hash:
            identifiers.append({"emailAddress": str(email_hash)})
        if phone_hash:
            identifiers.append({"phoneNumber": str(phone_hash)})
        if identifiers:
            api["userData"] = {"userIdentifiers": identifiers}

    return api


def _customer_id_from_resource(resource: str) -> str | None:
    match = _RESOURCE_CUSTOMER_RE.search(resource or "")
    if match:
        return match.group(1)
    digits = "".join(ch for ch in (resource or "") if ch.isdigit())
    return digits or None


def _conversion_action_product_id(resource_or_id: str) -> str:
    match = _CONVERSION_ACTION_ID_RE.search(resource_or_id or "")
    if match:
        return match.group(1)
    digits = "".join(ch for ch in (resource_or_id or "") if ch.isdigit())
    return digits


def _safe_date(value: str) -> str:
    """Sanitiza literal de data GAQL (YYYY-MM-DD)."""
    raw = (value or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise GoogleAdsApiError(f"data inválida para GAQL: {value!r}")
    return raw


def _as_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
