"""Google Ads — sincronização de contas e métricas diárias (Fase 4B).

Sem mutação de campanhas. Usa GoogleAdsReadPort (fakes em testes).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.control.audit import _append_event
from app.control.google_ads import (
    CONNECTION_STATUS_CONNECTED,
    FakeGoogleAdsReadPort,
    GoogleAdsAccount as GoogleAdsAccountDTO,
    GoogleAdsConnectionNotFound,
    GoogleAdsConversionAction,
    GoogleAdsMetricRow,
    GoogleAdsReadPort,
    _assert_can_manage_connection,
    _assert_can_view_connection,
    _normalize_customer_id,
)
from app.control.stores import _find_store
from app.control.types import (
    Actor,
    ControlError,
    StoreNotFound,
    StoreRef,
)
from app.cripto import decifrar
from app.models import (
    GoogleAdsAccount,
    GoogleAdsCampaignDaily,
    GoogleAdsConnection,
    agora,
    novo_id,
)

CENTAVOS = Decimal("0.01")
MICROS = Decimal("1000000")
CTR_PREC = Decimal("0.0001")

ACCOUNT_STATUS_ACTIVE = "ativo"
ACCOUNT_STATUS_INACTIVE = "inativo"
ACCOUNT_STATUS_UNKNOWN = "desconhecido"


class GoogleAdsManagerAccountNotSelectable(ControlError):
    """Conta manager não pode ser selecionada como anunciante."""


class GoogleAdsAccountNotFound(ControlError):
    pass


class GoogleAdsNotConnected(ControlError):
    """Loja sem conexão Google Ads ativa com refresh token."""


class GoogleAdsNoSelectedAccount(ControlError):
    """Nenhuma conta anunciante selecionada para a loja."""


@dataclass(frozen=True)
class GoogleAdsAccountView:
    id: str
    loja_id: str
    customer_id: str
    login_customer_id: str | None
    is_manager: bool
    currency_code: str | None
    time_zone: str | None
    descriptive_name: str | None
    selected: bool
    status: str


@dataclass(frozen=True)
class MetricsSummary:
    loja_id: str
    customer_id: str | None
    date_from: str
    date_to: str
    impressions: int
    clicks: int
    cost_micros: int
    cost: Decimal
    conversions: Decimal
    conversions_value: Decimal
    currency_code: str | None
    ctr: Decimal | None
    cpc: Decimal | None
    # CPL = cost / Google conversions (não junta VendaProjetada Revy).
    cpl: Decimal | None
    # ROAS = conversions_value Google / cost (não usa faturamento Revy).
    roas: Decimal | None
    # Alias de cpl (custo por conversão Google).
    cost_per_conversion: Decimal | None


@dataclass(frozen=True)
class SyncMetricsResult:
    loja_id: str
    customer_id: str
    rows_upserted: int
    date_from: str
    date_to: str


@dataclass(frozen=True)
class AcquisitionGoogleResumo:
    """Contrato read-only de aquisição Google para Revy Loja / dashboard."""

    loja_id: str
    date_from: str
    date_to: str
    google_disponivel: bool
    summary: MetricsSummary | None


def cost_from_micros(cost_micros: int | Decimal) -> Decimal:
    """Converte cost_micros (1e6) para valor monetário com 2 casas (ROUND_HALF_UP)."""
    micros = Decimal(int(cost_micros))
    return (micros / MICROS).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def compute_ctr(impressions: int, clicks: int) -> Decimal | None:
    if impressions <= 0:
        return None
    return (Decimal(clicks) / Decimal(impressions)).quantize(
        CTR_PREC, rounding=ROUND_HALF_UP
    )


def compute_cpc(cost_micros: int, clicks: int) -> Decimal | None:
    if clicks <= 0:
        return None
    return (cost_from_micros(cost_micros) / Decimal(clicks)).quantize(
        CENTAVOS, rounding=ROUND_HALF_UP
    )


def compute_cpl(
    cost_micros: int,
    conversions: Decimal | float | int,
) -> Decimal | None:
    """Custo por conversão Google (CPL) quando conversions > 0."""
    conv = Decimal(str(conversions))
    if conv <= 0:
        return None
    return (cost_from_micros(cost_micros) / conv).quantize(
        CENTAVOS, rounding=ROUND_HALF_UP
    )


def compute_roas(
    cost_micros: int,
    conversions_value: Decimal | float | int,
) -> Decimal | None:
    """ROAS = conversions_value / cost quando cost > 0 e value > 0.

    Usa apenas métricas Google (conversions_value). Não junta VendaProjetada
    Revy — datas e atribuição diferem; join fica fora deste resumo.
    """
    cost = cost_from_micros(cost_micros)
    value = Decimal(str(conversions_value))
    if cost <= 0 or value <= 0:
        return None
    return (value / cost).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


class GoogleAdsMetricsControl:
    """Contas + métricas diárias por loja via read_port."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        read_port: GoogleAdsReadPort | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._read_port = read_port or FakeGoogleAdsReadPort()
        self._now = now or (lambda: datetime.now(timezone.utc))

    @property
    def read_port(self) -> GoogleAdsReadPort:
        return self._read_port

    def list_accounts(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> tuple[GoogleAdsAccountView, ...]:
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_view_connection(db, actor, loja.id)
            rows = (
                db.query(GoogleAdsAccount)
                .filter(GoogleAdsAccount.loja_id == loja.id)
                .order_by(GoogleAdsAccount.customer_id.asc())
                .all()
            )
            return tuple(_account_view(r) for r in rows)

    def select_account(
        self,
        actor: Actor,
        store: StoreRef,
        customer_id: str,
    ) -> GoogleAdsAccountView:
        cid = _normalize_customer_id(customer_id)
        if not cid:
            raise GoogleAdsAccountNotFound("customer_id inválido")

        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_manage_connection(db, actor, loja.id)

            account = (
                db.query(GoogleAdsAccount)
                .filter(
                    GoogleAdsAccount.loja_id == loja.id,
                    GoogleAdsAccount.customer_id == cid,
                )
                .first()
            )
            if account is None:
                raise GoogleAdsAccountNotFound(
                    "conta Google Ads não encontrada para a loja"
                )
            if account.is_manager:
                raise GoogleAdsManagerAccountNotSelectable(
                    "conta manager não pode ser selecionada como anunciante"
                )

            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)

            others = (
                db.query(GoogleAdsAccount)
                .filter(
                    GoogleAdsAccount.loja_id == loja.id,
                    GoogleAdsAccount.selected.is_(True),
                    GoogleAdsAccount.customer_id != cid,
                )
                .all()
            )
            for other in others:
                other.selected = False
                other.updated_at = now

            account.selected = True
            account.updated_at = now

            connection = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == loja.id)
                .first()
            )
            if connection is not None:
                connection.customer_id = account.customer_id
                connection.login_customer_id = account.login_customer_id
                connection.updated_at = now

            _append_event(
                db,
                actor=actor,
                store_id=loja.id,
                action="google_ads.account_selected",
                resource_type="google_ads_account",
                resource_id=account.id,
                after={
                    "customer_id": account.customer_id,
                    "login_customer_id": account.login_customer_id,
                    "is_manager": account.is_manager,
                },
            )
            db.commit()
            db.refresh(account)
            return _account_view(account)

    def sync_accounts(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> tuple[GoogleAdsAccountView, ...]:
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_manage_connection(db, actor, loja.id)
            refresh_token, _connection = _require_connected(db, loja.id)

        discovered = list(self._read_port.list_accounts(refresh_token))

        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)

            views: list[GoogleAdsAccountView] = []
            for dto in discovered:
                views.append(_upsert_account(db, loja_id=loja.id, dto=dto, now=now))

            _append_event(
                db,
                actor=actor,
                store_id=loja.id,
                action="google_ads.accounts_synced",
                resource_type="google_ads_account",
                resource_id=loja.id,
                after={"count": len(views)},
            )
            db.commit()
            return tuple(views)

    def sync_metrics(
        self,
        actor: Actor,
        store: StoreRef,
        *,
        date_from: str,
        date_to: str,
    ) -> SyncMetricsResult:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        if d_from > d_to:
            raise ControlError("date_from deve ser <= date_to")

        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_manage_connection(db, actor, loja.id)
            loja_id = loja.id

        result = self._sync_metrics_core(
            loja_id,
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
        )

        with self._session_factory() as db:
            _append_event(
                db,
                actor=actor,
                store_id=result.loja_id,
                action="google_ads.metrics_synced",
                resource_type="google_ads_campaign_daily",
                resource_id=result.customer_id,
                after={
                    "customer_id": result.customer_id,
                    "date_from": result.date_from,
                    "date_to": result.date_to,
                    "rows_upserted": result.rows_upserted,
                },
            )
            db.commit()

        return result

    def sync_metrics_for_store_id(
        self,
        loja_id: str,
        *,
        date_from: str,
        date_to: str,
    ) -> SyncMetricsResult:
        """Sincroniza métricas para job interno (sem Actor/RBAC).

        Confia no caller (worker). Só exige conexão ativa + conta selecionada.
        Não grava auditoria de ator humano.
        """
        lid = (loja_id or "").strip()
        if not lid:
            raise StoreNotFound("Loja não encontrada")
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        if d_from > d_to:
            raise ControlError("date_from deve ser <= date_to")
        return self._sync_metrics_core(
            lid,
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
        )

    def _sync_metrics_core(
        self,
        loja_id: str,
        *,
        date_from: str,
        date_to: str,
    ) -> SyncMetricsResult:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)

        with self._session_factory() as db:
            refresh_token, connection = _require_connected(db, loja_id)
            selected = _selected_account(db, loja_id, connection)
            customer_id = selected.customer_id
            login_customer_id = selected.login_customer_id
            currency = selected.currency_code

        rows = self._read_port.fetch_metrics(
            refresh_token=refresh_token,
            customer_id=customer_id,
            login_customer_id=login_customer_id,
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
        )

        upserted = self._upsert_metric_rows(
            loja_id=loja_id,
            rows=rows,
            default_currency=currency,
        )

        return SyncMetricsResult(
            loja_id=loja_id,
            customer_id=customer_id,
            rows_upserted=upserted,
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
        )

    def metrics_summary(
        self,
        actor: Actor,
        store: StoreRef,
        *,
        date_from: str,
        date_to: str,
    ) -> MetricsSummary:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        if d_from > d_to:
            raise ControlError("date_from deve ser <= date_to")

        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_view_connection(db, actor, loja.id)
            loja_id = loja.id

        return self._metrics_summary_unscoped(
            loja_id=loja_id,
            date_from=d_from,
            date_to=d_to,
        )

    def list_conversion_actions(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> tuple[GoogleAdsConversionAction, ...]:
        """Lista conversion actions remotas da conta selecionada (sem create)."""
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_view_connection(db, actor, loja.id)
            refresh_token, connection = _require_connected(db, loja.id)
            selected = _selected_account(db, loja.id, connection)
            customer_id = selected.customer_id
            login_customer_id = selected.login_customer_id

        actions = self._read_port.list_conversion_actions(
            refresh_token=refresh_token,
            customer_id=customer_id,
            login_customer_id=login_customer_id,
        )
        return tuple(actions)

    def acquisition_resumo(
        self,
        store: StoreRef,
        *,
        date_from: str,
        date_to: str,
    ) -> AcquisitionGoogleResumo:
        """Resumo comercial Google read-only (service token / Loja).

        Sem actor de browser: loja ausente → StoreNotFound.
        google_disponivel exige conexão connected + conta anunciante selecionada
        (ou customer_id na conexão). Não expõe tokens.
        """
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        if d_from > d_to:
            raise ControlError("date_from deve ser <= date_to")

        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            loja_id = loja.id
            disponivel = _google_disponivel(db, loja_id)

        if not disponivel:
            return AcquisitionGoogleResumo(
                loja_id=loja_id,
                date_from=d_from.isoformat(),
                date_to=d_to.isoformat(),
                google_disponivel=False,
                summary=None,
            )

        summary = self._metrics_summary_unscoped(
            loja_id=loja_id,
            date_from=d_from,
            date_to=d_to,
        )
        return AcquisitionGoogleResumo(
            loja_id=loja_id,
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
            google_disponivel=True,
            summary=summary,
        )

    def _metrics_summary_unscoped(
        self,
        *,
        loja_id: str,
        date_from: date,
        date_to: date,
    ) -> MetricsSummary:
        """Agrega métricas diárias sem checagem de actor (uso service/dashboard)."""
        with self._session_factory() as db:
            connection = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == loja_id)
                .first()
            )
            selected = (
                db.query(GoogleAdsAccount)
                .filter(
                    GoogleAdsAccount.loja_id == loja_id,
                    GoogleAdsAccount.selected.is_(True),
                )
                .first()
            )
            customer_id = (
                selected.customer_id
                if selected is not None
                else (connection.customer_id if connection else None)
            )

            q = db.query(GoogleAdsCampaignDaily).filter(
                GoogleAdsCampaignDaily.loja_id == loja_id,
                GoogleAdsCampaignDaily.date >= date_from,
                GoogleAdsCampaignDaily.date <= date_to,
            )
            if customer_id:
                q = q.filter(GoogleAdsCampaignDaily.customer_id == customer_id)
            daily = q.all()

            impressions = sum(int(r.impressions) for r in daily)
            clicks = sum(int(r.clicks) for r in daily)
            cost_micros = sum(int(r.cost_micros) for r in daily)
            conversions = sum(
                (Decimal(str(r.conversions)) for r in daily), Decimal("0")
            )
            conversions_value = sum(
                (Decimal(str(r.conversions_value)) for r in daily), Decimal("0")
            )
            currency = None
            if daily:
                currency = daily[0].currency_code
            if selected is not None and not currency:
                currency = selected.currency_code

            cpl = compute_cpl(cost_micros, conversions)
            return MetricsSummary(
                loja_id=loja_id,
                customer_id=customer_id,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
                impressions=impressions,
                clicks=clicks,
                cost_micros=cost_micros,
                cost=cost_from_micros(cost_micros),
                conversions=conversions,
                conversions_value=conversions_value,
                currency_code=currency,
                ctr=compute_ctr(impressions, clicks),
                cpc=compute_cpc(cost_micros, clicks),
                cpl=cpl,
                roas=compute_roas(cost_micros, conversions_value),
                cost_per_conversion=cpl,
            )

    def _upsert_metric_rows(
        self,
        *,
        loja_id: str,
        rows: Sequence[GoogleAdsMetricRow],
        default_currency: str | None,
    ) -> int:
        count = 0
        with self._session_factory() as db:
            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            for row in rows:
                day = _parse_date(row.date)
                existing = (
                    db.query(GoogleAdsCampaignDaily)
                    .filter(
                        GoogleAdsCampaignDaily.customer_id == row.customer_id,
                        GoogleAdsCampaignDaily.campaign_id == str(row.campaign_id),
                        GoogleAdsCampaignDaily.date == day,
                    )
                    .first()
                )
                currency = default_currency
                if existing is None:
                    db.add(
                        GoogleAdsCampaignDaily(
                            id=novo_id(),
                            loja_id=loja_id,
                            customer_id=row.customer_id,
                            campaign_id=str(row.campaign_id),
                            date=day,
                            impressions=int(row.impressions),
                            clicks=int(row.clicks),
                            cost_micros=int(row.cost_micros),
                            conversions=Decimal(str(row.conversions)),
                            conversions_value=Decimal(str(row.conversions_value)),
                            currency_code=currency,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    existing.impressions = int(row.impressions)
                    existing.clicks = int(row.clicks)
                    existing.cost_micros = int(row.cost_micros)
                    existing.conversions = Decimal(str(row.conversions))
                    existing.conversions_value = Decimal(str(row.conversions_value))
                    if currency:
                        existing.currency_code = currency
                    existing.updated_at = now
                count += 1
            db.commit()
        return count


def _account_view(row: GoogleAdsAccount) -> GoogleAdsAccountView:
    return GoogleAdsAccountView(
        id=row.id,
        loja_id=row.loja_id,
        customer_id=row.customer_id,
        login_customer_id=row.login_customer_id,
        is_manager=bool(row.is_manager),
        currency_code=row.currency_code,
        time_zone=row.time_zone,
        descriptive_name=row.descriptive_name,
        selected=bool(row.selected),
        status=row.status,
    )


def _upsert_account(
    db: Any,
    *,
    loja_id: str,
    dto: GoogleAdsAccountDTO,
    now: datetime,
) -> GoogleAdsAccountView:
    cid = _normalize_customer_id(dto.customer_id) or dto.customer_id
    login = _normalize_customer_id(dto.login_customer_id)
    existing = (
        db.query(GoogleAdsAccount)
        .filter(
            GoogleAdsAccount.loja_id == loja_id,
            GoogleAdsAccount.customer_id == cid,
        )
        .first()
    )
    if existing is None:
        existing = GoogleAdsAccount(
            id=novo_id(),
            loja_id=loja_id,
            customer_id=cid,
            login_customer_id=login,
            is_manager=bool(dto.is_manager),
            currency_code=dto.currency_code,
            time_zone=dto.time_zone,
            descriptive_name=dto.descriptive_name,
            selected=False,
            status=ACCOUNT_STATUS_ACTIVE,
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        existing.login_customer_id = login
        existing.is_manager = bool(dto.is_manager)
        existing.currency_code = dto.currency_code
        existing.time_zone = dto.time_zone
        existing.descriptive_name = dto.descriptive_name
        existing.status = ACCOUNT_STATUS_ACTIVE
        existing.updated_at = now
    db.flush()
    return _account_view(existing)


def _google_disponivel(db: Any, loja_id: str) -> bool:
    """Conexão connected + refresh token + conta anunciante (selected ou customer_id)."""
    connection = (
        db.query(GoogleAdsConnection)
        .filter(GoogleAdsConnection.loja_id == loja_id)
        .first()
    )
    if connection is None:
        return False
    if (
        connection.status != CONNECTION_STATUS_CONNECTED
        or not connection.refresh_token_ciphertext
    ):
        return False
    selected = (
        db.query(GoogleAdsAccount)
        .filter(
            GoogleAdsAccount.loja_id == loja_id,
            GoogleAdsAccount.selected.is_(True),
            GoogleAdsAccount.is_manager.is_(False),
        )
        .first()
    )
    if selected is not None:
        return True
    return bool(connection.customer_id)


def _require_connected(
    db: Any,
    loja_id: str,
) -> tuple[str, GoogleAdsConnection]:
    connection = (
        db.query(GoogleAdsConnection)
        .filter(GoogleAdsConnection.loja_id == loja_id)
        .first()
    )
    if connection is None:
        raise GoogleAdsConnectionNotFound("conexão Google Ads não encontrada")
    if (
        connection.status != CONNECTION_STATUS_CONNECTED
        or not connection.refresh_token_ciphertext
    ):
        raise GoogleAdsNotConnected(
            "conexão Google Ads inativa ou sem refresh token"
        )
    return decifrar(connection.refresh_token_ciphertext), connection


def _selected_account(
    db: Any,
    loja_id: str,
    connection: GoogleAdsConnection,
) -> GoogleAdsAccount:
    selected = (
        db.query(GoogleAdsAccount)
        .filter(
            GoogleAdsAccount.loja_id == loja_id,
            GoogleAdsAccount.selected.is_(True),
        )
        .first()
    )
    if selected is not None:
        if selected.is_manager:
            raise GoogleAdsManagerAccountNotSelectable(
                "conta manager não pode ser usada para métricas"
            )
        return selected
    if connection.customer_id:
        fallback = (
            db.query(GoogleAdsAccount)
            .filter(
                GoogleAdsAccount.loja_id == loja_id,
                GoogleAdsAccount.customer_id == connection.customer_id,
            )
            .first()
        )
        if fallback is not None and not fallback.is_manager:
            return fallback
        if fallback is None:
            # conexão tem customer_id mas ainda sem row de conta — sintetiza view
            synthetic = GoogleAdsAccount(
                id="synthetic",
                loja_id=loja_id,
                customer_id=connection.customer_id,
                login_customer_id=connection.login_customer_id,
                is_manager=False,
                currency_code=None,
                time_zone=None,
                descriptive_name=None,
                selected=True,
                status=ACCOUNT_STATUS_UNKNOWN,
            )
            return synthetic
    raise GoogleAdsNoSelectedAccount(
        "selecione uma conta anunciante antes de sincronizar métricas"
    )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError as exc:
        raise ControlError(f"data inválida: {value}") from exc
