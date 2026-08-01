from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models import RedefinicaoSenha, Usuario, agora
from app.password_rules import validar_nova_senha
from app.tokens import as_utc, token_hash

_LIFETIME = timedelta(hours=24)
_REEMISSAO_MINIMA = timedelta(minutes=2)


class PasswordResetInvalid(ValueError):
    pass


@dataclass(frozen=True)
class IssuedReset:
    usuario_id: str
    email: str
    nome: str
    token: str
    expira_em: datetime


def issue_reset(db: Session, *, email: str) -> IssuedReset | None:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    user = db.query(Usuario).filter(Usuario.email == normalized).first()
    if user is None or not user.ativo:
        return None

    now = agora()
    recente = (
        db.query(RedefinicaoSenha)
        .filter(
            RedefinicaoSenha.usuario_id == user.id,
            RedefinicaoSenha.usado_em.is_(None),
            RedefinicaoSenha.revogado_em.is_(None),
            RedefinicaoSenha.criado_em > now - _REEMISSAO_MINIMA,
        )
        .first()
    )
    if recente is not None:
        return None  # rate limit: já há token pendente recente

    db.query(RedefinicaoSenha).filter(
        RedefinicaoSenha.usuario_id == user.id,
        RedefinicaoSenha.usado_em.is_(None),
        RedefinicaoSenha.revogado_em.is_(None),
    ).update({RedefinicaoSenha.revogado_em: now}, synchronize_session=False)

    token = secrets.token_urlsafe(32)
    expira_em = now + _LIFETIME
    db.add(
        RedefinicaoSenha(
            usuario_id=user.id,
            token_hash=token_hash(token),
            expira_em=expira_em,
            criado_em=now,
        )
    )
    db.commit()
    return IssuedReset(
        usuario_id=user.id,
        email=user.email,
        nome=user.nome,
        token=token,
        expira_em=expira_em,
    )


def consume_reset(db: Session, *, token: str, senha: str, confirmacao: str) -> Usuario:
    normalized_token = (token or "").strip()
    if not normalized_token or len(normalized_token) > 256:
        raise PasswordResetInvalid("link inválido ou expirado")
    now = agora()
    registro = (
        db.query(RedefinicaoSenha)
        .filter(
            RedefinicaoSenha.token_hash == token_hash(normalized_token),
            RedefinicaoSenha.usado_em.is_(None),
            RedefinicaoSenha.revogado_em.is_(None),
        )
        .first()
    )
    if registro is None or as_utc(registro.expira_em) <= now:
        raise PasswordResetInvalid("link inválido ou expirado")
    user = db.get(Usuario, registro.usuario_id)
    if user is None or not user.ativo:
        raise PasswordResetInvalid("link inválido ou expirado")
    # Levanta SenhaInvalida ANTES de consumir o token (form pode ser reenviado).
    senha_validada = validar_nova_senha(senha, confirmacao)
    user.senha_hash = hash_senha(senha_validada)
    registro.usado_em = now
    db.commit()
    db.refresh(user)
    return user
