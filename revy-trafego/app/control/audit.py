from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.control.types import (
    Actor,
    AuditEventView,
    AuditPage,
    AuditQuery,
    AuditResult,
    StoreNotFound,
)
from app.models import AuditoriaEvento, VinculoTrafego


class AuditTrail:
    """Consulta autorizada da trilha administrativa imutável."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def list(self, actor: Actor, query: AuditQuery) -> AuditPage:
        limit = max(1, min(query.limit, 500))
        with self._session_factory() as db:
            events = db.query(AuditoriaEvento)
            if actor.is_admin:
                if query.store_id:
                    events = events.filter(AuditoriaEvento.loja_id == query.store_id)
            else:
                store_ids = [
                    store_id
                    for (store_id,) in db.query(VinculoTrafego.loja_id)
                    .filter(
                        VinculoTrafego.gestor_id == actor.id,
                        VinculoTrafego.encerrado_em.is_(None),
                    )
                    .all()
                ]
                if query.store_id and query.store_id not in store_ids:
                    raise StoreNotFound("Loja não encontrada")
                if query.store_id:
                    store_ids = [query.store_id]
                if not store_ids:
                    return AuditPage(items=())
                events = events.filter(AuditoriaEvento.loja_id.in_(store_ids))
            rows = (
                events.order_by(
                    AuditoriaEvento.criado_em.asc(),
                    AuditoriaEvento.id.asc(),
                )
                .limit(limit)
                .all()
            )
            return AuditPage(items=tuple(_event_view(event) for event in rows))

    def list_recent(self, actor: Actor, *, limit: int = 20) -> AuditPage:
        """Últimos eventos no escopo do ator (mais recentes primeiro)."""
        limit = max(1, min(limit, 100))
        with self._session_factory() as db:
            events = db.query(AuditoriaEvento)
            if actor.is_admin:
                pass
            else:
                store_ids = [
                    store_id
                    for (store_id,) in db.query(VinculoTrafego.loja_id)
                    .filter(
                        VinculoTrafego.gestor_id == actor.id,
                        VinculoTrafego.encerrado_em.is_(None),
                    )
                    .all()
                ]
                if not store_ids:
                    return AuditPage(items=())
                events = events.filter(AuditoriaEvento.loja_id.in_(store_ids))
            rows = (
                events.order_by(
                    AuditoriaEvento.criado_em.desc(),
                    AuditoriaEvento.id.desc(),
                )
                .limit(limit)
                .all()
            )
            return AuditPage(items=tuple(_event_view(event) for event in rows))


def _append_event(
    db: Any,
    *,
    actor: Actor,
    store_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        AuditoriaEvento(
            loja_id=store_id,
            ator_gestor_id=actor.id,
            ator_email=actor.email,
            acao=action,
            recurso_tipo=resource_type,
            recurso_id=resource_id,
            resultado=AuditResult.SUCCESS.value,
            antes_json=_dump_json(before),
            depois_json=_dump_json(after),
            motivo=(reason.strip() if reason and reason.strip() else None),
        )
    )


def _dump_json(value: dict[str, object] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_json(value: str | None) -> dict[str, object] | None:
    if not value:
        return None
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else None


def _event_view(event: AuditoriaEvento) -> AuditEventView:
    return AuditEventView(
        id=event.id,
        store_id=event.loja_id,
        actor_id=event.ator_gestor_id,
        actor_email=event.ator_email,
        action=event.acao,
        resource_type=event.recurso_tipo,
        resource_id=event.recurso_id,
        result=AuditResult(event.resultado),
        before=_load_json(event.antes_json),
        after=_load_json(event.depois_json),
        reason=event.motivo,
        created_at=event.criado_em,
    )
