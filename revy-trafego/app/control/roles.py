from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.control.audit import _append_event
from app.control.stores import _find_store
from app.control.types import (
    AccessDenied,
    Actor,
    AssignStoreRole,
    PersonNotFound,
    RevokeStoreRole,
    StoreNotFound,
    StoreRef,
    StoreRole,
    StoreRoleConflict,
    StoreRoleNotFound,
    StoreRoleView,
)
from app.models import CargoLoja, Pessoa, VinculoTrafego, agora


class StoreRoles:
    """Cargos estruturais de Pessoas Revy, sempre isolados por Loja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def assign(self, actor: Actor, command: AssignStoreRole) -> StoreRoleView:
        _require_admin(actor)
        with self._session_factory() as db:
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            person = db.get(Pessoa, command.person.id)
            if person is None:
                raise PersonNotFound("Pessoa Revy não encontrada")
            if _active_role(db, store.id, person.id, command.role) is not None:
                raise StoreRoleConflict(store.id, person.id, command.role)

            role = CargoLoja(
                loja_id=store.id,
                pessoa_id=person.id,
                cargo=command.role.value,
                origem="control",
            )
            db.add(role)
            try:
                db.flush()
                _append_event(
                    db,
                    actor=actor,
                    store_id=store.id,
                    action="store_role.assigned",
                    resource_type="cargo_loja",
                    resource_id=role.id,
                    after={
                        "person_id": person.id,
                        "role": command.role.value,
                    },
                )
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise StoreRoleConflict(store.id, person.id, command.role) from exc
            db.refresh(role)
            return _role_view(role)

    def revoke(self, actor: Actor, command: RevokeStoreRole) -> StoreRoleView:
        _require_admin(actor)
        with self._session_factory() as db:
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            person = db.get(Pessoa, command.person.id)
            if person is None:
                raise PersonNotFound("Pessoa Revy não encontrada")
            role = _active_role(db, store.id, person.id, command.role)
            if role is None:
                raise StoreRoleNotFound("cargo ativo não encontrado na Loja")

            role.encerrado_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="store_role.revoked",
                resource_type="cargo_loja",
                resource_id=role.id,
                before={
                    "person_id": person.id,
                    "role": command.role.value,
                    "active": True,
                },
                after={
                    "person_id": person.id,
                    "role": command.role.value,
                    "active": False,
                },
                reason=command.reason,
            )
            db.commit()
            db.refresh(role)
            return _role_view(role)

    def list_for_store(
        self,
        actor: Actor,
        store_ref: StoreRef,
        *,
        include_ended: bool = False,
    ) -> tuple[StoreRoleView, ...]:
        with self._session_factory() as db:
            store = _find_store(db, store_ref)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            _authorize_listing(db, actor, store.id)

            query = db.query(CargoLoja).filter(CargoLoja.loja_id == store.id)
            if not include_ended:
                query = query.filter(CargoLoja.encerrado_em.is_(None))
            rows = query.order_by(CargoLoja.iniciado_em, CargoLoja.id).all()
            return tuple(_role_view(row) for row in rows)


def _require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise AccessDenied("somente Admin Revy pode administrar cargos da Loja")


def _authorize_listing(db: Any, actor: Actor, store_id: str) -> None:
    if actor.is_admin:
        return
    active_link = (
        db.query(VinculoTrafego)
        .filter(
            VinculoTrafego.loja_id == store_id,
            VinculoTrafego.gestor_id == actor.id,
            VinculoTrafego.encerrado_em.is_(None),
        )
        .first()
    )
    if active_link is None:
        raise StoreNotFound("Loja não encontrada")


def _active_role(
    db: Any,
    store_id: str,
    person_id: str,
    role: StoreRole,
) -> CargoLoja | None:
    return (
        db.query(CargoLoja)
        .filter(
            CargoLoja.loja_id == store_id,
            CargoLoja.pessoa_id == person_id,
            CargoLoja.cargo == role.value,
            CargoLoja.encerrado_em.is_(None),
        )
        .first()
    )


def _role_view(role: CargoLoja) -> StoreRoleView:
    return StoreRoleView(
        id=role.id,
        store_id=role.loja_id,
        person_id=role.pessoa_id,
        role=StoreRole(role.cargo),
        source=role.origem,
        source_id=role.origem_id,
        started_at=role.iniciado_em,
        ended_at=role.encerrado_em,
    )
