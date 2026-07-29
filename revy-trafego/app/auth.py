from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request
from sqlalchemy.orm import Session

from app.control.access_backfill import backfill_acessos_control
from app.models import AcessoControl, GestorRevy

_hasher = PasswordHasher()
_SESSION_VERSION_KEY = "sessao_versao"
_MANAGER_SESSION_VERSION_ATTR = "_control_session_version"


@dataclass
class SessaoGestor:
    """Contexto de UI: gestor + loja selecionada (compatível com templates de portal)."""

    id: str
    email: str
    nome: str
    papel: str
    loja_slug: str


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verifica_senha(hash_atual: str, senha: str) -> bool:
    try:
        return _hasher.verify(hash_atual, senha)
    except (VerifyMismatchError, InvalidHashError):
        return False


def autenticar(db: Session, email: str, senha: str) -> GestorRevy | None:
    gestor = db.query(GestorRevy).filter(GestorRevy.email == email.strip().lower()).first()
    if gestor is None or not gestor.ativo or not verifica_senha(gestor.senha_hash, senha):
        return None
    acesso = _acesso_projetado(db, gestor.id)
    if acesso is not None:
        if acesso.estado != "ativo":
            return None
        setattr(gestor, _MANAGER_SESSION_VERSION_ATTR, acesso.sessao_versao)
    return gestor


def gestor_atual(request: Request, db: Session) -> GestorRevy | None:
    gestor_id = request.session.get("gestor_id")
    if not gestor_id:
        return None
    gestor = db.get(GestorRevy, gestor_id)
    if gestor is None or not gestor.ativo:
        return None
    acesso = _acesso_projetado(db, gestor.id)
    if acesso is not None and acesso.estado != "ativo":
        return None
    if acesso is not None:
        session_version = request.session.get(_SESSION_VERSION_KEY)
        if session_version is None:
            if acesso.sessao_versao != 1:
                return None
        elif session_version != acesso.sessao_versao:
            return None
    return gestor


def loja_atual(request: Request) -> str | None:
    slug = (request.session.get("loja_slug") or "").strip()
    return slug or None


def sessao_gestor(request: Request, db: Session) -> SessaoGestor | None:
    gestor = gestor_atual(request, db)
    if not gestor:
        return None
    slug = loja_atual(request) or ""
    return SessaoGestor(
        id=gestor.id,
        email=gestor.email,
        nome=gestor.nome,
        papel=gestor.papel,
        loja_slug=slug,
    )


def iniciar_sessao(request: Request, gestor: GestorRevy) -> None:
    request.session.clear()
    request.session["gestor_id"] = gestor.id
    session_version = getattr(gestor, _MANAGER_SESSION_VERSION_ATTR, None)
    if session_version is not None:
        request.session[_SESSION_VERSION_KEY] = session_version
    request.session["csrf"] = secrets.token_urlsafe(24)


def definir_loja(request: Request, loja_slug: str) -> None:
    request.session["loja_slug"] = loja_slug.strip()


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


def bootstrap_gestor_se_vazio(db: Session, *, email: str, senha: str, nome: str) -> GestorRevy | None:
    if db.query(GestorRevy).count() > 0:
        try:
            backfill_acessos_control(db.connection())
            db.commit()
        except Exception:
            db.rollback()
            raise
        return None
    if not email or not senha:
        return None
    gestor = GestorRevy(
        email=email.strip().lower(),
        nome=(nome or "Equipe Tráfego").strip()[:160],
        senha_hash=hash_senha(senha),
        papel="admin",
        ativo=True,
    )
    db.add(gestor)
    try:
        db.flush()
        backfill_acessos_control(db.connection())
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(gestor)
    return gestor


def _acesso_projetado(db: Session, gestor_id: str) -> AcessoControl | None:
    return (
        db.query(AcessoControl)
        .filter(AcessoControl.gestor_legado_id == gestor_id)
        .first()
    )
