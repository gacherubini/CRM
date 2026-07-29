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
from app.control.session import actor_from_user
from app.control.stores import StoreControl
from app.control.types import ControlError, CreateStore, StoreSlugConflict
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
            "control_rbac_enabled": settings.revy_control_rbac_enabled,
            "stores": stores,
            "is_admin": manager.papel == "admin",
            "created": request.query_params.get("created") == "1",
            "erro": error,
            "form_values": form_values or {"nome": "", "slug": ""},
        },
        status_code=status_code,
    )
