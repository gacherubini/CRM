from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.control.audit import _append_event
from app.control.provisioning_hooks import safe_enqueue_store_snapshot
from app.control.types import (
    AccessDenied,
    Actor,
    CreateStore,
    InvalidStoreSlug,
    InvalidStoreTransition,
    StoreEditConflict,
    StoreNotFound,
    StoreRef,
    StoreReadinessBlocked,
    StoreRole,
    StoreSlugConflict,
    StoreStatus,
    StoreView,
    TransitionStore,
    UpdateStore,
)
from app.models import AcessoControl, CargoLoja, Loja, VinculoTrafego, agora

_ALLOWED_TRANSITIONS = {
    StoreStatus.DRAFT: frozenset({StoreStatus.CONFIGURING}),
    StoreStatus.CONFIGURING: frozenset({StoreStatus.READY}),
    StoreStatus.READY: frozenset({StoreStatus.ACTIVE}),
    StoreStatus.ACTIVE: frozenset({StoreStatus.SUSPENDED}),
    StoreStatus.SUSPENDED: frozenset({StoreStatus.ACTIVE, StoreStatus.CLOSED}),
    StoreStatus.CLOSED: frozenset(),
}
_CANONICAL_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class StoreControl:
    """Cadastro e consulta de Lojas através de tipos de domínio estáveis."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def create(self, actor: Actor, command: CreateStore) -> StoreView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode criar Loja")

        name = _normalize_name(command.name)
        slug = command.slug.strip().lower()
        if not slug:
            raise ValueError("slug da Loja é obrigatório")
        if len(slug) > 120 or not _CANONICAL_SLUG.fullmatch(slug):
            raise InvalidStoreSlug(command.slug)

        with self._session_factory() as db:
            store = Loja(nome=name, slug=slug, status=StoreStatus.DRAFT.value)
            db.add(store)
            try:
                db.flush()
                _append_event(
                    db,
                    actor=actor,
                    store_id=store.id,
                    action="store.created",
                    resource_type="loja",
                    resource_id=store.id,
                    after={
                        "name": store.nome,
                        "slug": store.slug,
                        "status": store.status,
                    },
                )
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise StoreSlugConflict(f"slug de Loja já existe: {slug}") from exc
            db.refresh(store)
            return _store_view(store)

    def update(self, actor: Actor, command: UpdateStore) -> StoreView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode editar Loja")
        name = _normalize_name(command.name)

        with self._session_factory() as db:
            store = _find_store(db, command.store, for_update=True)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            current = StoreStatus(store.status)
            if current is not StoreStatus.DRAFT:
                raise StoreEditConflict(current)
            if store.nome == name:
                return _store_view(store)

            before = {"name": store.nome}
            store.nome = name
            store.versao += 1
            store.atualizada_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="store.updated",
                resource_type="loja",
                resource_id=store.id,
                before=before,
                after={"name": store.nome},
            )
            db.commit()
            db.refresh(store)
            return _store_view(store)

    def get(self, actor: Actor, store: StoreRef) -> StoreView:
        with self._session_factory() as db:
            row = _find_store(db, store)
            if row is None:
                raise StoreNotFound("Loja não encontrada")
            if not actor.is_admin:
                active_link = (
                    db.query(VinculoTrafego)
                    .filter(
                        VinculoTrafego.loja_id == row.id,
                        VinculoTrafego.gestor_id == actor.id,
                        VinculoTrafego.encerrado_em.is_(None),
                    )
                    .first()
                )
                if active_link is None:
                    raise StoreNotFound("Loja não encontrada")
            return _store_view(row)

    def transition(self, actor: Actor, command: TransitionStore) -> StoreView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode alterar o estado da Loja")

        with self._session_factory() as db:
            store = _find_store(db, command.store, for_update=True)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            current = StoreStatus(store.status)
            if command.target not in _ALLOWED_TRANSITIONS[current]:
                raise InvalidStoreTransition(current, command.target)
            if (
                current is StoreStatus.CONFIGURING
                and command.target is StoreStatus.READY
            ):
                owner_person_ids = [
                    row[0]
                    for row in db.query(CargoLoja.pessoa_id)
                    .filter(
                        CargoLoja.loja_id == store.id,
                        CargoLoja.cargo == StoreRole.OWNER.value,
                        CargoLoja.encerrado_em.is_(None),
                    )
                    .all()
                ]
                if not owner_person_ids:
                    raise StoreReadinessBlocked(store.id, "active_owner")
                activatable = (
                    db.query(AcessoControl.id)
                    .filter(
                        AcessoControl.pessoa_id.in_(owner_person_ids),
                        AcessoControl.estado.in_(("pendente", "ativo")),
                    )
                    .first()
                )
                if activatable is None:
                    raise StoreReadinessBlocked(store.id, "activatable_owner")
            store.status = command.target.value
            store.versao += 1
            store.atualizada_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="store.status_changed",
                resource_type="loja",
                resource_id=store.id,
                before={"status": current.value},
                after={"status": command.target.value},
                reason=command.reason,
            )
            db.commit()
            db.refresh(store)
            view = _store_view(store)
            safe_enqueue_store_snapshot(
                self._session_factory, StoreRef(id=view.id)
            )
            return view


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > 160:
        raise ValueError("nome da Loja deve ter entre 1 e 160 caracteres")
    return normalized


def _find_store(
    db: Any,
    store: StoreRef,
    *,
    for_update: bool = False,
) -> Loja | None:
    query = db.query(Loja)
    if for_update:
        query = query.with_for_update()
    if store.id:
        return query.filter(Loja.id == store.id).first()
    return query.filter(Loja.slug == store.slug.strip().lower()).first()


def _store_view(store: Loja) -> StoreView:
    return StoreView(
        id=store.id,
        name=store.nome,
        slug=store.slug,
        status=StoreStatus(store.status),
        version=store.versao,
        created_at=store.criada_em,
        updated_at=store.atualizada_em,
    )
