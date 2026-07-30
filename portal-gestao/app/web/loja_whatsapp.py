"""Canais WhatsApp na Loja (Ajustes) — dono/gerente cadastram e pareiam números.

QR nunca vai a log nem a auditoria: vive só no request/response do conectar. A
sessão carrega apenas um token curto; o payload fica no store de `qr_efemero`,
porque um QR em base64 estouraria o limite de ~4 KB do cookie.
Gated por REVY_LOJA_SHELL_ENABLED + REVY_LOJA_WHATSAPP_ENABLED (default off).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import csrf_valido, usuario_atual  # noqa: E402
from app.clients.chatbot import ChatbotIndisponivel  # noqa: E402
from app.config import (  # noqa: E402
    revy_loja_shell_enabled,
    revy_loja_whatsapp_enabled,
)
from app.db import get_db  # noqa: E402
from app.loja import qr_efemero  # noqa: E402
from app.loja.types import ROLES_GESTAO  # noqa: E402
from app.loja.whatsapp_canais import ROTULOS, montar_canais_view  # noqa: E402
from app.loja_operacao_auditoria import registrar_auditoria_canal  # noqa: E402
from app.main import (  # noqa: E402
    contexto,
    get_chatbot_client,
    redirecionar_login,
    templates,
)

_TELA = "/app/loja/whatsapp"
# Erro genérico: nenhuma mensagem de canal carrega QR nem detalhe de provedor.
_ERRO_CHATBOT = "chatbot_indisponivel"


def _habilitado() -> bool:
    """Gate duplo, lido em runtime (Settings é snapshot de boot)."""
    return revy_loja_shell_enabled() and revy_loja_whatsapp_enabled()


def _autorizado(usuario) -> bool:
    return (getattr(usuario, "papel", "") or "").strip().casefold() in ROLES_GESTAO


def _para_app() -> RedirectResponse:
    return RedirectResponse("/app", status_code=303)


def _para_tela() -> RedirectResponse:
    return RedirectResponse(_TELA, status_code=303)


@router.get(_TELA, response_class=HTMLResponse)
def loja_whatsapp_canais(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or not _autorizado(usuario):
        return _para_app()

    canais, erro = None, None
    try:
        canais = chatbot.listar_canais_whatsapp()
    except ChatbotIndisponivel as exc:
        erro = str(exc)

    view = montar_canais_view(canais, erro=erro)
    return templates.TemplateResponse(
        "loja/whatsapp_canais.html",
        contexto(
            request,
            usuario,
            db,
            view=view,
            # QR só existe neste render; o token sai da sessão e o payload sai do
            # store, para não sobreviver ao reload.
            qr=qr_efemero.consumir(request.session.pop("canal_qr_token", None)),
            acao_erro=request.session.pop("canal_erro", None),
        ),
        headers={"Cache-Control": "no-store"},
    )


async def _guarda(request: Request, db: Session):
    """Devolve (usuario, form, resposta_de_erro) para as ações de escrita."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return None, None, redirecionar_login()
    form = await request.form()
    if (
        not _habilitado()
        or not _autorizado(usuario)
        or not csrf_valido(request, form.get("csrf"))
    ):
        return None, None, _para_app()
    return usuario, form, None


def _auditar(db: Session, usuario, acao: str, *, success: bool, error_code=None) -> None:
    registrar_auditoria_canal(
        db,
        loja_slug=usuario.loja_slug,
        acao=acao,
        ator_email=usuario.email,
        provedor="evolution",
        success=success,
        error_code=error_code,
        commit=True,
    )


@router.post("/app/loja/whatsapp/canais")
async def loja_whatsapp_criar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    label = (form.get("label") or "").strip()
    if not label:
        request.session["canal_erro"] = "Informe um nome para o número."
        return _para_tela()
    try:
        chatbot.registrar_canal_whatsapp(label)
        _auditar(db, usuario, "criar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "criar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/conectar")
async def loja_whatsapp_conectar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        resultado = chatbot.conectar_canal_whatsapp(canal_id)
        # Pareamento consumido no próximo GET. Nunca em log, nunca em auditoria.
        # Só o token curto vai para o cookie: o QR em base64 estouraria os ~4 KB.
        if resultado.get("qr_payload"):
            request.session["canal_qr_token"] = qr_efemero.guardar(
                canal_id, resultado["qr_payload"]
            )
        _auditar(db, usuario, "conectar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "conectar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/desconectar")
async def loja_whatsapp_desconectar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.desconectar_canal_whatsapp(canal_id)
        _auditar(db, usuario, "desconectar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "desconectar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/inativar")
async def loja_whatsapp_inativar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Remoção é lógica: o Chatbot marca ativo=False, o histórico fica."""
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.inativar_canal_whatsapp(canal_id)
        _auditar(db, usuario, "inativar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "inativar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.get("/app/loja/whatsapp/canais/{canal_id}/status")
def loja_whatsapp_status(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Rota fina para o polling enquanto há QR na tela (JSON, sem redirect)."""
    usuario = usuario_atual(request, db)
    if not usuario or not _habilitado() or not _autorizado(usuario):
        return JSONResponse({"erro": "nao_autorizado"}, status_code=403)
    try:
        dados = chatbot.obter_status_canal_whatsapp(canal_id)
    except ChatbotIndisponivel:
        return JSONResponse({"erro": "indisponivel"}, status_code=503)
    estado = str(dados.get("estado") or "pendente")
    return JSONResponse(
        {"estado": estado, "rotulo": ROTULOS.get(estado, estado)},
        headers={"Cache-Control": "no-store"},
    )
