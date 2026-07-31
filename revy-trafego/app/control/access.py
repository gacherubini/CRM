from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.control.audit import _append_event
from app.control.stores import _find_store, _store_view
from app.control.types import (
    AccessibleStore,
    AccessDenied,
    ActiveResponsibleConflict,
    Actor,
    GrantTrafficAccess,
    ManagerNotFound,
    RevokeTrafficAccess,
    StoreNotFound,
    StoreRef,
    TrafficLinkConflict,
    TrafficLinkDetail,
    TrafficLinkNotFound,
    TrafficLinkView,
    TrafficRole,
)
from app.models import AcessoControl, GestorRevy, Loja, Pessoa, VinculoTrafego, agora


class AccessControl:
    """Vínculos de tráfego e escopo visível no Revy Control."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def grant(
        self,
        actor: Actor,
        command: GrantTrafficAccess,
    ) -> TrafficLinkView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode atribuir gestores")

        with self._session_factory() as db:
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            manager = (
                db.query(GestorRevy)
                .filter(
                    GestorRevy.id == command.manager_id,
                    GestorRevy.ativo.is_(True),
                )
                .first()
            )
            if manager is None:
                raise ManagerNotFound("Gestor de Tráfego não encontrado ou inativo")
            current_responsible = _active_responsible(db, store.id)
            if (
                command.role is TrafficRole.RESPONSIBLE
                and current_responsible is not None
            ):
                raise ActiveResponsibleConflict(
                    store.id,
                    current_responsible.gestor_id,
                )
            link = VinculoTrafego(
                loja_id=store.id,
                gestor_id=command.manager_id,
                tipo=command.role.value,
            )
            db.add(link)
            try:
                db.flush()
                _append_event(
                    db,
                    actor=actor,
                    store_id=store.id,
                    action="traffic_access.granted",
                    resource_type="vinculo_trafego",
                    resource_id=link.id,
                    after={
                        "manager_id": link.gestor_id,
                        "role": link.tipo,
                    },
                )
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                current_responsible = _active_responsible(db, store.id)
                if (
                    command.role is TrafficRole.RESPONSIBLE
                    and current_responsible is not None
                ):
                    raise ActiveResponsibleConflict(
                        store.id,
                        current_responsible.gestor_id,
                    ) from exc
                raise TrafficLinkConflict(
                    "o gestor já possui vínculo ativo com a Loja"
                ) from exc
            db.refresh(link)
            return _traffic_link_view(link)

    def scope(self, actor: Actor) -> tuple[AccessibleStore, ...]:
        with self._session_factory() as db:
            if actor.is_admin:
                stores = db.query(Loja).order_by(Loja.nome, Loja.id).all()
                return tuple(
                    AccessibleStore(store=_store_view(store), role=None)
                    for store in stores
                )
            rows = (
                db.query(Loja, VinculoTrafego)
                .join(VinculoTrafego, VinculoTrafego.loja_id == Loja.id)
                .filter(
                    VinculoTrafego.gestor_id == actor.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .order_by(Loja.nome, Loja.id)
                .all()
            )
            return tuple(
                AccessibleStore(
                    store=_store_view(store),
                    role=TrafficRole(link.tipo),
                )
                for store, link in rows
            )

    def list_links(
        self, actor: Actor, store_ref: StoreRef
    ) -> tuple[TrafficLinkDetail, ...]:
        with self._session_factory() as db:
            store = _find_store(db, store_ref)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            if not actor.is_admin:
                mine = (
                    db.query(VinculoTrafego.id)
                    .filter(
                        VinculoTrafego.loja_id == store.id,
                        VinculoTrafego.gestor_id == actor.id,
                        VinculoTrafego.encerrado_em.is_(None),
                    )
                    .first()
                )
                if mine is None:
                    raise StoreNotFound("Loja não encontrada")
            rows = (
                db.query(VinculoTrafego, Pessoa)
                .join(
                    AcessoControl,
                    AcessoControl.gestor_legado_id == VinculoTrafego.gestor_id,
                )
                .join(Pessoa, Pessoa.id == AcessoControl.pessoa_id)
                .filter(
                    VinculoTrafego.loja_id == store.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .order_by(Pessoa.nome, Pessoa.email)
                .all()
            )
            return tuple(
                TrafficLinkDetail(
                    link=_traffic_link_view(link),
                    manager_email=person.email,
                    manager_name=person.nome,
                )
                for link, person in rows
            )

    def authorize(self, actor: Actor, store_ref: StoreRef) -> AccessibleStore:
        with self._session_factory() as db:
            store = _find_store(db, store_ref)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            if actor.is_admin:
                return AccessibleStore(store=_store_view(store), role=None)
            link = (
                db.query(VinculoTrafego)
                .filter(
                    VinculoTrafego.loja_id == store.id,
                    VinculoTrafego.gestor_id == actor.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .first()
            )
            if link is None:
                raise StoreNotFound("Loja não encontrada")
            return AccessibleStore(
                store=_store_view(store),
                role=TrafficRole(link.tipo),
            )

    def revoke(
        self,
        actor: Actor,
        command: RevokeTrafficAccess,
    ) -> TrafficLinkView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode revogar gestores")

        with self._session_factory() as db:
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            link = (
                db.query(VinculoTrafego)
                .filter(
                    VinculoTrafego.loja_id == store.id,
                    VinculoTrafego.gestor_id == command.manager_id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .first()
            )
            if link is None:
                raise TrafficLinkNotFound("vínculo de tráfego ativo não encontrado")
            before = {
                "manager_id": link.gestor_id,
                "role": link.tipo,
                "active": True,
            }
            link.encerrado_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="traffic_access.revoked",
                resource_type="vinculo_trafego",
                resource_id=link.id,
                before=before,
                after={
                    "manager_id": link.gestor_id,
                    "role": link.tipo,
                    "active": False,
                },
                reason=command.reason,
            )
            db.commit()
            db.refresh(link)
            return _traffic_link_view(link)


def _active_responsible(db: Any, store_id: str) -> VinculoTrafego | None:
    return (
        db.query(VinculoTrafego)
        .filter(
            VinculoTrafego.loja_id == store_id,
            VinculoTrafego.tipo == TrafficRole.RESPONSIBLE.value,
            VinculoTrafego.encerrado_em.is_(None),
        )
        .first()
    )


def _traffic_link_view(link: VinculoTrafego) -> TrafficLinkView:
    return TrafficLinkView(
        id=link.id,
        store_id=link.loja_id,
        manager_id=link.gestor_id,
        role=TrafficRole(link.tipo),
        started_at=link.iniciado_em,
        ended_at=link.encerrado_em,
    )
