from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import csrf_token, csrf_valido, gestor_atual, sessao_gestor
from app.config import settings
from app.control.access import AccessControl
from app.control.audit import AuditTrail
from app.control.session import actor_from_user
from app.control.stores import StoreControl
from app.control.types import (
    ActiveResponsibleConflict,
    AuditQuery,
    ControlError,
    CreateStore,
    GrantTrafficAccess,
    InvalidStoreTransition,
    ManagerNotFound,
    RevokeTrafficAccess,
    StoreNotFound,
    StoreRef,
    StoreSlugConflict,
    StoreStatus,
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
    except InvalidStoreTransition as exc:
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
    status_code: int = 200,
):
    actor = actor_from_user(manager)
    try:
        store = StoreControl(SessionLocal).get(actor, StoreRef(id=loja_id))
        audit = AuditTrail(SessionLocal).list(
            actor,
            AuditQuery(store_id=loja_id, limit=100),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)

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
            "audit_events": audit.items,
            "store_statuses": tuple(StoreStatus),
            "is_admin": manager.papel == "admin",
            "ok": request.query_params.get("ok"),
            "erro": error,
        },
        status_code=status_code,
    )
