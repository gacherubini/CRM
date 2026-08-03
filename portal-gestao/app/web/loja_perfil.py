"""Perfil do usuário logado — dados da conta e troca de senha (própria).

Disponível a qualquer usuário autenticado (dono, gerente, vendedor, etc.).
Não depende de REVY_LOJA_SHELL_ENABLED: a UI legada também pode acessar
via redirect de /conta/senha ou link no header.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter(tags=["revy-loja-perfil"])

from app.auth import (  # noqa: E402
    csrf_valido,
    hash_senha,
    usuario_atual,
    verifica_senha,
)
from app.db import get_db  # noqa: E402
from app.main import (  # noqa: E402
    PAPEIS_EQUIPE_ROTULO,
    contexto,
    redirecionar_login,
    templates,
)
from app.models import Usuario  # noqa: E402
from app.password_rules import SenhaInvalida, validar_nova_senha  # noqa: E402

_TELA = "/app/loja/perfil"
_POST_SENHA = "/app/loja/perfil/senha"


def aplicar_troca_senha(
    usuario: Usuario,
    *,
    senha_atual: str,
    senha: str,
    senha_confirmacao: str,
) -> str | None:
    """Valida e aplica hash da nova senha no objeto usuário (sem commit).

    Retorna mensagem de erro em PT-BR ou None em caso de sucesso.
    """
    if not verifica_senha(usuario.senha_hash, senha_atual):
        return "Senha atual incorreta."
    try:
        senha_validada = validar_nova_senha(senha, senha_confirmacao)
    except SenhaInvalida as exc:
        return str(exc)
    usuario.senha_hash = hash_senha(senha_validada)
    return None


def _render_perfil(
    request: Request,
    usuario: Usuario,
    db: Session,
    *,
    erro: str | None = None,
    mensagem: str | None = None,
    status_code: int = 200,
):
    papel = (usuario.papel or "").strip().casefold()
    return templates.TemplateResponse(
        "loja/perfil.html",
        contexto(
            request,
            usuario,
            db,
            erro=erro,
            mensagem=mensagem,
            papel_rotulo=PAPEIS_EQUIPE_ROTULO.get(papel, usuario.papel or "—"),
        ),
        status_code=status_code,
    )


@router.get(_TELA, response_class=HTMLResponse)
def loja_perfil(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    return _render_perfil(request, usuario, db)


@router.post(_POST_SENHA, response_class=HTMLResponse)
def loja_perfil_senha_salvar(
    request: Request,
    senha_atual: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    senha_confirmacao: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not csrf_valido(request, csrf):
        return _render_perfil(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página.",
            status_code=400,
        )
    erro = aplicar_troca_senha(
        usuario,
        senha_atual=senha_atual,
        senha=senha,
        senha_confirmacao=senha_confirmacao,
    )
    if erro:
        return _render_perfil(request, usuario, db, erro=erro, status_code=400)
    db.commit()
    return _render_perfil(
        request, usuario, db, mensagem="Senha alterada com sucesso."
    )
