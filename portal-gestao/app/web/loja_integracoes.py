"""Painel de status das integrações na Loja (Ajustes) — dono/gerente.

Só status (Meta/Google/WhatsApp), não configuração: os badges consomem o
agregador do Revy Control via service token, mas **server-side** (o navegador do
dono/gerente fala só com o Portal; o token de serviço nunca vai ao browser). O
endpoint gestor do Control exige sessão de gestor — que o dono/gerente da Loja
não tem —, por isso o Portal usa a superfície service-token por slug.
Gated por REVY_LOJA_SHELL_ENABLED (default off).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import usuario_atual  # noqa: E402
from app.clients.revy_trafego import RevyTrafegoClient  # noqa: E402
from app.config import revy_loja_shell_enabled  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.types import ROLES_GESTAO  # noqa: E402
from app.main import contexto, redirecionar_login, templates  # noqa: E402

_TELA = "/app/loja/integracoes"
_HEALTH = "/app/loja/integracoes/health"


def _habilitado() -> bool:
    """Gate lido em runtime (Settings é snapshot de boot)."""
    return revy_loja_shell_enabled()


def _autorizado(usuario) -> bool:
    return (getattr(usuario, "papel", "") or "").strip().casefold() in ROLES_GESTAO


@router.get(_TELA, response_class=HTMLResponse)
def loja_integracoes(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or not _autorizado(usuario):
        return RedirectResponse("/app", status_code=303)
    # A página só monta o container + o JS; os dados vêm do endpoint abaixo, que
    # o JS busca no open e no "Testar agora". Nenhum dado sensível no HTML.
    return templates.TemplateResponse(
        "loja/integracoes.html",
        contexto(request, usuario, db),
        headers={"Cache-Control": "no-store"},
    )


@router.get(_HEALTH)
def loja_integracoes_health(
    request: Request,
    forcar: int = 0,
    db: Session = Depends(get_db),
):
    """Proxy server-side do agregador do Control (Meta/Google/WhatsApp).

    200 = JSON do agregador (mesmo contrato do Control, com `status=missing`
    quando algo não está configurado). 502 = Control offline/não configurado no
    Portal; o JS mostra o estado neutro "Não foi possível verificar agora".
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return JSONResponse({"detail": "não autenticado"}, status_code=401)
    if not _habilitado() or not _autorizado(usuario):
        return JSONResponse({"detail": "não autorizado"}, status_code=403)
    dados = RevyTrafegoClient().fetch_integracoes_health(
        loja_slug=usuario.loja_slug, forcar=bool(forcar)
    )
    if dados is None:
        return JSONResponse({"detail": "integrações indisponíveis"}, status_code=502)
    return JSONResponse(dados, headers={"Cache-Control": "no-store"})
