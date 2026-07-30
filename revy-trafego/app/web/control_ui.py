from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import csrf_token, csrf_valido, gestor_atual, sessao_gestor
from app.config import settings
from app.control.access import AccessControl
from app.control.accounts import ControlAccounts
from app.control.audit import AuditTrail
from app.control.contracts import (
    ContractBillingStatus,
    ContractControl,
    ContractNotFound,
    UpsertContract,
)
from app.control.dashboard import DashboardControl
from app.control.google_ads import (
    GoogleAdsConnectionNotFound,
    GoogleAdsOAuthMisconfigured,
    GoogleAdsOAuthStateInvalid,
    GoogleAdsTokenExchangeError,
)
from app.control.google_ads_conversions import GoogleAdsInvalidConversionBinding
from app.control.google_ads_metrics import (
    GoogleAdsAccountNotFound,
    GoogleAdsManagerAccountNotSelectable,
    GoogleAdsNotConnected,
)
from app.control.people import PeopleDirectory
from app.control.portfolio import (
    InvalidModuleSelection,
    ModuleCode,
    ModuleStatus,
    PortfolioConflict,
    PortfolioControl,
)
from app.control.roles import StoreRoles
from app.control.session import actor_from_user
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    ActiveResponsibleConflict,
    AssignStoreRole,
    AuditQuery,
    ControlError,
    CreateStore,
    GrantTrafficAccess,
    InvalidPersonEmail,
    InvalidStoreTransition,
    ManagerNotFound,
    PersonEmailConflict,
    PersonNotFound,
    PersonRef,
    RegisterPerson,
    RevokeStoreRole,
    RevokeTrafficAccess,
    StoreNotFound,
    StoreReadinessBlocked,
    StoreRef,
    StoreSlugConflict,
    StoreStatus,
    StoreRole,
    StoreRoleConflict,
    StoreRoleNotFound,
    StoreRoleRef,
    TrafficLinkConflict,
    TrafficLinkNotFound,
    TrafficRole,
    TransitionStore,
)
from app.db import SessionLocal, get_db
from app.models import GoogleAdsOAuthState

# redirect_uri registrado no Google Cloud Console (GOOGLE_ADS_OAUTH_REDIRECT_URI)
# deve apontar para esta rota HTML; o endpoint JSON equivalente
# (/control/v1/google-ads/oauth/callback) segue existindo para compatibilidade.
GOOGLE_ADS_OAUTH_CALLBACK_PATH = "/app/control/google-ads/oauth/callback"

router = APIRouter(tags=["control-ui"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


def _public_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{settings.url_prefix}{normalized}" if settings.url_prefix else normalized


templates.env.globals["public_path"] = _public_path


def _format_brl(value: Decimal) -> str:
    try:
        amount = Decimal(value)
        if not amount.is_finite():
            return "—"
        formatted = f"{amount:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "—"
    integer, decimal = formatted.split(".")
    return f"R$ {integer.replace(',', '.')},{decimal}"


def _dashboard_surface_enabled() -> bool:
    return (
        settings.revy_control_enabled
        and settings.revy_control_dashboard_enabled
    )


def _google_ads_surface_enabled() -> bool:
    """Superfície Google Ads do Control: flag do produto + flag do módulo."""
    return settings.revy_control_enabled and settings.google_ads_sync_enabled


def _google_oauth_configured() -> bool:
    """Credenciais da operação Google presentes (evita adapter Fake em produção)."""
    return bool(
        settings.google_ads_oauth_client_id
        and settings.google_ads_oauth_client_secret
        and settings.google_ads_oauth_redirect_uri
        and settings.google_ads_developer_token
    )


def _google_conversions_surface_enabled() -> bool:
    return (
        _google_ads_surface_enabled()
        and settings.google_conversions_enabled
    )


@router.get("/app/control/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _dashboard_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return RedirectResponse(_public_path("/login"), status_code=303)

    actor = actor_from_user(manager)
    user = sessao_gestor(request, db)
    assert user is not None
    stores = AccessControl(SessionLocal).scope(actor)
    nav_stores = (
        stores
        if settings.revy_control_rbac_enabled
        else [item.store.slug for item in stores]
    )
    overview = DashboardControl(SessionLocal).overview(actor)
    items = overview.items
    integration_by_store = {
        item.store_id: item for item in overview.integrations
    }
    google_by_store = None
    if settings.google_ads_sync_enabled:
        from app.web.control import _dashboard_google_by_store

        google_by_store = _dashboard_google_by_store(overview)
    return templates.TemplateResponse(
        request=request,
        name="control/dashboard.html",
        context={
            "usuario": user,
            "csrf": csrf_token(request),
            "lojas": nav_stores,
            "control_enabled": settings.revy_control_enabled,
            "control_rbac_enabled": settings.revy_control_rbac_enabled,
            "control_dashboard_enabled": True,
            "google_ads_sync_enabled": settings.google_ads_sync_enabled,
            "items": items,
            "overview": overview,
            "integration_by_store": integration_by_store,
            "google_by_store": google_by_store,
        },
    )


@router.get("/app/control/lojas", response_class=HTMLResponse)
def list_stores_page(
    request: Request,
    db: Session = Depends(get_db),
):
    if not settings.revy_control_enabled:
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return RedirectResponse(_public_path("/login"), status_code=303)
    return _render_stores_page(request, db, manager)


@router.get("/app/control/acessos", response_class=HTMLResponse)
def list_control_accounts_page(
    request: Request,
    db: Session = Depends(get_db),
):
    if not settings.revy_control_enabled:
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return RedirectResponse(_public_path("/login"), status_code=303)
    if manager.papel != "admin":
        return HTMLResponse(
            "<h1>Acesso negado</h1>"
            "<p>Você não tem permissão para consultar acessos do Control.</p>",
            status_code=403,
        )

    actor = actor_from_user(manager)
    user = sessao_gestor(request, db)
    assert user is not None
    stores = AccessControl(SessionLocal).scope(actor)
    nav_stores = (
        stores
        if settings.revy_control_rbac_enabled
        else [item.store.slug for item in stores]
    )
    accounts = ControlAccounts(SessionLocal).list(actor)
    return templates.TemplateResponse(
        request=request,
        name="control/acessos.html",
        context={
            "usuario": user,
            "csrf": csrf_token(request),
            "lojas": nav_stores,
            "control_enabled": settings.revy_control_enabled,
            "control_rbac_enabled": settings.revy_control_rbac_enabled,
            "control_dashboard_enabled": _dashboard_surface_enabled(),
            "accounts": accounts,
        },
    )


@router.post("/app/control/lojas", response_class=HTMLResponse)
async def create_store_page(
    request: Request,
    db: Session = Depends(get_db),
):
    if not settings.revy_control_enabled:
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return RedirectResponse(_public_path("/login"), status_code=303)
    if manager.papel != "admin":
        return HTMLResponse(
            "<h1>Acesso negado</h1><p>Você não tem permissão para criar lojas.</p>",
            status_code=403,
        )

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return HTMLResponse(
            "<h1>Requisição negada</h1><p>Token CSRF inválido.</p>",
            status_code=403,
        )

    name = (form.get("nome") or "").strip()
    slug = (form.get("slug") or "").strip().lower()
    form_values = {"nome": name, "slug": slug}
    if (
        not name
        or len(name) > 160
        or len(slug) > 120
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
    ):
        return _render_stores_page(
            request,
            db,
            manager,
            error="Informe um nome e um slug canônico para a Loja.",
            form_values=form_values,
            status_code=422,
        )

    try:
        StoreControl(SessionLocal).create(
            actor_from_user(manager),
            CreateStore(name=name, slug=slug),
        )
    except StoreSlugConflict:
        return _render_stores_page(
            request,
            db,
            manager,
            error="Já existe uma Loja com esse slug.",
            form_values=form_values,
            status_code=409,
        )
    except ControlError:
        return HTMLResponse(
            "<h1>Não foi possível criar a Loja</h1><p>Revise os dados e tente novamente.</p>",
            status_code=409,
        )
    return RedirectResponse(
        _public_path("/app/control/lojas?created=1"),
        status_code=303,
    )


@router.get("/app/control/lojas/{loja_id}", response_class=HTMLResponse)
def store_detail_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not settings.revy_control_enabled:
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return RedirectResponse(_public_path("/login"), status_code=303)
    return _render_store_detail(request, db, manager, loja_id)


@router.post(
    "/app/control/lojas/{loja_id}/modulos",
    response_class=HTMLResponse,
)
async def configure_store_modules_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    try:
        PortfolioControl(SessionLocal).configure(
            actor_from_user(manager),
            StoreRef(id=loja_id),
            tuple(form.getlist("modulos")),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except InvalidModuleSelection:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Selecione ao menos um módulo para a Loja.",
            status_code=422,
        )
    except PortfolioConflict:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível configurar os módulos da Loja.",
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "modulos"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/contrato",
    response_class=HTMLResponse,
)
async def configure_store_contract_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    form_values = {
        "valor_mensal": (form.get("valor_mensal") or "").strip(),
        "vigencia_inicio": (form.get("vigencia_inicio") or "").strip(),
        "vigencia_fim": (form.get("vigencia_fim") or "").strip(),
        "vencimento_dia": (form.get("vencimento_dia") or "").strip(),
        "situacao_cobranca": (
            form.get("situacao_cobranca") or ""
        ).strip(),
    }
    try:
        if not re.fullmatch(
            r"[0-9]{1,10}(?:\.[0-9]{1,2})?",
            form_values["valor_mensal"],
        ):
            raise ValueError
        monthly_amount = Decimal(form_values["valor_mensal"])
        if not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
            form_values["vigencia_inicio"],
        ):
            raise ValueError
        starts_on = date.fromisoformat(form_values["vigencia_inicio"])
        ends_on = None
        if form_values["vigencia_fim"]:
            if not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                form_values["vigencia_fim"],
            ):
                raise ValueError
            ends_on = date.fromisoformat(form_values["vigencia_fim"])
        if ends_on is not None and ends_on < starts_on:
            raise ValueError
        if not re.fullmatch(r"[0-9]{1,2}", form_values["vencimento_dia"]):
            raise ValueError
        due_day = int(form_values["vencimento_dia"])
        if not 1 <= due_day <= 31:
            raise ValueError
        billing_status = ContractBillingStatus(
            form_values["situacao_cobranca"]
        )
        ContractControl(SessionLocal).upsert(
            actor_from_user(manager),
            UpsertContract(
                store=StoreRef(id=loja_id),
                monthly_amount=monthly_amount,
                starts_on=starts_on,
                ends_on=ends_on,
                due_day=due_day,
                billing_status=billing_status,
            ),
        )
    except (InvalidOperation, ValueError):
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Revise os dados do contrato da Loja.",
            contract_form_values=form_values,
            status_code=422,
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    return RedirectResponse(
        _detail_path(loja_id, "contrato"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/cargos",
    response_class=HTMLResponse,
)
async def assign_store_role_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    email = (form.get("email") or "").strip()
    name = (form.get("nome") or "").strip()
    role_value = (form.get("cargo") or "").strip()
    form_values = {"email": email, "nome": name, "cargo": role_value}
    try:
        role = StoreRole(role_value)
    except ValueError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Selecione um cargo válido para a Loja.",
            person_form_values=form_values,
            status_code=422,
        )
    if len(name) > 160:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="O nome da Pessoa Revy deve ter até 160 caracteres.",
            person_form_values=form_values,
            status_code=422,
        )

    actor = actor_from_user(manager)
    try:
        StoreControl(SessionLocal).get(actor, StoreRef(id=loja_id))
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    people = PeopleDirectory(SessionLocal)
    try:
        person = people.find_by_email(actor, email)
    except InvalidPersonEmail:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Informe um e-mail válido para a Pessoa Revy.",
            person_form_values=form_values,
            status_code=422,
        )
    if person is None:
        if not name:
            return _render_store_detail(
                request,
                db,
                manager,
                loja_id,
                error="Informe o nome para cadastrar uma nova Pessoa Revy.",
                person_form_values=form_values,
                status_code=422,
            )
        try:
            person = people.register(
                actor,
                RegisterPerson(name=name, email=email),
            )
        except PersonEmailConflict:
            return _render_store_detail(
                request,
                db,
                manager,
                loja_id,
                error="Já existe uma Pessoa Revy com esse e-mail.",
                person_form_values=form_values,
                status_code=409,
            )

    try:
        StoreRoles(SessionLocal).assign(
            actor,
            AssignStoreRole(
                store=StoreRef(id=loja_id),
                person=PersonRef(id=person.id),
                role=role,
            ),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except PersonNotFound:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Pessoa Revy não encontrada.",
            person_form_values=form_values,
            status_code=404,
        )
    except StoreRoleConflict:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Essa pessoa já possui esse cargo ativo na Loja.",
            person_form_values=form_values,
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "cargo"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/cargos/{cargo_id}/revogar",
    response_class=HTMLResponse,
)
async def revoke_store_role_page(
    loja_id: str,
    cargo_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    try:
        StoreRoles(SessionLocal).revoke(
            actor_from_user(manager),
            RevokeStoreRole(
                store=StoreRef(id=loja_id),
                assignment=StoreRoleRef(id=cargo_id),
                reason=(form.get("motivo") or "").strip() or None,
            ),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except StoreRoleNotFound:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Cargo ativo não encontrado na Loja.",
            status_code=404,
        )
    except StoreReadinessBlocked as exc:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error=str(exc),
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "cargo_revogado"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/estado",
    response_class=HTMLResponse,
)
async def transition_store_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()
    try:
        target = StoreStatus((form.get("estado") or "").strip())
    except ValueError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Selecione um estado válido para a Loja.",
            status_code=422,
        )
    try:
        StoreControl(SessionLocal).transition(
            actor_from_user(manager),
            TransitionStore(
                store=StoreRef(id=loja_id),
                target=target,
                reason=(form.get("motivo") or "").strip() or None,
            ),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except (InvalidStoreTransition, StoreReadinessBlocked) as exc:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error=str(exc),
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "estado"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/gestores",
    response_class=HTMLResponse,
)
async def grant_traffic_access_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()
    manager_id = (form.get("gestor_id") or "").strip()
    try:
        role = TrafficRole((form.get("tipo") or "").strip())
    except ValueError:
        role = None
    if not manager_id or len(manager_id) > 36 or role is None:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Informe um ID de gestor e um tipo de vínculo válidos.",
            status_code=422,
        )
    try:
        AccessControl(SessionLocal).grant(
            actor_from_user(manager),
            GrantTrafficAccess(
                store=StoreRef(id=loja_id),
                manager_id=manager_id,
                role=role,
            ),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except ManagerNotFound:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Gestor não encontrado ou inativo.",
            status_code=404,
        )
    except (ActiveResponsibleConflict, TrafficLinkConflict) as exc:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error=str(exc),
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "gestor"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/gestores/revogar",
    response_class=HTMLResponse,
)
@router.post(
    "/app/control/lojas/{loja_id}/gestores/{gestor_id}/revogar",
    response_class=HTMLResponse,
)
async def revoke_traffic_access_page(
    loja_id: str,
    request: Request,
    gestor_id: str | None = None,
    db: Session = Depends(get_db),
):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()
    manager_id = (gestor_id or form.get("gestor_id") or "").strip()
    if not manager_id or len(manager_id) > 36:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Informe um ID de gestor válido para revogar.",
            status_code=422,
        )
    try:
        AccessControl(SessionLocal).revoke(
            actor_from_user(manager),
            RevokeTrafficAccess(
                store=StoreRef(id=loja_id),
                manager_id=manager_id,
                reason=(form.get("motivo") or "").strip() or None,
            ),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except TrafficLinkNotFound:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Vínculo de tráfego ativo não encontrado.",
            status_code=404,
        )
    return RedirectResponse(
        _detail_path(loja_id, "revogado"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/google-ads/oauth/start",
    response_class=HTMLResponse,
)
async def start_google_ads_oauth_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _google_ads_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()
    if not _google_oauth_configured():
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Google Ads não está configurado neste ambiente.",
            status_code=409,
        )

    from app.web.control import _google_ads_control

    try:
        result = _google_ads_control().start_oauth(
            actor_from_user(manager),
            StoreRef(id=loja_id),
        )
    except AccessDenied:
        return _access_denied()
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except (GoogleAdsOAuthMisconfigured, ControlError):
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível iniciar a conexão com o Google Ads.",
            status_code=409,
        )
    return RedirectResponse(result.auth_url, status_code=303)


@router.post(
    "/app/control/lojas/{loja_id}/google-ads/desconectar",
    response_class=HTMLResponse,
)
async def disconnect_google_ads_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _google_ads_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    from app.web.control import _google_ads_control

    try:
        _google_ads_control().disconnect(
            actor_from_user(manager),
            StoreRef(id=loja_id),
        )
    except AccessDenied:
        return _access_denied()
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except GoogleAdsConnectionNotFound:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="A Loja não possui conexão Google Ads para desconectar.",
            status_code=404,
        )
    except ControlError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível desconectar o Google Ads.",
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "google_desconectado"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/google-ads/accounts/sync",
    response_class=HTMLResponse,
)
async def sync_google_ads_accounts_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _google_ads_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    from app.web.control import _google_ads_metrics_control

    try:
        _google_ads_metrics_control().sync_accounts(
            actor_from_user(manager),
            StoreRef(id=loja_id),
        )
    except AccessDenied:
        return _access_denied()
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except GoogleAdsNotConnected:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Conecte o Google Ads antes de sincronizar as contas.",
            status_code=409,
        )
    except ControlError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível sincronizar as contas do Google Ads.",
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "google_contas_sincronizadas"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/google-ads/accounts/select",
    response_class=HTMLResponse,
)
async def select_google_ads_account_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _google_ads_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()
    customer_id = (form.get("customer_id") or "").strip()
    if not customer_id or len(customer_id) > 20:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Selecione uma conta anunciante do Google Ads.",
            status_code=422,
        )

    from app.web.control import _google_ads_metrics_control

    try:
        _google_ads_metrics_control().select_account(
            actor_from_user(manager),
            StoreRef(id=loja_id),
            customer_id,
        )
    except AccessDenied:
        return _access_denied()
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except GoogleAdsManagerAccountNotSelectable:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Conta gerenciadora (MCC) não pode ser selecionada.",
            status_code=422,
        )
    except GoogleAdsAccountNotFound:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Conta Google Ads não encontrada para esta Loja.",
            status_code=404,
        )
    except ControlError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível selecionar a conta do Google Ads.",
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "google_conta_selecionada"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/google-ads/conversion-bindings",
    response_class=HTMLResponse,
)
async def bind_google_ads_conversion_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _google_conversions_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    event_type = (form.get("revy_event_type") or "").strip()
    resource_name = (
        form.get("conversion_action_resource_name") or ""
    ).strip()
    customer_id = (form.get("customer_id") or "").strip()
    if (
        not event_type
        or len(event_type) > 80
        or not resource_name
        or len(resource_name) > 240
        or not customer_id
        or len(customer_id) > 20
    ):
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Selecione o evento Revy e uma ação de conversão válida.",
            status_code=422,
        )

    from app.web.control import _google_ads_conversions_control

    try:
        _google_ads_conversions_control().bind_conversion_action(
            actor_from_user(manager),
            StoreRef(id=loja_id),
            revy_event_type=event_type,
            conversion_action_resource_name=resource_name,
            customer_id=customer_id,
            active=True,
        )
    except AccessDenied:
        return _access_denied()
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except GoogleAdsInvalidConversionBinding:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível validar o vínculo de conversão.",
            status_code=422,
        )
    except ControlError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível vincular a ação de conversão.",
            status_code=409,
        )
    return RedirectResponse(
        _detail_path(loja_id, "google_conversao_vinculada"),
        status_code=303,
    )


@router.post(
    "/app/control/lojas/{loja_id}/google-ads/metrics/sync",
    response_class=HTMLResponse,
)
async def sync_google_ads_metrics_page(
    loja_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _google_ads_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    date_from = (form.get("date_from") or "").strip()
    date_to = (form.get("date_to") or "").strip()
    try:
        parsed_from = date.fromisoformat(date_from)
        parsed_to = date.fromisoformat(date_to)
        if parsed_from > parsed_to:
            raise ValueError
    except ValueError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Informe um período válido para sincronizar as métricas.",
            status_code=422,
        )

    from app.web.control import _google_ads_metrics_control

    try:
        _google_ads_metrics_control().sync_metrics(
            actor_from_user(manager),
            StoreRef(id=loja_id),
            date_from=date_from,
            date_to=date_to,
        )
    except AccessDenied:
        return _access_denied()
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except GoogleAdsNotConnected:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Conecte o Google Ads antes de sincronizar as métricas.",
            status_code=409,
        )
    except ControlError:
        return _render_store_detail(
            request,
            db,
            manager,
            loja_id,
            error="Não foi possível sincronizar as métricas do Google Ads.",
            status_code=409,
        )
    return RedirectResponse(
        _public_path(
            f"/app/control/lojas/{loja_id}"
            f"?ok=google_metricas_sincronizadas"
            f"&date_from={date_from}&date_to={date_to}"
        ),
        status_code=303,
    )


@router.get(GOOGLE_ADS_OAUTH_CALLBACK_PATH, response_class=HTMLResponse)
def google_ads_oauth_callback_page(
    request: Request,
    state: str = Query(default="", max_length=128),
    code: str = Query(default="", max_length=512),
    error: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    """Callback OAuth do Google em HTML — é aqui que um humano volta do consent.

    O `loja_id` sai da connection devolvida por `complete_oauth` (resolvida a
    partir do `state`): o Google não permite variar o `redirect_uri`, então não
    há parâmetro extra na URL. O endpoint JSON equivalente em
    `app/web/control.py` continua existindo para compatibilidade.
    """
    if not _google_ads_surface_enabled():
        return HTMLResponse("Página não encontrada.", status_code=404)
    manager, denied = _actor_for_store_mutation(request, db)
    if denied is not None:
        return denied
    if not _google_oauth_configured():
        return _google_oauth_failure(
            request,
            db,
            manager,
            state,
            "Google Ads não está configurado neste ambiente.",
        )
    if error:
        return _google_oauth_failure(
            request,
            db,
            manager,
            state,
            "Autorização do Google não concluída. Tente conectar novamente.",
        )

    from app.web.control import _google_ads_control

    try:
        connection = _google_ads_control().complete_oauth(state=state, code=code)
    except AccessDenied:
        return _access_denied()
    except GoogleAdsOAuthStateInvalid:
        return _google_oauth_failure(
            request,
            db,
            manager,
            state,
            "Link de conexão do Google expirado ou já utilizado. "
            "Comece a conexão novamente.",
        )
    except (GoogleAdsTokenExchangeError, GoogleAdsOAuthMisconfigured, ControlError):
        return _google_oauth_failure(
            request,
            db,
            manager,
            state,
            "O Google não confirmou a autorização. Tente conectar novamente.",
        )
    return RedirectResponse(
        _detail_path(connection.loja_id, "google_conectado"),
        status_code=303,
    )


def _render_stores_page(
    request: Request,
    db: Session,
    manager,
    *,
    error: str | None = None,
    form_values: dict[str, str] | None = None,
    status_code: int = 200,
):
    user = sessao_gestor(request, db)
    assert user is not None
    stores = AccessControl(SessionLocal).scope(actor_from_user(manager))
    nav_stores = (
        stores
        if settings.revy_control_rbac_enabled
        else [item.store.slug for item in stores]
    )
    return templates.TemplateResponse(
        request=request,
        name="control/lojas.html",
        context={
            "usuario": user,
            "csrf": csrf_token(request),
            "lojas": nav_stores,
            "control_enabled": settings.revy_control_enabled,
            "control_rbac_enabled": settings.revy_control_rbac_enabled,
            "control_dashboard_enabled": _dashboard_surface_enabled(),
            "stores": stores,
            "is_admin": manager.papel == "admin",
            "created": request.query_params.get("created") == "1",
            "erro": error,
            "form_values": form_values or {"nome": "", "slug": ""},
        },
        status_code=status_code,
    )


def _admin_for_mutation(request: Request, db: Session):
    if not settings.revy_control_enabled:
        return None, HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return None, RedirectResponse(_public_path("/login"), status_code=303)
    if manager.papel != "admin":
        return None, _access_denied()
    return manager, None


def _actor_for_store_mutation(request: Request, db: Session):
    """Gate de mutação de Loja sem exigir Admin Revy.

    Igual a `_admin_for_mutation` menos o bloqueio por papel: quem decide se um
    gestor pode agir na Loja é o domínio, num lugar só
    (`_assert_can_manage_connection` em `app/control/google_ads.py`, que aceita
    Admin Revy ou Gestor Responsável e recusa colaborador com `AccessDenied`).
    Handlers que usam este gate devem capturar `AccessDenied` e devolver
    `_access_denied()`. `_admin_for_mutation` segue valendo para os handlers
    que são de admin por natureza.
    """
    if not settings.revy_control_enabled:
        return None, HTMLResponse("Página não encontrada.", status_code=404)
    manager = gestor_atual(request, db)
    if manager is None:
        return None, RedirectResponse(_public_path("/login"), status_code=303)
    return manager, None


def _access_denied(
    mensagem: str = "Você não tem permissão para alterar esta Loja.",
) -> HTMLResponse:
    """403 padrão do Control (mesma página para gate e para `AccessDenied`)."""
    return HTMLResponse(
        f"<h1>Acesso negado</h1><p>{escape(mensagem)}</p>",
        status_code=403,
    )


def _csrf_denied() -> HTMLResponse:
    return HTMLResponse(
        "<h1>Requisição negada</h1><p>Token CSRF inválido.</p>",
        status_code=403,
    )


def _google_oauth_state_store_id(state: str) -> str | None:
    """Loja do state OAuth — leitura só para escolher onde mostrar o banner.

    Validação (expiração, consumo) permanece em `complete_oauth`; aqui não há
    decisão de autorização nem de fluxo.
    """
    value = (state or "").strip()
    if not value or len(value) > 128:
        return None
    with SessionLocal() as db:
        row = (
            db.query(GoogleAdsOAuthState)
            .filter(GoogleAdsOAuthState.state == value)
            .first()
        )
        return row.loja_id if row is not None else None


def _google_oauth_failure(
    request: Request,
    db: Session,
    manager,
    state: str,
    mensagem: str,
    *,
    status_code: int = 400,
):
    """Banner de erro no detalhe da Loja; página avulsa quando o state não resolve."""
    loja_id = _google_oauth_state_store_id(state)
    if loja_id is None:
        return HTMLResponse(
            "<h1>Conexão com o Google Ads não concluída</h1>"
            f"<p>{escape(mensagem)}</p>"
            f'<p><a href="{escape(_public_path("/app/control/lojas"))}">'
            "Voltar para as Lojas</a></p>",
            status_code=status_code,
        )
    return _render_store_detail(
        request,
        db,
        manager,
        loja_id,
        error=mensagem,
        status_code=status_code,
    )


def _detail_path(loja_id: str, success: str) -> str:
    return _public_path(f"/app/control/lojas/{loja_id}?ok={success}")


def _google_metrics_period(request: Request) -> tuple[str, str]:
    today = date.today()
    default_from = today - timedelta(days=6)
    raw_from = request.query_params.get("date_from")
    raw_to = request.query_params.get("date_to")
    try:
        date_from = date.fromisoformat(raw_from) if raw_from else default_from
        date_to = date.fromisoformat(raw_to) if raw_to else today
        if date_from > date_to:
            raise ValueError
    except ValueError:
        date_from = default_from
        date_to = today
    return date_from.isoformat(), date_to.isoformat()


def _render_store_detail(
    request: Request,
    db: Session,
    manager,
    loja_id: str,
    *,
    error: str | None = None,
    person_form_values: dict[str, str] | None = None,
    contract_form_values: dict[str, str] | None = None,
    status_code: int = 200,
):
    actor = actor_from_user(manager)
    store_ref = StoreRef(id=loja_id)
    try:
        store = StoreControl(SessionLocal).get(actor, store_ref)
        modules = PortfolioControl(SessionLocal).list_modules(actor, store_ref)
        audit = AuditTrail(SessionLocal).list(
            actor,
            AuditQuery(store_id=loja_id, limit=100),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    try:
        contract = ContractControl(SessionLocal).get(actor, store_ref)
    except ContractNotFound:
        contract = None
    if contract_form_values is None:
        contract_form_values = (
            {
                "valor_mensal": f"{contract.monthly_amount:.2f}",
                "vigencia_inicio": contract.starts_on.isoformat(),
                "vigencia_fim": (
                    contract.ends_on.isoformat()
                    if contract.ends_on is not None
                    else ""
                ),
                "vencimento_dia": str(contract.due_day),
                "situacao_cobranca": contract.billing_status.value,
            }
            if contract is not None
            else {
                "valor_mensal": "",
                "vigencia_inicio": "",
                "vigencia_fim": "",
                "vencimento_dia": "",
                "situacao_cobranca": ContractBillingStatus.CURRENT.value,
            }
        )

    store_people = ()
    if manager.papel == "admin":
        roles = StoreRoles(SessionLocal).list_for_store(
            actor,
            StoreRef(id=loja_id),
        )
        people = PeopleDirectory(SessionLocal)
        store_people = tuple(
            {
                "person": people.get(actor, PersonRef(id=role.person_id)),
                "role": role,
            }
            for role in roles
        )

    google_connection = None
    google_accounts = ()
    google_conversion_actions = ()
    google_conversion_bindings = ()
    google_metrics_summary = None
    google_metrics_date_from, google_metrics_date_to = _google_metrics_period(
        request
    )
    if _google_ads_surface_enabled() and _google_oauth_configured():
        from app.web.control import (
            _google_ads_control,
            _google_ads_metrics_control,
        )

        try:
            google_connection = _google_ads_control().get(actor, store_ref)
        except GoogleAdsConnectionNotFound:
            pass
        except ControlError:
            pass
        if google_connection is not None and google_connection.has_refresh_token:
            try:
                google_accounts = _google_ads_metrics_control().list_accounts(
                    actor,
                    store_ref,
                )
            except ControlError:
                pass

    google_has_selected_account = any(
        account.selected and not account.is_manager
        for account in google_accounts
    )
    google_selected_account = next(
        (
            account
            for account in google_accounts
            if account.selected and not account.is_manager
        ),
        None,
    )
    if (
        _google_conversions_surface_enabled()
        and google_selected_account is not None
    ):
        from app.web.control import (
            _google_ads_conversions_control,
            _google_ads_metrics_control,
        )

        try:
            google_conversion_actions = (
                _google_ads_metrics_control().list_conversion_actions(
                    actor,
                    store_ref,
                )
            )
            google_conversion_bindings = (
                _google_ads_conversions_control().list_bindings(
                    actor,
                    store_ref,
                )
            )
        except ControlError:
            pass
    if google_selected_account is not None:
        from app.web.control import _google_ads_metrics_control

        try:
            google_metrics_summary = (
                _google_ads_metrics_control().metrics_summary(
                    actor,
                    store_ref,
                    date_from=google_metrics_date_from,
                    date_to=google_metrics_date_to,
                )
            )
        except ControlError:
            pass
    google_next_step = None
    if google_connection is None or not google_connection.has_refresh_token:
        google_next_step = "connection"
    elif not google_has_selected_account:
        google_next_step = "account"

    user = sessao_gestor(request, db)
    assert user is not None
    stores = AccessControl(SessionLocal).scope(actor)
    nav_stores = (
        stores
        if settings.revy_control_rbac_enabled
        else [item.store.slug for item in stores]
    )
    return templates.TemplateResponse(
        request=request,
        name="control/loja_detail.html",
        context={
            "usuario": user,
            "csrf": csrf_token(request),
            "lojas": nav_stores,
            "control_enabled": settings.revy_control_enabled,
            "control_rbac_enabled": settings.revy_control_rbac_enabled,
            "control_dashboard_enabled": _dashboard_surface_enabled(),
            "google_ads_enabled": _google_ads_surface_enabled(),
            "google_oauth_configured": _google_oauth_configured(),
            "google_connection": google_connection,
            "google_accounts": google_accounts,
            "google_selected_account": google_selected_account,
            "google_next_step": google_next_step,
            "google_conversions_enabled": (
                _google_conversions_surface_enabled()
            ),
            "google_conversion_actions": google_conversion_actions,
            "google_conversion_bindings": google_conversion_bindings,
            "google_revy_event_types": ("venda_confirmada",),
            "google_metrics_summary": google_metrics_summary,
            "google_metrics_date_from": google_metrics_date_from,
            "google_metrics_date_to": google_metrics_date_to,
            "google_metrics_cost_brl": (
                _format_brl(google_metrics_summary.cost)
                if google_metrics_summary is not None
                else None
            ),
            "google_metrics_impressions": (
                f"{google_metrics_summary.impressions:,}".replace(",", ".")
                if google_metrics_summary is not None
                else None
            ),
            "google_metrics_conversions": (
                f"{google_metrics_summary.conversions:f}".rstrip("0").rstrip(".")
                if google_metrics_summary is not None
                else None
            ),
            "store": store,
            "modules": modules,
            "module_options": tuple(ModuleCode),
            "active_module_codes": frozenset(
                module.code.value
                for module in modules
                if module.status == ModuleStatus.ACTIVE
            ),
            "contract": contract,
            "contract_statuses": tuple(ContractBillingStatus),
            "contract_form_values": contract_form_values,
            "contract_amount_brl": (
                _format_brl(contract.monthly_amount)
                if contract is not None
                else None
            ),
            "audit_events": audit.items,
            "store_statuses": tuple(StoreStatus),
            "store_roles": tuple(StoreRole),
            "store_people": store_people,
            "is_admin": manager.papel == "admin",
            "ok": request.query_params.get("ok"),
            "erro": error,
            "person_form_values": person_form_values
            or {"email": "", "nome": "", "cargo": StoreRole.SELLER.value},
        },
        status_code=status_code,
    )
