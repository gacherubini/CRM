"""Outbox durável de snapshots de provisionamento (Revy Control).

Enqueue idempotente + process_pending para entrega assíncrona.
Worker/thread de polling fica atrás da flag
``REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED`` (default off).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.control.provisioning import StoreProvisioningSnapshot
from app.models import ControlProvisioningOutbox, Loja, agora, novo_id


def snapshot_to_payload(
    snapshot: StoreProvisioningSnapshot,
    *,
    loja_slug: str,
) -> dict[str, Any]:
    """Serializa o snapshot para JSON (timestamps em ISO-8601)."""
    loja_id = ""
    if snapshot.operational:
        loja_id = snapshot.operational[0].loja_id
    return {
        "schema_version": snapshot.schema_version,
        "loja_id": loja_id,
        "loja_slug": loja_slug,
        "operational": [
            {
                "schema_version": item.schema_version,
                "event_id": item.event_id,
                "loja_id": item.loja_id,
                "aggregate": item.aggregate,
                "version": item.version,
                "state": item.state,
                "effective_at": item.effective_at.isoformat(),
                "occurred_at": item.occurred_at.isoformat(),
                "reason": item.reason,
            }
            for item in snapshot.operational
        ],
        "people": [
            {
                "person_id": person.person_id,
                "email": person.email,
                "name": person.name,
            }
            for person in snapshot.people
        ],
        "roles": [
            {
                "assignment_id": role.assignment_id,
                "person_id": role.person_id,
                "role": role.role,
                "state": role.state,
                "started_at": role.started_at.isoformat(),
                "ended_at": role.ended_at.isoformat() if role.ended_at else None,
            }
            for role in snapshot.roles
        ],
    }


def event_id_for(
    *,
    loja_id: str,
    destination: str,
    snapshot: StoreProvisioningSnapshot,
) -> str:
    """Event ID estável para o mesmo snapshot e destino.

    Usa o composite das versões de cada aggregate operacional (ordenado),
    caindo no version da Loja quando só ela está presente.
    """
    version_token = ",".join(
        f"{item.aggregate}={item.version}"
        for item in sorted(snapshot.operational, key=lambda item: item.aggregate)
    )
    if not version_token:
        version_token = "0"
    return f"{loja_id}:{destination}:{version_token}"


def enqueue_delivery(
    db: Any,
    *,
    loja_id: str,
    loja_slug: str,
    destination: str,
    snapshot: StoreProvisioningSnapshot,
) -> ControlProvisioningOutbox:
    """Enfileira entrega; idempotente em ``event_id`` (retorna a linha existente)."""
    event_id = event_id_for(
        loja_id=loja_id, destination=destination, snapshot=snapshot
    )
    existing = (
        db.query(ControlProvisioningOutbox)
        .filter(ControlProvisioningOutbox.event_id == event_id)
        .first()
    )
    if existing is not None:
        return existing

    payload = snapshot_to_payload(snapshot, loja_slug=loja_slug)
    now = agora()
    row = ControlProvisioningOutbox(
        id=novo_id(),
        loja_id=loja_id,
        destination=destination,
        event_id=event_id,
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        status="pending",
        attempts=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def process_pending(
    db: Any,
    poster: Callable[[str, dict[str, Any]], None],
    *,
    limit: int = 20,
) -> int:
    """Processa pendentes: chama ``poster(destination, payload)`` e marca status.

    Retorna quantos foram marcados como ``delivered``.
    """
    rows = (
        db.query(ControlProvisioningOutbox)
        .filter(ControlProvisioningOutbox.status == "pending")
        .order_by(
            ControlProvisioningOutbox.created_at.asc(),
            ControlProvisioningOutbox.id.asc(),
        )
        .limit(limit)
        .all()
    )
    delivered = 0
    for row in rows:
        payload = json.loads(row.payload_json)
        now = agora()
        try:
            poster(row.destination, payload)
        except Exception as exc:  # noqa: BLE001 — outbox captura falhas de entrega
            row.status = "failed"
            row.attempts = int(row.attempts or 0) + 1
            row.last_error = f"{type(exc).__name__}: {exc}"
            row.updated_at = now
            continue
        row.status = "delivered"
        row.attempts = int(row.attempts or 0) + 1
        row.last_error = None
        row.updated_at = now
        delivered += 1
    db.flush()
    return delivered


def resolve_loja_slug(db: Any, loja_id: str) -> str:
    """Resolve slug da Loja a partir do id (uso do publisher/delivery durável)."""
    store = db.query(Loja).filter(Loja.id == loja_id).first()
    if store is None:
        return ""
    return store.slug
