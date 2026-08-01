from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models import ConviteAcessoLoja, Usuario, VinculoLojaPessoa, PessoaRevyProjetada, agora
from app.tokens import as_utc as _as_utc, token_hash as _token_hash

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

        pessoa = PessoaRevyProjetada(
            id=user.id,
            email=normalized_email,
            nome=normalized_name,
        )
        db.add(pessoa)
        db.flush()

        vinculo = VinculoLojaPessoa(
            pessoa_id=user.id,
            loja_slug=normalized_slug,
            cargo="dono",
            state="pendente",
            versao=0,
            atualizado_em=now,
        )
        db.add(vinculo)
    else:
        if user.papel != "dono":
            raise OwnerInvitationConflict("e-mail já possui acesso configurado")

        pessoa = db.query(PessoaRevyProjetada).filter(
            PessoaRevyProjetada.id == user.id
        ).first()
        if pessoa is None:
            pessoa = PessoaRevyProjetada(
                id=user.id,
                email=normalized_email,
                nome=normalized_name,
            )
            db.add(pessoa)
            db.flush()

        existing_vinculo = (
            db.query(VinculoLojaPessoa).filter(
                VinculoLojaPessoa.pessoa_id == user.id,
                VinculoLojaPessoa.loja_slug == normalized_slug,
                VinculoLojaPessoa.cargo == "dono",
            )
            .first()
        )

        if existing_vinculo is None:
            vinculo = VinculoLojaPessoa(
                pessoa_id=user.id,
                loja_slug=normalized_slug,
                cargo="dono",
                state="pendente" if not user.ativo else "ativo",
                versao=0,
                atualizado_em=now,
            )
            db.add(vinculo)
        else:
            existing_vinculo.state = "pendente" if not user.ativo else "ativo"
            existing_vinculo.atualizado_em = now

        if not user.ativo:
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
        store_slug=normalized_slug,
        token=token,
        expires_at=expires_at,
    )


def _find_active_invitation(
    db: Session, normalized_token: str, now: datetime
) -> ConviteAcessoLoja | None:
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
        return None
    return invitation


def owner_invitation_needs_password(db: Session, *, token: str) -> bool:
    """False quando o convite é para um dono já ativo (multiloja): ele já tem
    senha e a aceitação apenas confirma o novo vínculo. True nos demais casos
    (dono inativo, ou convite que o fluxo normal vai reportar como inválido)."""
    normalized_token = token.strip()
    if not normalized_token or len(normalized_token) > 256:
        return True
    invitation = _find_active_invitation(db, normalized_token, agora())
    if invitation is None:
        return True
    user = db.get(Usuario, invitation.usuario_id)
    return not (user is not None and user.ativo and user.papel == "dono")


def activate_owner_invitation(db: Session, *, token: str, password: str) -> Usuario:
    normalized_token = token.strip()
    if not normalized_token or len(normalized_token) > 256:
        raise OwnerInvitationInvalid("convite inválido ou expirado")
    now = agora()
    invitation = _find_active_invitation(db, normalized_token, now)
    if invitation is None:
        raise OwnerInvitationInvalid("convite inválido ou expirado")
    user = db.get(Usuario, invitation.usuario_id)
    if user is None or user.papel != "dono":
        raise OwnerInvitationInvalid("convite inválido ou expirado")
    if not user.ativo:
        # Primeiro acesso do dono: precisa definir a senha.
        if not 12 <= len(password) <= 256:
            raise OwnerInvitationInvalid("a senha deve ter entre 12 e 256 caracteres")
        user.senha_hash = hash_senha(password)
        user.ativo = True
    # Dono já ativo (multiloja): não altera a senha, apenas confirma o vínculo.
    invitation.usado_em = now
    db.query(VinculoLojaPessoa).filter(
        VinculoLojaPessoa.pessoa_id == user.id,
        VinculoLojaPessoa.cargo == "dono",
        VinculoLojaPessoa.state == "pendente",
    ).update(
        {VinculoLojaPessoa.state: "ativo", VinculoLojaPessoa.atualizado_em: now},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(user)
    return user
