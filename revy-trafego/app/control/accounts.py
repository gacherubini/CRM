from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.control.audit import _append_event
from app.control.types import (
    AccessDenied,
    Actor,
    ControlAccountConflict,
    ControlAccountRole,
    ControlAccountStatus,
    ControlAccountView,
    PersonNotFound,
)
from app.models import AcessoControl, GestorRevy, Pessoa, agora


class ControlAccounts:
    """Leitura administrativa dos acessos globais ao Revy Control."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def list(self, actor: Actor) -> tuple[ControlAccountView, ...]:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode consultar acessos do Control")

        with self._session_factory() as db:
            rows = (
                db.query(AcessoControl, Pessoa)
                .join(Pessoa, Pessoa.id == AcessoControl.pessoa_id)
                .order_by(Pessoa.email, AcessoControl.id)
                .all()
            )
            return tuple(
                ControlAccountView(
                    id=access.id,
                    person_id=person.id,
                    person_name=person.nome,
                    person_email=person.email,
                    role=ControlAccountRole(access.papel),
                    status=ControlAccountStatus(access.estado),
                    created_at=access.criada_em,
                    updated_at=access.atualizada_em,
                )
                for access, person in rows
            )

    def disable(self, actor: Actor, access_id: str) -> ControlAccountView:
        _require_admin(actor)
        with self._session_factory() as db:
            access = db.get(AcessoControl, access_id)
            if access is None:
                raise ControlAccountConflict("Acesso Control não encontrado")
            if access.id == actor.id or access.gestor_legado_id == actor.id:
                raise ControlAccountConflict(
                    "Admin Revy não pode desativar o próprio acesso"
                )
            if access.estado != ControlAccountStatus.ACTIVE.value:
                raise ControlAccountConflict(
                    "somente acesso ativo pode ser desativado"
                )
            person = db.get(Pessoa, access.pessoa_id)
            if person is None:
                raise PersonNotFound("Pessoa Revy não encontrada")
            legacy_manager = _legacy_manager(db, access)

            previous_version = access.sessao_versao
            access.estado = ControlAccountStatus.DISABLED.value
            access.sessao_versao = previous_version + 1
            access.atualizada_em = agora()
            if legacy_manager is not None:
                legacy_manager.ativo = False
            _append_event(
                db,
                actor=actor,
                store_id=None,
                action="control_account.disabled",
                resource_type="acesso_control",
                resource_id=access.id,
                before={
                    "status": ControlAccountStatus.ACTIVE.value,
                    "session_version": previous_version,
                },
                after={
                    "status": ControlAccountStatus.DISABLED.value,
                    "session_version": access.sessao_versao,
                },
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            return _account_view(access, person)

    def enable(self, actor: Actor, access_id: str) -> ControlAccountView:
        _require_admin(actor)
        with self._session_factory() as db:
            access = db.get(AcessoControl, access_id)
            if access is None:
                raise ControlAccountConflict("Acesso Control não encontrado")
            if access.estado != ControlAccountStatus.DISABLED.value:
                raise ControlAccountConflict(
                    "somente acesso desativado pode ser reativado"
                )
            if not access.senha_hash or not access.gestor_legado_id:
                raise ControlAccountConflict(
                    "acesso não possui credencial e gestor legado para reativação"
                )
            person = db.get(Pessoa, access.pessoa_id)
            if person is None:
                raise PersonNotFound("Pessoa Revy não encontrada")
            legacy_manager = _legacy_manager(db, access)
            if legacy_manager is None:
                raise ControlAccountConflict(
                    "gestor legado do acesso não encontrado"
                )

            previous_version = access.sessao_versao
            access.estado = ControlAccountStatus.ACTIVE.value
            access.sessao_versao = previous_version + 1
            access.atualizada_em = agora()
            legacy_manager.ativo = True
            _append_event(
                db,
                actor=actor,
                store_id=None,
                action="control_account.enabled",
                resource_type="acesso_control",
                resource_id=access.id,
                before={
                    "status": ControlAccountStatus.DISABLED.value,
                    "session_version": previous_version,
                },
                after={
                    "status": ControlAccountStatus.ACTIVE.value,
                    "session_version": access.sessao_versao,
                },
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            return _account_view(access, person)


def _require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise AccessDenied("somente Admin Revy pode administrar acessos do Control")


def _legacy_manager(db: Any, access: AcessoControl) -> GestorRevy | None:
    if access.gestor_legado_id is None:
        return None
    manager = db.get(GestorRevy, access.gestor_legado_id)
    if manager is None:
        raise ControlAccountConflict("gestor legado do acesso não encontrado")
    return manager


def _account_view(
    access: AcessoControl,
    person: Pessoa,
) -> ControlAccountView:
    return ControlAccountView(
        id=access.id,
        person_id=person.id,
        person_name=person.nome,
        person_email=person.email,
        role=ControlAccountRole(access.papel),
        status=ControlAccountStatus(access.estado),
        created_at=access.criada_em,
        updated_at=access.atualizada_em,
    )
