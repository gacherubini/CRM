from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.control.audit import _append_event
from app.control.provisioning_hooks import safe_enqueue_store_snapshot
from app.control.readiness import build_readiness_report, first_failed_required
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
    StoreSlugConflict,
    StoreStatus,
    StoreView,
    TransitionStore,
    UpdateStore,
)
from app.db import Base
from app.models import Loja, VinculoTrafego, agora

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

    def list(self, actor: Actor) -> tuple[StoreView, ...]:
        """Lista lojas no escopo do ator (admin: todas; gestor: vínculo ativo)."""
        with self._session_factory() as db:
            if actor.is_admin:
                rows = db.query(Loja).order_by(Loja.nome, Loja.id).all()
                return tuple(_store_view(row) for row in rows)
            rows = (
                db.query(Loja)
                .join(VinculoTrafego, VinculoTrafego.loja_id == Loja.id)
                .filter(
                    VinculoTrafego.gestor_id == actor.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .order_by(Loja.nome, Loja.id)
                .all()
            )
            return tuple(_store_view(row) for row in rows)

    def delete(self, actor: Actor, store: StoreRef) -> str:
        """Remove ou arquiva uma Loja.

        Loja em rascunho é apagada de vez (junto com o que estiver vinculado);
        loja com qualquer histórico é arquivada (estado `encerrada`), preservando
        auditoria e dados fiscais. Retorna 'deleted' ou 'archived'."""
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode excluir Loja")

        with self._session_factory() as db:
            row = _find_store(db, store, for_update=True)
            if row is None:
                raise StoreNotFound("Loja não encontrada")
            loja_id = row.id
            status = StoreStatus(row.status)

            if status is not StoreStatus.DRAFT:
                if status is StoreStatus.CLOSED:
                    return "archived"
                before = {"status": row.status}
                row.status = StoreStatus.CLOSED.value
                row.versao += 1
                row.atualizada_em = agora()
                _append_event(
                    db,
                    actor=actor,
                    store_id=loja_id,
                    action="store.archived",
                    resource_type="loja",
                    resource_id=loja_id,
                    before=before,
                    after={"status": row.status},
                )
                db.commit()
                return "archived"

            # Rascunho: hard delete. Deixa um rastro sem loja_id (a linha da loja
            # e seus eventos somem) e remove os filhos antes da própria loja.
            _append_event(
                db,
                actor=actor,
                store_id=None,
                action="store.deleted",
                resource_type="loja",
                resource_id=loja_id,
                before={"name": row.nome, "slug": row.slug, "status": row.status},
            )
            _delete_store_children(db, loja_id)
            db.delete(row)
            db.commit()
            return "deleted"

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
            ) or command.target is StoreStatus.ACTIVE:
                # Pronta e Ativa exigem checks required ok. Aceite de alerta
                # não inventa ready=True se required falhar.
                report = build_readiness_report(db, store)
                if not report.ready:
                    failed = first_failed_required(report)
                    requirement = failed.code if failed is not None else "ready"
                    raise StoreReadinessBlocked(store.id, requirement)
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


def _delete_store_children(db: Any, loja_id: str) -> None:
    """Apaga toda linha que referencia esta Loja, folha-primeiro.

    Percorre o metadata do SQLAlchemy em ordem topológica reversa (filhos antes
    de pais) e, para cada tabela com FK para `lojas`, deleta onde a coluna aponta
    para `loja_id`. É genérico de propósito: uma tabela nova que referencie a
    Loja passa a ser limpa aqui sem precisar editar este método."""
    lojas_table = Loja.__table__
    for table in reversed(Base.metadata.sorted_tables):
        if table is lojas_table:
            continue
        for fk in table.foreign_keys:
            if fk.column.table is lojas_table:
                db.execute(table.delete().where(fk.parent == loja_id))
                break


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


# Estados em que jobs de tráfego (spend Meta, CAPI outbox) não devem processar.
# Histórico e filas permanecem intactos (PARK / BLOCK do ADR 0001).
_JOB_BLOCKED_STATUSES = frozenset(
    {
        StoreStatus.SUSPENDED.value,
        StoreStatus.CLOSED.value,
    }
)


def lookup_store_status(
    db: Any,
    *,
    loja_id: str | None = None,
    loja_slug: str | None = None,
) -> str | None:
    """Retorna o status canônico da Loja ou None se não houver cadastro Control."""
    if loja_id:
        row = db.query(Loja.status).filter(Loja.id == loja_id).first()
        if row is not None:
            return row[0]
    if loja_slug:
        slug = loja_slug.strip().lower()
        if slug:
            row = db.query(Loja.status).filter(Loja.slug == slug).first()
            if row is not None:
                return row[0]
    return None


def store_blocks_traffic_jobs(
    db: Any,
    *,
    loja_id: str | None = None,
    loja_slug: str | None = None,
) -> bool:
    """True quando a loja está suspensa/encerrada e jobs não devem avançar.

    Sem Loja no Control (legado só por slug), retorna False para preservar
    o comportamento atual durante o cutover.
    """
    status = lookup_store_status(db, loja_id=loja_id, loja_slug=loja_slug)
    if status is None:
        return False
    return status in _JOB_BLOCKED_STATUSES
