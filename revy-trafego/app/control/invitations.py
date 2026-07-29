from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.auth import hash_senha
from app.control.audit import _append_event
from app.control.types import (
    AccessDenied,
    ActivateControlAccess,
    ActivatedControlAccount,
    Actor,
    ControlAccountConflict,
    ControlAccountRole,
    ControlAccountStatus,
    ControlInvitationInvalid,
    InviteControlAccess,
    IssuedControlInvitation,
    PersonNotFound,
    WeakControlPassword,
)
from app.models import (
    AcessoControl,
    ConviteAcessoControl,
    GestorRevy,
    Pessoa,
    agora,
)

_INVITATION_LIFETIME = timedelta(hours=24)
_MINIMUM_PASSWORD_LENGTH = 12
_MAXIMUM_PASSWORD_LENGTH = 256


class ControlInvitations:
    """Emissão e consumo de convites de acesso global ao Revy Control."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def issue(
        self,
        actor: Actor,
        command: InviteControlAccess,
    ) -> IssuedControlInvitation:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode emitir convites do Control")

        raw_token = secrets.token_urlsafe(32)
        now = agora()
        expires_at = now + _INVITATION_LIFETIME
        with self._session_factory() as db:
            person = db.get(Pessoa, command.person.id)
            if person is None:
                raise PersonNotFound("Pessoa Revy não encontrada")

            access = (
                db.query(AcessoControl)
                .filter(AcessoControl.pessoa_id == person.id)
                .first()
            )
            if access is None:
                access = AcessoControl(
                    pessoa_id=person.id,
                    papel=command.role.value,
                    estado=ControlAccountStatus.PENDING.value,
                    senha_hash=None,
                    sessao_versao=1,
                    gestor_legado_id=None,
                    criada_em=now,
                    atualizada_em=now,
                )
                db.add(access)
                db.flush()
            elif (
                access.estado != ControlAccountStatus.PENDING.value
                or access.gestor_legado_id is not None
                or access.senha_hash is not None
            ):
                raise ControlAccountConflict(
                    "a Pessoa Revy já possui acesso configurado no Control"
                )
            else:
                access.papel = command.role.value
                access.atualizada_em = now

            (
                db.query(ConviteAcessoControl)
                .filter(
                    ConviteAcessoControl.acesso_id == access.id,
                    ConviteAcessoControl.usado_em.is_(None),
                    ConviteAcessoControl.revogado_em.is_(None),
                )
                .update(
                    {ConviteAcessoControl.revogado_em: now},
                    synchronize_session=False,
                )
            )
            invitation = ConviteAcessoControl(
                acesso_id=access.id,
                token_hash=_token_hash(raw_token),
                expira_em=expires_at,
                criado_por_gestor_id=actor.id,
                criado_em=now,
            )
            db.add(invitation)
            _append_event(
                db,
                actor=actor,
                store_id=None,
                action="control_invitation.issued",
                resource_type="acesso_control",
                resource_id=access.id,
                after={
                    "person_id": person.id,
                    "role": command.role.value,
                    "status": ControlAccountStatus.PENDING.value,
                },
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ControlAccountConflict(
                    "não foi possível emitir o convite para esta Pessoa Revy"
                ) from exc
            return IssuedControlInvitation(
                access_id=access.id,
                person_email=person.email,
                token=raw_token,
                expires_at=expires_at,
            )

    def activate(
        self,
        command: ActivateControlAccess,
    ) -> ActivatedControlAccount:
        password = command.password
        if not _MINIMUM_PASSWORD_LENGTH <= len(password) <= _MAXIMUM_PASSWORD_LENGTH:
            raise WeakControlPassword(
                "a senha deve ter entre 12 e 256 caracteres"
            )

        now = agora()
        with self._session_factory() as db:
            invitation = (
                db.query(ConviteAcessoControl)
                .filter(
                    ConviteAcessoControl.token_hash
                    == _token_hash(command.token.strip()),
                    ConviteAcessoControl.usado_em.is_(None),
                    ConviteAcessoControl.revogado_em.is_(None),
                )
                .first()
            )
            if invitation is None or _as_utc(invitation.expira_em) <= now:
                raise ControlInvitationInvalid("convite inválido ou expirado")

            access = db.get(AcessoControl, invitation.acesso_id)
            if (
                access is None
                or access.estado != ControlAccountStatus.PENDING.value
                or access.gestor_legado_id is not None
                or access.senha_hash is not None
            ):
                raise ControlInvitationInvalid("convite inválido ou expirado")
            person = db.get(Pessoa, access.pessoa_id)
            if person is None:
                raise ControlInvitationInvalid("convite inválido ou expirado")

            existing_manager = (
                db.query(GestorRevy)
                .filter(
                    or_(
                        GestorRevy.id == access.id,
                        GestorRevy.email == person.email,
                    )
                )
                .first()
            )
            if existing_manager is not None:
                raise ControlInvitationInvalid("convite inválido ou expirado")

            password_hash = hash_senha(password)
            manager = GestorRevy(
                id=access.id,
                email=person.email,
                nome=person.nome,
                senha_hash=password_hash,
                papel=access.papel,
                ativo=True,
                criado_em=now,
            )
            db.add(manager)
            db.flush()
            access.senha_hash = password_hash
            access.estado = ControlAccountStatus.ACTIVE.value
            access.gestor_legado_id = manager.id
            access.atualizada_em = now
            invitation.usado_em = now
            _append_event(
                db,
                actor=Actor(
                    id=manager.id,
                    email=manager.email,
                    name=manager.nome,
                    role=manager.papel,
                ),
                store_id=None,
                action="control_access.activated",
                resource_type="acesso_control",
                resource_id=access.id,
                before={"status": ControlAccountStatus.PENDING.value},
                after={
                    "role": access.papel,
                    "status": ControlAccountStatus.ACTIVE.value,
                },
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ControlInvitationInvalid("convite inválido ou expirado") from exc
            return ActivatedControlAccount(
                access_id=access.id,
                person_email=person.email,
                role=ControlAccountRole(access.papel),
                status=ControlAccountStatus(access.estado),
            )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
