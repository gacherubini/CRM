from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models import ConviteAcessoLoja, Usuario, agora

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
_LIFETIME = timedelta(hours=24)


class OwnerInvitationError(ValueError):
    pass


class OwnerInvitationConflict(OwnerInvitationError):
    pass


class OwnerInvitationInvalid(OwnerInvitationError):
    pass


@dataclass(frozen=True)
class IssuedOwnerInvitation:
    user_id: str
    email: str
    name: str
    store_slug: str
    token: str
    expires_at: datetime


def issue_owner_invitation(
    db: Session, *, email: str, name: str, store_slug: str
) -> IssuedOwnerInvitation:
    normalized_email = email.strip().lower()
    normalized_name = " ".join(name.split())
    normalized_slug = store_slug.strip().lower()
    if not _EMAIL.fullmatch(normalized_email):
        raise OwnerInvitationError("e-mail inválido")
    if not normalized_name or len(normalized_name) > 160:
        raise OwnerInvitationError("nome inválido")
    if not _SLUG.fullmatch(normalized_slug):
        raise OwnerInvitationError("loja inválida")

    now = agora()
    user = db.query(Usuario).filter(Usuario.email == normalized_email).first()
    if user is None:
        user = Usuario(
            email=normalized_email,
            nome=normalized_name,
            senha_hash=hash_senha(secrets.token_urlsafe(32)),
            papel="dono",
            loja_slug=normalized_slug,
            ativo=False,
        )
        db.add(user)
        db.flush()
    else:
        if user.ativo or user.papel != "dono" or user.loja_slug != normalized_slug:
            raise OwnerInvitationConflict("e-mail já possui acesso configurado")
        previous = (
            db.query(ConviteAcessoLoja.id)
            .filter(ConviteAcessoLoja.usuario_id == user.id)
            .first()
        )
        if previous is None:
            raise OwnerInvitationConflict("e-mail já possui acesso configurado")
        user.nome = normalized_name

    db.query(ConviteAcessoLoja).filter(
        ConviteAcessoLoja.usuario_id == user.id,
        ConviteAcessoLoja.usado_em.is_(None),
        ConviteAcessoLoja.revogado_em.is_(None),
    ).update({ConviteAcessoLoja.revogado_em: now}, synchronize_session=False)

    token = secrets.token_urlsafe(32)
    expires_at = now + _LIFETIME
    db.add(
        ConviteAcessoLoja(
            usuario_id=user.id,
            token_hash=_token_hash(token),
            expira_em=expires_at,
            criado_em=now,
        )
    )
    db.commit()
    return IssuedOwnerInvitation(
        user_id=user.id,
        email=user.email,
        name=user.nome,
        store_slug=user.loja_slug,
        token=token,
        expires_at=expires_at,
    )


def activate_owner_invitation(db: Session, *, token: str, password: str) -> Usuario:
    if not 12 <= len(password) <= 256:
        raise OwnerInvitationInvalid("a senha deve ter entre 12 e 256 caracteres")
    normalized_token = token.strip()
    if not normalized_token or len(normalized_token) > 256:
        raise OwnerInvitationInvalid("convite inválido ou expirado")
    now = agora()
    invitation = (
        db.query(ConviteAcessoLoja)
        .filter(
            ConviteAcessoLoja.token_hash == _token_hash(normalized_token),
            ConviteAcessoLoja.usado_em.is_(None),
            ConviteAcessoLoja.revogado_em.is_(None),
        )
        .first()
    )
    if invitation is None or _as_utc(invitation.expira_em) <= now:
        raise OwnerInvitationInvalid("convite inválido ou expirado")
    user = db.get(Usuario, invitation.usuario_id)
    if user is None or user.ativo or user.papel != "dono":
        raise OwnerInvitationInvalid("convite inválido ou expirado")
    user.senha_hash = hash_senha(password)
    user.ativo = True
    invitation.usado_em = now
    db.commit()
    db.refresh(user)
    return user


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
