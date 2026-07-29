from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.control.integrations import pixel_configured
from app.control.readiness import StoreReadiness
from app.control.stores import StoreControl
from app.control.types import AccessDenied, Actor, StoreRef, StoreStatus, StoreView
from app.meta_ads_spend import normalizar_ad_account_id
from app.models import GoogleAdsConnection, MetaAdsConfig, MetaPixelConfig


class _WhatsAppChannelsPort(Protocol):
    def list_for_store(self, store_ref: StoreRef) -> list[Any]: ...


@dataclass(frozen=True)
class StoreReadinessSummary:
    store_id: str
    slug: str
    name: str
    status: StoreStatus
    ready: bool


@dataclass(frozen=True)
class DashboardCounts:
    ativas: int
    em_configuracao: int
    suspensas: int
    erro: int


@dataclass(frozen=True)
class PendingReadinessItem:
    store_id: str
    slug: str
    name: str
    status: StoreStatus
    failing_codes: tuple[str, ...]


@dataclass(frozen=True)
class StoreIntegrationHealth:
    store_id: str
    slug: str
    pixel_connected: bool
    meta_ads_connected: bool
    google_status: str | None
    whatsapp_channels: int | None


@dataclass(frozen=True)
class DashboardOverview:
    counts: DashboardCounts
    items: tuple[StoreReadinessSummary, ...]
    pending_readiness: tuple[PendingReadinessItem, ...]
    integrations: tuple[StoreIntegrationHealth, ...]


class _StoreStub:
    """Stub mínimo para reutilizar helpers que esperam Loja (id/slug)."""

    def __init__(self, store_id: str, slug: str) -> None:
        self.id = store_id
        self.slug = slug


class DashboardControl:
    """Resumo lean de prontidão e saúde no escopo do ator."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        whatsapp_port: _WhatsAppChannelsPort | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._stores = StoreControl(session_factory)
        self._readiness = StoreReadiness(session_factory)
        self._whatsapp_port = whatsapp_port

    def summary(self, actor: Actor) -> tuple[StoreReadinessSummary, ...]:
        return self.overview(actor).items

    def overview(self, actor: Actor) -> DashboardOverview:
        """Visão admin (todas) ou gestor (somente lojas com vínculo)."""
        stores = self._stores.list(actor)
        items: list[StoreReadinessSummary] = []
        pending: list[PendingReadinessItem] = []
        integrations: list[StoreIntegrationHealth] = []
        ativas = 0
        em_configuracao = 0
        suspensas = 0
        erro = 0

        for store in stores:
            report = self._readiness.evaluate(actor, StoreRef(id=store.id))
            items.append(
                StoreReadinessSummary(
                    store_id=store.id,
                    slug=store.slug,
                    name=store.name,
                    status=store.status,
                    ready=report.ready,
                )
            )
            if store.status is StoreStatus.ACTIVE:
                ativas += 1
            elif store.status is StoreStatus.CONFIGURING:
                em_configuracao += 1
            elif store.status is StoreStatus.SUSPENDED:
                suspensas += 1

            # Card "erro": loja ativa que perdeu prontidão (required falhou).
            if store.status is StoreStatus.ACTIVE and not report.ready:
                erro += 1

            if not report.ready:
                failing = tuple(
                    check.code for check in report.checks if not check.ok
                )
                pending.append(
                    PendingReadinessItem(
                        store_id=store.id,
                        slug=store.slug,
                        name=store.name,
                        status=store.status,
                        failing_codes=failing,
                    )
                )

            integrations.append(self._integration_health(store))

        return DashboardOverview(
            counts=DashboardCounts(
                ativas=ativas,
                em_configuracao=em_configuracao,
                suspensas=suspensas,
                erro=erro,
            ),
            items=tuple(items),
            pending_readiness=tuple(pending),
            integrations=tuple(integrations),
        )

    def admin_overview(self, actor: Actor) -> DashboardOverview:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode ver overview global")
        return self.overview(actor)

    def gestor_overview(self, actor: Actor) -> DashboardOverview:
        """Alias semântico: overview já filtra pelo vínculo do gestor."""
        return self.overview(actor)

    def _integration_health(self, store: StoreView) -> StoreIntegrationHealth:
        with self._session_factory() as db:
            stub = _StoreStub(store.id, store.slug)
            pixel_ok = pixel_configured(db, stub)

            ads_row = (
                db.query(MetaAdsConfig)
                .filter(MetaAdsConfig.loja_id == store.id)
                .first()
            )
            if ads_row is None:
                ads_row = (
                    db.query(MetaAdsConfig)
                    .filter(MetaAdsConfig.loja_slug == store.slug)
                    .first()
                )
            account = normalizar_ad_account_id(
                ads_row.ad_account_id if ads_row else None
            )
            meta_ads_ok = bool(
                ads_row and account and ads_row.token_ciphertext
            )

            google_status: str | None = None
            google_row = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == store.id)
                .first()
            )
            if google_row is not None:
                google_status = google_row.status

        whatsapp_count: int | None = None
        if self._whatsapp_port is not None:
            try:
                channels = self._whatsapp_port.list_for_store(
                    StoreRef(id=store.id)
                )
                whatsapp_count = len(channels)
            except Exception:
                whatsapp_count = None

        return StoreIntegrationHealth(
            store_id=store.id,
            slug=store.slug,
            pixel_connected=pixel_ok,
            meta_ads_connected=meta_ads_ok,
            google_status=google_status,
            whatsapp_channels=whatsapp_count,
        )
