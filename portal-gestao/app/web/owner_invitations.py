from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import csrf_token, csrf_valido
from app.config import settings
from app.db import get_db
from app.email import EmailMessage, send_email
from app.owner_invitations import (
    OwnerInvitationConflict,
    OwnerInvitationError,
    OwnerInvitationInvalid,
    activate_owner_invitation,
    issue_owner_invitation,
)

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


class OwnerInvitationBody(BaseModel):
    email: str
    nome: str
    loja_slug: str


def _expected_service_token() -> str:
    return (
        os.getenv("PORTAL_SERVICE_TOKEN")
        or os.getenv("PORTAL_PROVISIONING_TOKEN")
        or ""
    ).strip()


@router.post("/internal/v1/lojistas/convite")
def invite_owner_internal(
    body: OwnerInvitationBody,
    db: Session = Depends(get_db),
    x_service_token: str = Header(default="", alias="X-Service-Token"),
):
    expected = _expected_service_token()
    if not expected:
        return JSONResponse({"detail": "serviço de convites não configurado"}, status_code=503)
    if not secrets.compare_digest(x_service_token or "", expected):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)

    email_pendente = False
    try:
        invitation = issue_owner_invitation(
            db,
            email=body.email,
            name=body.nome,
            store_slug=body.loja_slug,
        )
    except OwnerInvitationConflict:
        # Conflito real: o e-mail já pertence a outro tipo de acesso (vendedor/gerente).
        # NÃO é um reenvio idempotente — o caso "dono já vinculado" retorna 200 acima.
        return JSONResponse(
            {"detail": "e-mail já pertence a outro tipo de acesso"},
            status_code=409,
        )
    except OwnerInvitationError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    link = settings.absolute_url(f"/convite/aceitar?token={invitation.token}")
    try:
        send_email(
            EmailMessage(
                to=invitation.email,
                subject="Seu acesso à Revy",
                text_body=(
                    f"Você foi convidado(a) como dono(a) da loja {invitation.store_slug}.\n"
                    f"Crie sua senha e acesse: {link}\n\nO link expira em 24 horas."
                ),
                html_body=(
                    f"<p>Você foi convidado(a) como dono(a) da loja "
                    f"<strong>{invitation.store_slug}</strong>.</p>"
                    f"<p><a href=\"{link}\">Criar minha senha e acessar</a></p>"
                    "<p>O link expira em 24 horas.</p>"
                ),
            )
        )
    except Exception:
        email_pendente = True

    result = {
        "usuario_id": invitation.user_id,
        "email": invitation.email,
        "loja_slug": invitation.store_slug,
        "expira_em": invitation.expires_at.isoformat(),
    }
    if email_pendente:
        result["email_pendente"] = True
    return result


@router.get("/convite/aceitar", response_class=HTMLResponse)
def accept_owner_invitation_page(
    request: Request,
    token: str = Query(default="", max_length=256),
):
    return templates.TemplateResponse(
        request=request,
        name="convite_aceitar.html",
        context={"csrf": csrf_token(request), "token": token, "erro": None},
    )


@router.post("/convite/aceitar", response_class=HTMLResponse)
async def accept_owner_invitation_submit(
    request: Request, db: Session = Depends(get_db)
):
    form = await request.form()
    token = (form.get("token") or "").strip()

    def render_error(message: str, status_code: int):
        return templates.TemplateResponse(
            request=request,
            name="convite_aceitar.html",
            context={"csrf": csrf_token(request), "token": token, "erro": message},
            status_code=status_code,
        )

    if not csrf_valido(request, form.get("csrf")):
        return render_error("Sessão expirada. Recarregue a página.", 403)
    password = form.get("senha") or ""
    confirmation = form.get("senha_confirmacao") or ""
    if password != confirmation:
        return render_error("As senhas não coincidem.", 422)
    try:
        activate_owner_invitation(db, token=token, password=password)
    except OwnerInvitationInvalid as exc:
        return render_error(str(exc), 422)
    return RedirectResponse("/login?ativado=1", status_code=303)
