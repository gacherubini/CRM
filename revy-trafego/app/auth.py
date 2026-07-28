from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import GestorRevy

_hasher = PasswordHasher()


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
    return gestor


def gestor_atual(request: Request, db: Session) -> GestorRevy | None:
    gestor_id = request.session.get("gestor_id")
    if not gestor_id:
        return None
    gestor = db.get(GestorRevy, gestor_id)
    return gestor if gestor and gestor.ativo else None


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
    db.commit()
    db.refresh(gestor)
    return gestor
