"""Compat: /app/loja/catalogo redireciona para Números de WhatsApp.

O formulário do WhatsApp do catálogo vive em Ajustes → Números de WhatsApp.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter(tags=["revy-loja-catalogo"])

from app.auth import usuario_atual  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import redirecionar_login  # noqa: E402

_TELA_WHATSAPP = "/app/loja/whatsapp#catalogo-wa"


@router.get("/app/loja/catalogo")
@router.post("/app/loja/catalogo")
def loja_catalogo_redirect(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    return RedirectResponse(_TELA_WHATSAPP, status_code=303)
