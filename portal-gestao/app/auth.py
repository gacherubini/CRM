from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Usuario

_hasher = PasswordHasher()


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verifica_senha(hash_atual: str, senha: str) -> bool:
    try:
        return _hasher.verify(hash_atual, senha)
    except (VerifyMismatchError, InvalidHashError):
        return False


def autenticar(db: Session, email: str, senha: str) -> Usuario | None:
    usuario = db.query(Usuario).filter(Usuario.email == email.strip().lower()).first()
    if usuario is None or not usuario.ativo or not verifica_senha(usuario.senha_hash, senha):
        return None
    return usuario


def usuario_atual(request: Request, db: Session) -> Usuario | None:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    usuario = db.get(Usuario, usuario_id)
    return usuario if usuario and usuario.ativo else None


def iniciar_sessao(request: Request, usuario: Usuario) -> None:
    request.session.clear()
    request.session["usuario_id"] = usuario.id
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


def pode_ver_custo(usuario: Usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "admin_plataforma"}


def pode_gerir_estoque(usuario: Usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "admin_plataforma"}


def pode_registrar_venda(usuario: Usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "vendedor"}


def pode_confirmar_venda(usuario: Usuario) -> bool:
    return usuario.papel in {"dono", "gerente"}


def pode_ver_financeiro(usuario: Usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "admin_plataforma"}


def pode_gerir_metas(usuario: Usuario) -> bool:
    return usuario.papel in {"dono", "gerente"}


def pode_gerir_financeiras(usuario: Usuario) -> bool:
    """Acessos de portais bancários: só dono/gerente (nunca vendedor)."""
    return usuario.papel in {"dono", "gerente"}


def pode_gerir_trafego(usuario: Usuario) -> bool:
    """UI técnica de tráfego (Pixel/CAPI/campanhas).

    A partir da separação Revy Tráfego, o dono **não** gerencia config no portal.
    Rollback: ``PORTAL_TRAFEGO_UI_LEGACY=1`` restaura o menu técnico para dono/gerente.
    """
    import os

    if os.getenv("PORTAL_TRAFEGO_UI_LEGACY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return usuario.papel in {"dono", "gerente"}
    return False


def pode_ver_resultados_midia(usuario: Usuario) -> bool:
    """Cards de resultados de mídia (gasto/leads/ROAS) — dono e gerente."""
    return usuario.papel in {"dono", "gerente", "admin_plataforma"}


def pode_gerir_equipe(usuario: Usuario) -> bool:
    """Cadastro e manutenção de acessos da loja — somente dono ou plataforma.

    Listagem operacional (sem mutação) usa ``pode_ver_equipe``.
    """
    return usuario.papel in {"dono", "admin_plataforma"}


def pode_ver_equipe(usuario: Usuario) -> bool:
    """Lista da equipe para contexto operacional (dono e gerente).

    Mutação de conta/cargo/senha continua restrita a ``pode_gerir_equipe``.
    """
    return usuario.papel in {"dono", "gerente", "admin_plataforma"}


def pode_ver_relatorios(usuario: Usuario) -> bool:
    """Relatórios/exportação CSV (vendas, metas, funil) — apenas dono e gerente."""
    return usuario.papel in {"dono", "gerente"}
