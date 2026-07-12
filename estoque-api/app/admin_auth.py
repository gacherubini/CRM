import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request
from sqlalchemy.orm import Session

from app.models_db import Loja, UsuarioEstoque

_hasher = PasswordHasher()


def hash_senha(senha: str) -> str:
    if len(senha) < 10:
        raise ValueError("a senha deve ter pelo menos 10 caracteres")
    return _hasher.hash(senha)


def verificar_senha(senha_hash: str, senha: str) -> bool:
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerifyMismatchError, InvalidHashError):
        return False


def autenticar(db: Session, loja_slug: str, email: str, senha: str) -> UsuarioEstoque | None:
    email = email.strip().lower()
    usuario = (
        db.query(UsuarioEstoque)
        .join(Loja, Loja.id == UsuarioEstoque.loja_id)
        .filter(
            Loja.slug == loja_slug.strip().lower(),
            UsuarioEstoque.email == email,
            UsuarioEstoque.ativo.is_(True),
        )
        .first()
    )
    return usuario if usuario and verificar_senha(usuario.senha_hash, senha) else None


def usuario_atual(request: Request, db: Session) -> UsuarioEstoque | None:
    usuario_id = request.session.get("estoque_usuario_id")
    if not usuario_id:
        return None
    usuario = db.get(UsuarioEstoque, usuario_id)
    return usuario if usuario and usuario.ativo else None


def iniciar_sessao(request: Request, usuario: UsuarioEstoque) -> None:
    request.session.clear()
    request.session["estoque_usuario_id"] = usuario.id
    request.session["csrf"] = secrets.token_urlsafe(24)


def encerrar_sessao(request: Request) -> None:
    request.session.clear()


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


def csrf_valido(request: Request, enviado: str | None) -> bool:
    esperado = request.session.get("csrf")
    return bool(esperado and enviado and secrets.compare_digest(esperado, enviado))
