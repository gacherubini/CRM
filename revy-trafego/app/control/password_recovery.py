from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.auth import hash_senha
from app.control.audit import _append_event
from app.control.types import (
    AccessDenied,
    Actor,
    ConsumeControlPasswordRecovery,
    ControlAccountConflict,
    ControlAccountStatus,
    ControlRecoveryInvalid,
    IssueControlPasswordRecovery,
    IssuedControlPasswordRecovery,
    RecoveredControlAccount,
    WeakControlPassword,
)
from app.models import (
    AcessoControl,
    GestorRevy,
    Pessoa,
    RecuperacaoSenhaControl,
    agora,
)

_RECOVERY_LIFETIME = timedelta(hours=1)
_MINIMUM_PASSWORD_LENGTH = 12
_MAXIMUM_PASSWORD_LENGTH = 256


class ControlPasswordRecovery:
    """Recuperação administrativa de senha sem expor a credencial existente."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def issue(
        self,
        actor: Actor,
        command: IssueControlPasswordRecovery,
    ) -> IssuedControlPasswordRecovery:
        if not actor.is_admin:
            raise AccessDenied(
                "somente Admin Revy pode emitir recuperação de senha"
            )

        raw_token = secrets.token_urlsafe(32)
        now = agora()
        expires_at = now + _RECOVERY_LIFETIME
        with self._session_factory() as db:
            access = db.get(AcessoControl, command.access_id)
            if access is None:
                raise ControlAccountConflict("Acesso Control não encontrado")
            if (
                access.estado
                not in {
                    ControlAccountStatus.ACTIVE.value,
                    ControlAccountStatus.DISABLED.value,
                }
                or not access.senha_hash
                or not access.gestor_legado_id
            ):
                raise ControlAccountConflict(
                    "o acesso ainda não possui credencial recuperável"
                )
            person = db.get(Pessoa, access.pessoa_id)
            manager = db.get(GestorRevy, access.gestor_legado_id)
            if person is None or manager is None:
                raise ControlAccountConflict(
                    "o acesso não possui identidade compatível para recuperação"
                )

            (
                db.query(RecuperacaoSenhaControl)
                .filter(
                    RecuperacaoSenhaControl.acesso_id == access.id,
                    RecuperacaoSenhaControl.usado_em.is_(None),
                    RecuperacaoSenhaControl.revogado_em.is_(None),
                )
                .update(
                    {RecuperacaoSenhaControl.revogado_em: now},
                    synchronize_session=False,
                )
            )
            recovery = RecuperacaoSenhaControl(
                acesso_id=access.id,
                token_hash=_token_hash(raw_token),
                expira_em=expires_at,
                criado_por_gestor_id=actor.id,
                criado_em=now,
            )
            db.add(recovery)
            _append_event(
                db,
                actor=actor,
                store_id=None,
                action="control_password_recovery.issued",
                resource_type="acesso_control",
                resource_id=access.id,
                after={
                    "person_id": person.id,
                    "status": access.estado,
                },
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ControlAccountConflict(
                    "não foi possível emitir a recuperação de senha"
                ) from exc
            return IssuedControlPasswordRecovery(
                access_id=access.id,
                person_email=person.email,
                token=raw_token,
                expires_at=expires_at,
            )

    def consume(
        self,
        command: ConsumeControlPasswordRecovery,
    ) -> RecoveredControlAccount:
        password = command.password
        if not _MINIMUM_PASSWORD_LENGTH <= len(password) <= _MAXIMUM_PASSWORD_LENGTH:
            raise WeakControlPassword(
                "a senha deve ter entre 12 e 256 caracteres"
            )

        now = agora()
        with self._session_factory() as db:
            recovery = (
                db.query(RecuperacaoSenhaControl)
                .filter(
                    RecuperacaoSenhaControl.token_hash
                    == _token_hash(command.token.strip()),
                    RecuperacaoSenhaControl.usado_em.is_(None),
                    RecuperacaoSenhaControl.revogado_em.is_(None),
                )
                .with_for_update()
                .first()
            )
            if recovery is None or _as_utc(recovery.expira_em) <= now:
                raise ControlRecoveryInvalid(
                    "recuperação de senha inválida ou expirada"
                )

            access = db.get(AcessoControl, recovery.acesso_id)
            if (
                access is None
                or access.estado
                not in {
                    ControlAccountStatus.ACTIVE.value,
                    ControlAccountStatus.DISABLED.value,
                }
                or not access.gestor_legado_id
            ):
                raise ControlRecoveryInvalid(
                    "recuperação de senha inválida ou expirada"
                )
            person = db.get(Pessoa, access.pessoa_id)
            manager = db.get(GestorRevy, access.gestor_legado_id)
            if person is None or manager is None:
                raise ControlRecoveryInvalid(
                    "recuperação de senha inválida ou expirada"
                )

            password_hash = hash_senha(password)
            previous_version = access.sessao_versao
            access.senha_hash = password_hash
            access.sessao_versao = previous_version + 1
            access.atualizada_em = now
            manager.senha_hash = password_hash
            manager.ativo = access.estado == ControlAccountStatus.ACTIVE.value
            recovery.usado_em = now
            _append_event(
                db,
                actor=Actor(
                    id=manager.id,
                    email=manager.email,
                    name=manager.nome,
                    role=manager.papel,
                ),
                store_id=None,
                action="control_password_recovery.consumed",
                resource_type="acesso_control",
                resource_id=access.id,
                before={"session_version": previous_version},
                after={"session_version": access.sessao_versao},
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ControlRecoveryInvalid(
                    "recuperação de senha inválida ou expirada"
                ) from exc
            return RecoveredControlAccount(
                access_id=access.id,
                person_email=person.email,
                status=ControlAccountStatus(access.estado),
            )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
