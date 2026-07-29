from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.control.stores import _find_store
from app.control.types import StoreNotFound, StoreRef
from app.models import AuditoriaEvento, LojaModulo, ModuloRevy


@dataclass(frozen=True)
class OperationalStateEnvelope:
    schema_version: int
    event_id: str
    loja_id: str
    aggregate: str
    version: int
    state: str
    effective_at: datetime
    occurred_at: datetime
    reason: str | None


class ProvisioningControl:
    """Snapshot do estado operacional projetável de uma Loja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def snapshot(
        self,
        store_ref: StoreRef,
    ) -> tuple[OperationalStateEnvelope, ...]:
        with self._session_factory() as db:
            store = _find_store(db, store_ref)
            if store is None:
                raise StoreNotFound("Loja não encontrada")

            items = [
                _envelope(
                    db,
                    loja_id=store.id,
                    aggregate="loja",
                    version=store.versao,
                    state=store.status,
                    effective_at=store.atualizada_em,
                    resource_type="loja",
                    resource_id=store.id,
                )
            ]
            assignments = (
                db.query(LojaModulo, ModuloRevy)
                .join(ModuloRevy, ModuloRevy.id == LojaModulo.modulo_id)
                .filter(LojaModulo.loja_id == store.id)
                .all()
            )
            by_code = {
                module.codigo: (assignment, module)
                for assignment, module in assignments
            }
            for code in ("vendas", "estoque"):
                match = by_code.get(code)
                if match is None:
                    continue
                assignment, module = match
                items.append(
                    _envelope(
                        db,
                        loja_id=store.id,
                        aggregate=module.codigo,
                        version=assignment.versao,
                        state=assignment.estado,
                        effective_at=assignment.atualizado_em,
                        resource_type="loja_modulo",
                        resource_id=assignment.id,
                    )
                )
            return tuple(items)


def _envelope(
    db: Any,
    *,
    loja_id: str,
    aggregate: str,
    version: int,
    state: str,
    effective_at: datetime,
    resource_type: str,
    resource_id: str,
) -> OperationalStateEnvelope:
    event = (
        db.query(AuditoriaEvento)
        .filter(
            AuditoriaEvento.loja_id == loja_id,
            AuditoriaEvento.recurso_tipo == resource_type,
            AuditoriaEvento.recurso_id == resource_id,
        )
        .order_by(
            AuditoriaEvento.criado_em.desc(),
            AuditoriaEvento.id.desc(),
        )
        .first()
    )
    if event is None:
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "urn:revy:operational-state:"
                f"{resource_type}:{resource_id}:{version}",
            )
        )
        occurred_at = effective_at
        reason = None
    else:
        event_id = event.id
        occurred_at = event.criado_em
        reason = event.motivo
    return OperationalStateEnvelope(
        schema_version=1,
        event_id=event_id,
        loja_id=loja_id,
        aggregate=aggregate,
        version=version,
        state=state,
        effective_at=effective_at,
        occurred_at=occurred_at,
        reason=reason,
    )
