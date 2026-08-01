from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import csrf_token, csrf_valido
from app.config import settings
from app.db import get_db
from app.email import EmailMessage, send_email
from app.password_reset import PasswordResetInvalid, consume_reset, issue_reset
from app.password_rules import SenhaInvalida

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)

_NEUTRO = "Se houver uma conta com esse e-mail, enviamos um link para redefinir a senha."


@router.get("/senha/esqueci", response_class=HTMLResponse)
def esqueci_pagina(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="senha_esqueci.html",
        context={"csrf": csrf_token(request), "erro": None, "mensagem": None},
    )


@router.post("/senha/esqueci", response_class=HTMLResponse)
def esqueci_enviar(
    request: Request,
    email: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    if not csrf_valido(request, csrf):
        return templates.TemplateResponse(
            request=request,
            name="senha_esqueci.html",
            context={
                "csrf": csrf_token(request),
                "erro": "Sessão expirada. Recarregue a página.",
                "mensagem": None,
            },
            status_code=400,
        )
    resultado = issue_reset(db, email=email)
    if resultado is not None:
        link = settings.absolute_url(f"/senha/redefinir?token={resultado.token}")
        try:
            send_email(
                EmailMessage(
                    to=resultado.email,
                    subject="Redefinir sua senha da Revy",
                    text_body=(
                        "Recebemos um pedido para redefinir sua senha.\n"
                        f"Crie uma nova senha: {link}\n\n"
                        "O link expira em 24 horas. Se não foi você, ignore este e-mail."
                    ),
                    html_body=(
                        "<p>Recebemos um pedido para redefinir sua senha.</p>"
                        f"<p><a href=\"{link}\">Criar uma nova senha</a></p>"
                        "<p>O link expira em 24 horas. Se não foi você, ignore este e-mail.</p>"
                    ),
                )
            )
        except Exception:
            logger.exception(
                "falha ao enviar e-mail de redefinição de senha para %s",
                resultado.email,
            )
    # Resposta sempre neutra (anti-enumeração), com ou sem envio.
    return templates.TemplateResponse(
        request=request,
        name="senha_esqueci.html",
        context={"csrf": csrf_token(request), "erro": None, "mensagem": _NEUTRO},
    )


@router.get("/senha/redefinir", response_class=HTMLResponse)
def redefinir_pagina(
    request: Request, token: str = Query(default="", max_length=256)
):
    return templates.TemplateResponse(
        request=request,
        name="senha_redefinir.html",
        context={"csrf": csrf_token(request), "token": token, "erro": None},
    )


@router.post("/senha/redefinir", response_class=HTMLResponse)
def redefinir_enviar(
    request: Request,
    token: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    senha_confirmacao: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    def erro(msg: str, code: int):
        return templates.TemplateResponse(
            request=request,
            name="senha_redefinir.html",
            context={"csrf": csrf_token(request), "token": token, "erro": msg},
            status_code=code,
        )

    if not csrf_valido(request, csrf):
        return erro("Sessão expirada. Recarregue a página.", 403)
    try:
        consume_reset(db, token=token, senha=senha, confirmacao=senha_confirmacao)
    except SenhaInvalida as exc:
        return erro(str(exc), 422)
    except PasswordResetInvalid as exc:
        return erro(str(exc), 422)
    return RedirectResponse("/login?senha_redefinida=1", status_code=303)
