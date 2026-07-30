"""Google Ads — ports de leitura/conversão e conexão OAuth (Fase 4A skeleton).

Sem mutação de campanhas. Adapters reais de API ficam para fatias posteriores;
aqui há ports, fakes e o fluxo de conexão com refresh token cifrado.
"""
from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlencode

from app.control.audit import _append_event
from app.control.stores import _find_store
from app.control.types import (
    AccessDenied,
    Actor,
    ControlError,
    StoreNotFound,
    StoreRef,
    TrafficRole,
)
from app.cripto import cifrar, decifrar
from app.models import (
    GoogleAdsConnection,
    GoogleAdsOAuthState,
    VinculoTrafego,
    agora,
)

# Escopos oficiais: Google Ads API + Data Manager API.
GOOGLE_ADS_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/datamanager",
)
_SCOPES_STORAGE = " ".join(GOOGLE_ADS_SCOPES)

GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_STATE_TTL = timedelta(minutes=10)

CONNECTION_STATUS_CONNECTED = "conectado"
CONNECTION_STATUS_ATTENTION = "atencao"
CONNECTION_STATUS_EXPIRED = "expirado"
CONNECTION_STATUS_REVOKED = "revogado"
CONNECTION_STATUS_ERROR = "erro"

_CONNECTION_STATUSES = frozenset(
    {
        CONNECTION_STATUS_CONNECTED,
        CONNECTION_STATUS_ATTENTION,
        CONNECTION_STATUS_EXPIRED,
        CONNECTION_STATUS_REVOKED,
        CONNECTION_STATUS_ERROR,
    }
)


class GoogleAdsOAuthStateInvalid(ControlError):
    """State OAuth ausente, expirado ou já consumido."""


class GoogleAdsConnectionNotFound(ControlError):
    pass


class GoogleAdsOAuthMisconfigured(ControlError):
    """Client OAuth não configurado no ambiente."""


class GoogleAdsTokenExchangeError(ControlError):
    """Falha ao trocar authorization code por tokens."""


@dataclass(frozen=True)
class GoogleAdsAccount:
    customer_id: str
    descriptive_name: str
    is_manager: bool
    currency_code: str | None = None
    time_zone: str | None = None
    login_customer_id: str | None = None


@dataclass(frozen=True)
class GoogleAdsMetricRow:
    """Stub de métrica diária — preenchido em fatias posteriores (GAQL)."""

    customer_id: str
    campaign_id: str
    date: str
    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    conversions: float = 0.0
    conversions_value: float = 0.0


@dataclass(frozen=True)
class GoogleDataManagerIngestResult:
    """Stub de resultado de ingestão na Data Manager API."""

    request_id: str
    accepted: int = 0
    rejected: int = 0


# Status canônicos Revy (mapeados a partir de RequestStatus da Data Manager API).
DM_STATUS_SUCCESS = "SUCCESS"
DM_STATUS_PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
DM_STATUS_FAILURE = "FAILURE"
DM_STATUS_PENDING = "PENDING"
DM_STATUS_UNKNOWN = "UNKNOWN"

_DM_STATUS_VALUES = frozenset(
    {
        DM_STATUS_SUCCESS,
        DM_STATUS_PARTIAL_SUCCESS,
        DM_STATUS_FAILURE,
        DM_STATUS_PENDING,
        DM_STATUS_UNKNOWN,
    }
)


@dataclass(frozen=True)
class GoogleDataManagerStatusResult:
    """Resultado de RetrieveRequestStatus (diagnóstico assíncrono)."""

    request_id: str
    status: str  # SUCCESS | PARTIAL_SUCCESS | FAILURE | PENDING | UNKNOWN
    raw_status: str | None = None
    error_summary: str | None = None


@dataclass(frozen=True)
class OAuthTokenBundle:
    refresh_token: str
    access_token: str
    scopes: tuple[str, ...] = GOOGLE_ADS_SCOPES
    expires_in: int | None = None


@dataclass(frozen=True)
class OAuthStartResult:
    auth_url: str
    state: str
    expires_at: datetime


@dataclass(frozen=True)
class GoogleAdsConnectionView:
    id: str
    loja_id: str
    status: str
    customer_id: str | None
    login_customer_id: str | None
    scopes: str
    has_refresh_token: bool
    created_at: datetime
    updated_at: datetime


class GoogleAdsReadPort(Protocol):
    """Leitura Google Ads API — sem métodos Mutate."""

    def list_accounts(self, refresh_token: str) -> Sequence[GoogleAdsAccount]:
        """Lista contas acessíveis ao refresh token (diretas + hierarquia)."""

    def fetch_metrics(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str | None,
        date_from: str,
        date_to: str,
    ) -> Sequence[GoogleAdsMetricRow]:
        """Stub de métricas diárias por campanha (GAQL Search/SearchStream)."""


class GoogleDataManagerPort(Protocol):
    """Envio de conversões via Data Manager API (IngestEvents + RetrieveRequestStatus)."""

    def ingest(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        events: Sequence[dict[str, Any]],
    ) -> GoogleDataManagerIngestResult:
        """Ingestão de eventos de conversão; retorna request_id para diagnóstico."""

    def retrieve_status(
        self,
        *,
        refresh_token: str,
        request_id: str,
    ) -> GoogleDataManagerStatusResult:
        """Consulta status assíncrono de um request_id (RetrieveRequestStatus)."""


class GoogleAdsTokenExchanger(Protocol):
    """Troca authorization code por tokens (injetável; fake em testes)."""

    def exchange(self, code: str) -> OAuthTokenBundle:
        """Troca o code OAuth; nunca deve vazar o refresh token em logs."""


@dataclass
class FakeGoogleAdsReadPort:
    """Adapter de teste: contas e métricas em memória."""

    accounts: list[GoogleAdsAccount] = field(default_factory=list)
    metrics: list[GoogleAdsMetricRow] = field(default_factory=list)
    list_accounts_calls: list[str] = field(default_factory=list)
    fetch_metrics_calls: list[dict[str, Any]] = field(default_factory=list)

    def list_accounts(self, refresh_token: str) -> Sequence[GoogleAdsAccount]:
        self.list_accounts_calls.append(refresh_token)
        return tuple(self.accounts)

    def fetch_metrics(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str | None,
        date_from: str,
        date_to: str,
    ) -> Sequence[GoogleAdsMetricRow]:
        self.fetch_metrics_calls.append(
            {
                "refresh_token": refresh_token,
                "customer_id": customer_id,
                "login_customer_id": login_customer_id,
                "date_from": date_from,
                "date_to": date_to,
            }
        )
        return tuple(
            row
            for row in self.metrics
            if row.customer_id == customer_id
            and date_from <= row.date <= date_to
        )


@dataclass
class FakeGoogleDataManagerPort:
    """Adapter de teste: registra ingestões/status sem chamar Google."""

    ingests: list[dict[str, Any]] = field(default_factory=list)
    retrieve_status_calls: list[dict[str, str]] = field(default_factory=list)
    next_request_id: str = "fake-request-1"
    next_status: str = DM_STATUS_SUCCESS
    status_by_request_id: dict[str, str] = field(default_factory=dict)
    error_summary: str | None = None

    def ingest(
        self,
        *,
        refresh_token: str,
        customer_id: str,
        events: Sequence[dict[str, Any]],
    ) -> GoogleDataManagerIngestResult:
        self.ingests.append(
            {
                "refresh_token": refresh_token,
                "customer_id": customer_id,
                "events": list(events),
            }
        )
        return GoogleDataManagerIngestResult(
            request_id=self.next_request_id,
            accepted=len(events),
            rejected=0,
        )

    def retrieve_status(
        self,
        *,
        refresh_token: str,
        request_id: str,
    ) -> GoogleDataManagerStatusResult:
        self.retrieve_status_calls.append(
            {
                "refresh_token": refresh_token,
                "request_id": request_id,
            }
        )
        status = self.status_by_request_id.get(request_id, self.next_status)
        if status not in _DM_STATUS_VALUES:
            status = DM_STATUS_UNKNOWN
        return GoogleDataManagerStatusResult(
            request_id=request_id,
            status=status,
            raw_status=status,
            error_summary=self.error_summary
            if status == DM_STATUS_FAILURE
            else None,
        )


@dataclass
class FakeGoogleAdsTokenExchanger:
    """Troca de code por tokens controlada em testes."""

    bundles_by_code: dict[str, OAuthTokenBundle] = field(default_factory=dict)
    default_bundle: OAuthTokenBundle | None = None
    calls: list[str] = field(default_factory=list)

    def exchange(self, code: str) -> OAuthTokenBundle:
        self.calls.append(code)
        if code in self.bundles_by_code:
            return self.bundles_by_code[code]
        if self.default_bundle is not None:
            return self.default_bundle
        raise GoogleAdsTokenExchangeError(
            f"código OAuth desconhecido no fake: {code}"
        )


class GoogleAdsConnectionControl:
    """Conexão OAuth multiusuário Google Ads por Loja.

    - start_oauth: gera state + auth_url (offline, adwords+datamanager)
    - complete_oauth: valida state, troca code (injetável), cifra refresh token
    - get / disconnect: nunca devolvem o refresh token em claro
    """

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        token_exchanger: GoogleAdsTokenExchanger | None = None,
        read_port: GoogleAdsReadPort | None = None,
        data_manager_port: GoogleDataManagerPort | None = None,
        now: Callable[[], datetime] | None = None,
        state_ttl: timedelta = OAUTH_STATE_TTL,
    ) -> None:
        self._session_factory = session_factory
        self._client_id = (client_id or "").strip()
        self._client_secret = (client_secret or "").strip()
        self._redirect_uri = (redirect_uri or "").strip()
        self._token_exchanger = token_exchanger or FakeGoogleAdsTokenExchanger(
            default_bundle=OAuthTokenBundle(
                refresh_token="fake-refresh-token",
                access_token="fake-access-token",
                scopes=GOOGLE_ADS_SCOPES,
            )
        )
        self._read_port = read_port or FakeGoogleAdsReadPort()
        self._data_manager_port = data_manager_port or FakeGoogleDataManagerPort()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._state_ttl = state_ttl

    @property
    def read_port(self) -> GoogleAdsReadPort:
        return self._read_port

    @property
    def data_manager_port(self) -> GoogleDataManagerPort:
        return self._data_manager_port

    def start_oauth(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> OAuthStartResult:
        self._require_oauth_client()
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_manage_connection(db, actor, loja.id)

            state = secrets.token_urlsafe(32)
            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            expires_at = now + self._state_ttl
            db.add(
                GoogleAdsOAuthState(
                    state=state,
                    loja_id=loja.id,
                    actor_id=actor.id,
                    expires_at=expires_at,
                    created_at=now,
                )
            )
            _append_event(
                db,
                actor=actor,
                store_id=loja.id,
                action="google_ads.oauth_started",
                resource_type="google_ads_oauth_state",
                resource_id=state,
                after={"expires_at": expires_at.isoformat()},
            )
            db.commit()

        auth_url = self._build_auth_url(state)
        return OAuthStartResult(
            auth_url=auth_url,
            state=state,
            expires_at=expires_at,
        )

    def complete_oauth(
        self,
        *,
        state: str,
        code: str,
        customer_id: str | None = None,
        login_customer_id: str | None = None,
    ) -> GoogleAdsConnectionView:
        state_value = (state or "").strip()
        code_value = (code or "").strip()
        if not state_value or not code_value:
            raise GoogleAdsOAuthStateInvalid("state ou code OAuth ausente")

        with self._session_factory() as db:
            row = (
                db.query(GoogleAdsOAuthState)
                .filter(GoogleAdsOAuthState.state == state_value)
                .first()
            )
            if row is None:
                raise GoogleAdsOAuthStateInvalid("state OAuth inválido")
            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                db.delete(row)
                db.commit()
                raise GoogleAdsOAuthStateInvalid("state OAuth expirado")

            loja_id = row.loja_id
            actor_id = row.actor_id
            db.delete(row)
            db.flush()

            try:
                bundle = self._token_exchanger.exchange(code_value)
            except GoogleAdsTokenExchangeError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise GoogleAdsTokenExchangeError(
                    "falha ao trocar authorization code"
                ) from exc

            if not (bundle.refresh_token or "").strip():
                raise GoogleAdsTokenExchangeError(
                    "resposta OAuth sem refresh token"
                )

            ciphertext = cifrar(bundle.refresh_token)
            scopes = (
                " ".join(bundle.scopes)
                if bundle.scopes
                else _SCOPES_STORAGE
            )

            connection = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == loja_id)
                .first()
            )
            before: dict[str, object] | None = None
            if connection is None:
                connection = GoogleAdsConnection(
                    loja_id=loja_id,
                    status=CONNECTION_STATUS_CONNECTED,
                    customer_id=_normalize_customer_id(customer_id),
                    login_customer_id=_normalize_customer_id(login_customer_id),
                    refresh_token_ciphertext=ciphertext,
                    scopes=scopes,
                    created_at=now,
                    updated_at=now,
                )
                db.add(connection)
            else:
                before = {
                    "status": connection.status,
                    "customer_id": connection.customer_id,
                    "login_customer_id": connection.login_customer_id,
                    "has_refresh_token": bool(
                        connection.refresh_token_ciphertext
                    ),
                }
                connection.status = CONNECTION_STATUS_CONNECTED
                if customer_id is not None:
                    connection.customer_id = _normalize_customer_id(
                        customer_id
                    )
                if login_customer_id is not None:
                    connection.login_customer_id = _normalize_customer_id(
                        login_customer_id
                    )
                connection.refresh_token_ciphertext = ciphertext
                connection.scopes = scopes
                connection.updated_at = now

            actor = Actor(
                id=actor_id,
                email="",
                name="",
                role="gestor",
            )
            db.flush()
            _append_event(
                db,
                actor=actor,
                store_id=loja_id,
                action="google_ads.oauth_completed",
                resource_type="google_ads_connection",
                resource_id=connection.id,
                before=before,
                after={
                    "status": connection.status,
                    "customer_id": connection.customer_id,
                    "login_customer_id": connection.login_customer_id,
                    "has_refresh_token": True,
                    "scopes": connection.scopes,
                },
            )
            db.commit()
            db.refresh(connection)
            return _connection_view(connection)

    def get(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> GoogleAdsConnectionView:
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_view_connection(db, actor, loja.id)
            connection = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == loja.id)
                .first()
            )
            if connection is None:
                raise GoogleAdsConnectionNotFound(
                    "conexão Google Ads não encontrada"
                )
            return _connection_view(connection)

    def disconnect(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> GoogleAdsConnectionView:
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_manage_connection(db, actor, loja.id)
            connection = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == loja.id)
                .first()
            )
            if connection is None:
                raise GoogleAdsConnectionNotFound(
                    "conexão Google Ads não encontrada"
                )
            before = {
                "status": connection.status,
                "has_refresh_token": bool(connection.refresh_token_ciphertext),
            }
            connection.refresh_token_ciphertext = None
            connection.status = CONNECTION_STATUS_REVOKED
            connection.updated_at = agora()
            _append_event(
                db,
                actor=actor,
                store_id=loja.id,
                action="google_ads.disconnected",
                resource_type="google_ads_connection",
                resource_id=connection.id,
                before=before,
                after={
                    "status": connection.status,
                    "has_refresh_token": False,
                },
            )
            db.commit()
            db.refresh(connection)
            return _connection_view(connection)

    def decrypt_refresh_token(self, connection_id: str) -> str | None:
        """Uso interno do backend somente — nunca expor em HTTP/logs."""
        with self._session_factory() as db:
            connection = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.id == connection_id)
                .first()
            )
            if connection is None or not connection.refresh_token_ciphertext:
                return None
            return decifrar(connection.refresh_token_ciphertext)

    def _require_oauth_client(self) -> None:
        if not self._client_id or not self._redirect_uri:
            raise GoogleAdsOAuthMisconfigured(
                "GOOGLE_ADS_OAUTH_CLIENT_ID e "
                "GOOGLE_ADS_OAUTH_REDIRECT_URI são obrigatórios"
            )

    def _build_auth_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": _SCOPES_STORAGE,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_OAUTH_AUTH_URL}?{urlencode(params)}"


def _connection_view(row: GoogleAdsConnection) -> GoogleAdsConnectionView:
    return GoogleAdsConnectionView(
        id=row.id,
        loja_id=row.loja_id,
        status=row.status,
        customer_id=row.customer_id,
        login_customer_id=row.login_customer_id,
        scopes=row.scopes,
        has_refresh_token=bool(row.refresh_token_ciphertext),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_customer_id(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in value.strip() if ch.isdigit())
    return digits or None


def _assert_can_view_connection(db: Any, actor: Actor, loja_id: str) -> None:
    if actor.is_admin:
        return
    link = (
        db.query(VinculoTrafego)
        .filter(
            VinculoTrafego.loja_id == loja_id,
            VinculoTrafego.gestor_id == actor.id,
            VinculoTrafego.encerrado_em.is_(None),
        )
        .first()
    )
    if link is None:
        # Não vaza existência da loja/conexão para gestores sem vínculo.
        raise StoreNotFound("Loja não encontrada")


def _assert_can_manage_connection(db: Any, actor: Actor, loja_id: str) -> None:
    """Admin ou responsável podem conectar/desconectar; colaborador não."""
    if actor.is_admin:
        return
    link = (
        db.query(VinculoTrafego)
        .filter(
            VinculoTrafego.loja_id == loja_id,
            VinculoTrafego.gestor_id == actor.id,
            VinculoTrafego.encerrado_em.is_(None),
        )
        .first()
    )
    if link is None:
        raise StoreNotFound("Loja não encontrada")
    if link.tipo != TrafficRole.RESPONSIBLE.value:
        raise AccessDenied(
            "somente Admin Revy ou Gestor Responsável pode "
            "conectar ou desconectar Google Ads"
        )
