"""Configuração da vitrine pública (WhatsApp do CTA do catálogo).

Dono/gerente definem o telefone livre gravado em ``estoque.lojas.whatsapp``.
Independente dos canais Evolution (atendimento/bot).
Gate: shell Revy Loja + módulo estoque.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter(tags=["revy-loja-catalogo"])

from app.auth import csrf_valido, usuario_atual  # noqa: E402
from app.clients.estoque import EstoqueClient, EstoqueIndisponivel  # noqa: E402
from app.config import revy_loja_shell_enabled  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.types import ROLES_GESTAO, Module  # noqa: E402
from app.main import (  # noqa: E402
    contexto,
    get_estoque_client,
    redirecionar_login,
    templates,
)
from app.web.loja_shell import check_module_access  # noqa: E402

_TELA = "/app/loja/catalogo"


def _autorizado(usuario) -> bool:
    return (getattr(usuario, "papel", "") or "").strip().casefold() in ROLES_GESTAO


def _para_app() -> RedirectResponse:
    return RedirectResponse("/app", status_code=303)


def _render(
    request: Request,
    usuario,
    db: Session,
    *,
    whatsapp: str = "",
    erro: str | None = None,
    mensagem: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "loja/catalogo.html",
        contexto(
            request,
            usuario,
            db,
            whatsapp=whatsapp or "",
            erro=erro,
            mensagem=mensagem,
        ),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.get(_TELA, response_class=HTMLResponse)
def loja_catalogo(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not revy_loja_shell_enabled() or not _autorizado(usuario):
        return _para_app()
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked

    whatsapp = ""
    erro = None
    try:
        dados = estoque.obter_loja()
        whatsapp = str(dados.get("whatsapp") or "")
    except EstoqueIndisponivel as exc:
        erro = str(exc) or "Não foi possível carregar o WhatsApp do catálogo."

    return _render(request, usuario, db, whatsapp=whatsapp, erro=erro)


@router.post(_TELA, response_class=HTMLResponse)
def loja_catalogo_salvar(
    request: Request,
    whatsapp: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if (
        not revy_loja_shell_enabled()
        or not _autorizado(usuario)
        or not csrf_valido(request, csrf)
    ):
        return _para_app()
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked

    valor = (whatsapp or "").strip()
    try:
        salva = estoque.atualizar_loja(whatsapp=valor or None)
        return _render(
            request,
            usuario,
            db,
            whatsapp=str(salva.get("whatsapp") or ""),
            mensagem="WhatsApp do catálogo atualizado.",
        )
    except EstoqueIndisponivel as exc:
        return _render(
            request,
            usuario,
            db,
            whatsapp=valor,
            erro=str(exc) or "Não foi possível salvar o WhatsApp do catálogo.",
            status_code=503,
        )
