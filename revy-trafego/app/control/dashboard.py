from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import func

from app.control.audit import AuditTrail
from app.control.integrations import pixel_configured
from app.control.portfolio import ModuleCode, ModuleStatus
from app.control.readiness import StoreReadiness
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    AuditEventView,
    StoreRef,
    StoreStatus,
    StoreView,
    TrafficRole,
)
from app.meta_ads_spend import normalizar_ad_account_id
from app.models import (
    GestorRevy,
    GoogleAdsConnection,
    LojaModulo,
    MetaAdsConfig,
    MetaPixelConfig,
    ModuloRevy,
    VendaProjetada,
    VinculoTrafego,
)

_RECENT_AUDIT_LIMIT = 15
_GOOGLE_FAILURE_STATUSES = frozenset({"erro", "expirado", "revogado", "atencao"})


class _WhatsAppChannelsPort(Protocol):
    def list_for_store(self, store_ref: StoreRef) -> list[Any]: ...


class _LeadsCountPort(Protocol):
    def count_for_store(self, slug: str) -> int | None: ...


@dataclass(frozen=True)
class StorePerformance:
    store_id: str
    slug: str
    name: str
    vendas: int
    leads: int | None
    conversao: float | None


@dataclass(frozen=True)
class NetworkHighlights:
    melhor_loja_nome: str | None
    melhor_loja_vendas: int
    ticket_medio: Decimal | None


@dataclass(frozen=True)
class NetworkOverview:
    lojas_ativas: int
    lojas_total: int
    vendas_mes: int
    vendas_delta_pct: float | None
    ticket_medio: Decimal | None
    leads_rede: int | None
    por_loja: tuple[StorePerformance, ...]
    destaques: NetworkHighlights


@dataclass(frozen=True)
class ResponsibleManagerSummary:
    id: str
    name: str
    email: str


@dataclass(frozen=True)
class StoreModuleSummary:
    code: str
    name: str
    status: str


@dataclass(frozen=True)
class StoreReadinessSummary:
    store_id: str
    slug: str
    name: str
    status: StoreStatus
    ready: bool
    gestor_responsavel: ResponsibleManagerSummary | None = None
    modulos: tuple[StoreModuleSummary, ...] = ()
    integration_failures: tuple[str, ...] = ()


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
    failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class DashboardOverview:
    counts: DashboardCounts
    items: tuple[StoreReadinessSummary, ...]
    pending_readiness: tuple[PendingReadinessItem, ...]
    integrations: tuple[StoreIntegrationHealth, ...]
    recent_audit: tuple[AuditEventView, ...] = ()


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
        self._audit = AuditTrail(session_factory)
        self._whatsapp_port = whatsapp_port

    def summary(self, actor: Actor) -> tuple[StoreReadinessSummary, ...]:
        return self.overview(actor).items

    def overview(self, actor: Actor) -> DashboardOverview:
        """Visão admin (todas) ou gestor (somente lojas com vínculo)."""
        stores = self._stores.list(actor)
        store_ids = [store.id for store in stores]
        responsaveis = self._load_responsaveis(store_ids)
        modulos_por_loja = self._load_modulos(store_ids)

        items: list[StoreReadinessSummary] = []
        pending: list[PendingReadinessItem] = []
        integrations: list[StoreIntegrationHealth] = []
        ativas = 0
        em_configuracao = 0
        suspensas = 0
        erro = 0

        for store in stores:
            report = self._readiness.evaluate(actor, StoreRef(id=store.id))
            health = self._integration_health(store)
            items.append(
                StoreReadinessSummary(
                    store_id=store.id,
                    slug=store.slug,
                    name=store.name,
                    status=store.status,
                    ready=report.ready,
                    gestor_responsavel=responsaveis.get(store.id),
                    modulos=modulos_por_loja.get(store.id, ()),
                    integration_failures=health.failures,
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

            integrations.append(health)

        recent = self._audit.list_recent(actor, limit=_RECENT_AUDIT_LIMIT)

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
            recent_audit=recent.items,
        )

    def admin_overview(self, actor: Actor) -> DashboardOverview:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode ver overview global")
        return self.overview(actor)

    def gestor_overview(self, actor: Actor) -> DashboardOverview:
        """Alias semântico: overview já filtra pelo vínculo do gestor."""
        return self.overview(actor)

    def network_overview(
        self, actor: Actor, *, leads_port: _LeadsCountPort | None = None
    ) -> NetworkOverview:
        """KPIs de negócio no escopo do ator. Vendas/ticket de vendas_projetadas;
        leads do Chatbot (port injetado). Só lojas ativas entram em por_loja."""
        stores = self._stores.list(actor)
        ativas = [s for s in stores if s.status is StoreStatus.ACTIVE]
        ativa_ids = [s.id for s in ativas]

        agora = datetime.now(timezone.utc)
        inicio_mes = datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)
        fim_mes = (
            datetime(agora.year + 1, 1, 1, tzinfo=timezone.utc)
            if agora.month == 12
            else datetime(agora.year, agora.month + 1, 1, tzinfo=timezone.utc)
        )
        inicio_mes_ant = (inicio_mes - timedelta(days=1)).replace(day=1)

        vendas_por_loja: dict[str, int] = {}
        vendas_mes = 0
        ticket_medio: Decimal | None = None
        vendas_mes_ant = 0
        if ativa_ids:
            with self._session_factory() as db:
                for loja_id, count in (
                    db.query(VendaProjetada.loja_id, func.count(VendaProjetada.id))
                    .filter(
                        VendaProjetada.loja_id.in_(ativa_ids),
                        VendaProjetada.confirmada_em >= inicio_mes,
                        VendaProjetada.confirmada_em < fim_mes,
                    )
                    .group_by(VendaProjetada.loja_id)
                    .all()
                ):
                    vendas_por_loja[loja_id] = count
                total_count, total_avg = (
                    db.query(
                        func.count(VendaProjetada.id),
                        func.avg(VendaProjetada.preco_venda),
                    )
                    .filter(
                        VendaProjetada.loja_id.in_(ativa_ids),
                        VendaProjetada.confirmada_em >= inicio_mes,
                        VendaProjetada.confirmada_em < fim_mes,
                    )
                    .one()
                )
                vendas_mes = int(total_count or 0)
                ticket_medio = (
                    Decimal(total_avg).quantize(Decimal("0.01"))
                    if total_avg is not None
                    else None
                )
                vendas_mes_ant = int(
                    db.query(func.count(VendaProjetada.id))
                    .filter(
                        VendaProjetada.loja_id.in_(ativa_ids),
                        VendaProjetada.confirmada_em >= inicio_mes_ant,
                        VendaProjetada.confirmada_em < inicio_mes,
                    )
                    .scalar()
                    or 0
                )

        delta_pct: float | None = None
        if vendas_mes_ant > 0:
            delta_pct = round((vendas_mes - vendas_mes_ant) / vendas_mes_ant * 100, 1)

        por_loja: list[StorePerformance] = []
        leads_total = 0
        algum_lead = False
        for store in ativas:
            vendas = vendas_por_loja.get(store.id, 0)
            leads = leads_port.count_for_store(store.slug) if leads_port else None
            if leads is not None:
                algum_lead = True
                leads_total += leads
            conversao = (
                (vendas / leads) if (leads is not None and leads > 0) else None
            )
            por_loja.append(
                StorePerformance(
                    store_id=store.id,
                    slug=store.slug,
                    name=store.name,
                    vendas=vendas,
                    leads=leads,
                    conversao=conversao,
                )
            )

        leads_rede = leads_total if algum_lead else None
        melhor = max(por_loja, key=lambda p: p.vendas, default=None)
        destaques = NetworkHighlights(
            melhor_loja_nome=melhor.name if melhor and melhor.vendas > 0 else None,
            melhor_loja_vendas=melhor.vendas if melhor else 0,
            ticket_medio=ticket_medio,
        )
        return NetworkOverview(
            lojas_ativas=len(ativas),
            lojas_total=len(stores),
            vendas_mes=vendas_mes,
            vendas_delta_pct=delta_pct,
            ticket_medio=ticket_medio,
            leads_rede=leads_rede,
            por_loja=tuple(por_loja),
            destaques=destaques,
        )

    def _load_responsaveis(
        self, store_ids: list[str]
    ) -> dict[str, ResponsibleManagerSummary]:
        if not store_ids:
            return {}
        with self._session_factory() as db:
            rows = (
                db.query(VinculoTrafego, GestorRevy)
                .join(GestorRevy, GestorRevy.id == VinculoTrafego.gestor_id)
                .filter(
                    VinculoTrafego.loja_id.in_(store_ids),
                    VinculoTrafego.tipo == TrafficRole.RESPONSIBLE.value,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .all()
            )
            return {
                link.loja_id: ResponsibleManagerSummary(
                    id=manager.id,
                    name=manager.nome,
                    email=manager.email,
                )
                for link, manager in rows
            }

    def _load_modulos(
        self, store_ids: list[str]
    ) -> dict[str, tuple[StoreModuleSummary, ...]]:
        if not store_ids:
            return {}
        with self._session_factory() as db:
            rows = (
                db.query(LojaModulo, ModuloRevy)
                .join(ModuloRevy, ModuloRevy.id == LojaModulo.modulo_id)
                .filter(LojaModulo.loja_id.in_(store_ids))
                .order_by(ModuloRevy.codigo)
                .all()
            )
            by_store: dict[str, list[StoreModuleSummary]] = {
                store_id: [] for store_id in store_ids
            }
            for assignment, module in rows:
                # Aceita somente códigos do catálogo conhecido.
                try:
                    code = ModuleCode(module.codigo).value
                    status = ModuleStatus(assignment.estado).value
                except ValueError:
                    continue
                by_store.setdefault(assignment.loja_id, []).append(
                    StoreModuleSummary(
                        code=code,
                        name=module.nome,
                        status=status,
                    )
                )
            return {
                store_id: tuple(items) for store_id, items in by_store.items()
            }

    def _integration_health(self, store: StoreView) -> StoreIntegrationHealth:
        failures: list[str] = []
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
            if ads_row is not None and ads_row.ultima_sync_status == "erro":
                detail = (ads_row.ultima_sync_erro or "").strip()
                failures.append(
                    f"meta_ads_sync:{detail}" if detail else "meta_ads_sync"
                )

            pixel_row = (
                db.query(MetaPixelConfig)
                .filter(MetaPixelConfig.loja_id == store.id)
                .first()
            )
            if pixel_row is None:
                pixel_row = (
                    db.query(MetaPixelConfig)
                    .filter(MetaPixelConfig.loja_slug == store.slug)
                    .first()
                )
            if pixel_row is not None and not pixel_ok:
                failures.append("pixel_incomplete")

            google_status: str | None = None
            google_row = (
                db.query(GoogleAdsConnection)
                .filter(GoogleAdsConnection.loja_id == store.id)
                .first()
            )
            if google_row is not None:
                google_status = google_row.status
                if google_status in _GOOGLE_FAILURE_STATUSES:
                    failures.append(f"google:{google_status}")

        whatsapp_count: int | None = None
        if self._whatsapp_port is not None:
            try:
                channels = self._whatsapp_port.list_for_store(
                    StoreRef(id=store.id)
                )
                whatsapp_count = len(channels)
            except Exception:
                whatsapp_count = None
                failures.append("whatsapp_unavailable")

        return StoreIntegrationHealth(
            store_id=store.id,
            slug=store.slug,
            pixel_connected=pixel_ok,
            meta_ads_connected=meta_ads_ok,
            google_status=google_status,
            whatsapp_channels=whatsapp_count,
            failures=tuple(failures),
        )
