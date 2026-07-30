"""Shell Revy Loja — injeção de nav, sessão multi-loja e gates de módulo."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import csrf_valido, usuario_atual
from app.config import (
    revy_loja_entitlements_enabled,
    revy_loja_shell_enabled,
)
from app.db import get_db
from app.loja import entitlements as ents_mod
from app.loja import identity, navigation
from app.loja.permissions import (
    LojaPermissionError,
    ModuloNaoContratado,
    SemAcessoLoja,
    require_module,
)
from app.loja.types import (
    ActorLoja,
    EntitlementState,
    Module,
    NavSection,
    StoreContext,
)

BRAND_NAME = "Revy Loja"

router = APIRouter(tags=["revy-loja-shell"])


def _actor_for(usuario: Any, control_memberships=None) -> ActorLoja:
    return identity.actor_from_usuario(usuario, memberships=control_memberships)


def resolve_store_and_entitlements(
    request: Request,
    usuario: Any,
    db: Session | None = None,
    *,
    control_memberships=None,
    control_entitlements: EntitlementState | None = None,
) -> tuple[StoreContext, EntitlementState, ActorLoja]:
    actor = _actor_for(usuario, control_memberships)
    store = identity.resolve_store_context(
        actor, identity.session_loja_slug(request.session)
    )
    ents = ents_mod.resolve_entitlements(
        store.loja_slug,
        store.roles,
        entitlements_enabled=revy_loja_entitlements_enabled(),
        db=db,
        control_entitlements=control_entitlements,
    )
    # Alinha loja_state com entitlement real quando flag on
    if revy_loja_entitlements_enabled():
        store = StoreContext(
            loja_slug=store.loja_slug,
            roles=store.roles,
            loja_state="ativa" if ents.loja_ativa else "suspensa",
        )
    return store, ents, actor


def build_loja_nav(
    store: StoreContext,
    entitlements: EntitlementState,
) -> tuple[NavSection, ...]:
    if not revy_loja_shell_enabled():
        return ()
    return navigation.build_nav(store, entitlements, shell_enabled=True)


def template_extras(
    request: Request,
    usuario: Any,
    db: Session | None = None,
    **_kwargs,
) -> dict[str, Any]:
    """Extras de template quando o shell está ligado; dict vazio se desligado."""
    if not revy_loja_shell_enabled() or usuario is None:
        return {}
    try:
        store, ents, actor = resolve_store_and_entitlements(request, usuario, db)
    except SemAcessoLoja:
        return {
            "loja_shell": True,
            "loja_brand": BRAND_NAME,
            "loja_nav": (),
            "lojas_disponiveis": (),
            "store_context": None,
            "entitlements": None,
        }
    nav = build_loja_nav(store, ents)
    return {
        "loja_shell": True,
        "loja_brand": BRAND_NAME,
        "loja_nav": nav,
        "lojas_disponiveis": identity.available_store_slugs(actor),
        "store_context": store,
        "entitlements": ents,
    }


def check_module_access(
    request: Request,
    usuario: Any,
    db: Session,
    module: Module | str,
) -> JSONResponse | HTMLResponse | None:
    """Retorna resposta 403 se entitlements on e módulo bloqueado; senão None.

    Com flag de entitlements desligada → sempre None (comportamento legado).
    """
    if not revy_loja_entitlements_enabled():
        return None
    try:
        _store, ents, _actor = resolve_store_and_entitlements(request, usuario, db)
        require_module(ents, module)
    except ModuloNaoContratado as exc:
        return _forbidden(request, str(exc.message))
    except LojaPermissionError as exc:
        return _forbidden(request, str(exc.message))
    return None


def _forbidden(request: Request, detail: str) -> HTMLResponse:
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"detail": detail}, status_code=403)  # type: ignore[return-value]
    html = (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        f"<title>403 — {BRAND_NAME}</title></head><body>"
        f"<h1>Acesso negado</h1><p>{detail}</p>"
        "<p><a href='/app'>Voltar</a></p></body></html>"
    )
    return HTMLResponse(html, status_code=403)


def redirecionar_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


# --- Rotas do shell (seleção multi-loja; overviews em loja_vendas/estoque/routes) ---


@router.post("/app/loja/selecionar")
async def loja_selecionar(
    request: Request,
    db: Session = Depends(get_db),
):
    """Troca a loja ativa na sessão (multi-loja)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app?erro=csrf", status_code=303)
    actor = _actor_for(usuario)
    # Em F1 o Control port pode enriquecer memberships; cutover usa só Usuario.
    # Testes injetam memberships extras via monkeypatch de actor se necessário.
    try:
        # memberships multi-loja podem vir de request.state (testes / futuro Control)
        extra = getattr(request.state, "loja_memberships", None)
        if extra is not None:
            actor = identity.actor_from_usuario(usuario, memberships=extra)
        slug = identity.select_store_slug(actor, str(form.get("loja_slug") or ""))
    except SemAcessoLoja:
        return RedirectResponse("/app?erro=loja-nao-autorizada", status_code=303)
    request.session[identity.SESSION_LOJA_KEY] = slug
    return RedirectResponse("/app", status_code=303)


def ensure_session_loja(request: Request, usuario: Any) -> None:
    """Garante loja_slug na sessão a partir do Usuario quando ainda vazio."""
    if identity.session_loja_slug(request.session):
        return
    slug = str(getattr(usuario, "loja_slug", "") or "").strip()
    if slug:
        request.session[identity.SESSION_LOJA_KEY] = slug
