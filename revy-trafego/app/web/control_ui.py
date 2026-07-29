from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import csrf_token, csrf_valido, gestor_atual, sessao_gestor
from app.config import settings
from app.control.access import AccessControl
from app.control.accounts import ControlAccounts
from app.control.audit import AuditTrail
from app.control.contracts import ContractControl, ContractNotFound
from app.control.people import PeopleDirectory
from app.control.portfolio import PortfolioControl
from app.control.roles import StoreRoles
from app.control.session import actor_from_user
from app.control.stores import StoreControl
from app.control.types import (
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
        return None, HTMLResponse(
            "<h1>Acesso negado</h1><p>Você não tem permissão para alterar esta Loja.</p>",
            status_code=403,
        )
    return manager, None


def _csrf_denied() -> HTMLResponse:
    return HTMLResponse(
        "<h1>Requisição negada</h1><p>Token CSRF inválido.</p>",
        status_code=403,
    )


def _detail_path(loja_id: str, success: str) -> str:
    return _public_path(f"/app/control/lojas/{loja_id}?ok={success}")


def _render_store_detail(
    request: Request,
    db: Session,
    manager,
    loja_id: str,
    *,
    error: str | None = None,
    person_form_values: dict[str, str] | None = None,
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
            "store": store,
            "modules": modules,
            "contract": contract,
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
