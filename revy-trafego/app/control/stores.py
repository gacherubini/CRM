from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.control.audit import _append_event
from app.control.types import (
    AccessDenied,
    Actor,
    CreateStore,
    InvalidStoreTransition,
    StoreNotFound,
    StoreRef,
    StoreSlugConflict,
    StoreStatus,
    StoreView,
    TransitionStore,
)
from app.models import Loja, VinculoTrafego, agora

_ALLOWED_TRANSITIONS = {
    StoreStatus.DRAFT: frozenset({StoreStatus.CONFIGURING}),
    StoreStatus.CONFIGURING: frozenset({StoreStatus.READY}),
    StoreStatus.READY: frozenset({StoreStatus.ACTIVE}),
    StoreStatus.ACTIVE: frozenset({StoreStatus.SUSPENDED}),
    StoreStatus.SUSPENDED: frozenset({StoreStatus.CLOSED}),
    StoreStatus.CLOSED: frozenset(),
}


class StoreControl:
    """Cadastro e consulta de Lojas através de tipos de domínio estáveis."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def create(self, actor: Actor, command: CreateStore) -> StoreView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode criar Loja")

        name = command.name.strip()
        slug = command.slug.strip().lower()
        if not name or not slug:
            raise ValueError("nome e slug da Loja são obrigatórios")

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
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            current = StoreStatus(store.status)
            if command.target not in _ALLOWED_TRANSITIONS[current]:
                raise InvalidStoreTransition(current, command.target)
            store.status = command.target.value
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
            return _store_view(store)


def _find_store(db: Any, store: StoreRef) -> Loja | None:
    query = db.query(Loja)
    if store.id:
        return query.filter(Loja.id == store.id).first()
    return query.filter(Loja.slug == store.slug.strip().lower()).first()


def _store_view(store: Loja) -> StoreView:
    return StoreView(
        id=store.id,
        name=store.nome,
        slug=store.slug,
        status=StoreStatus(store.status),
        created_at=store.criada_em,
        updated_at=store.atualizada_em,
    )
