"""Hooks pós-mutação: enfileira snapshot operacional para destinos.

Enqueue é local e barato; a entrega HTTP fica no worker
(``REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED``).
Falhas de enqueue nunca reverte a mutação de domínio.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from app.control.types import StoreRef

logger = logging.getLogger(__name__)

DEFAULT_PROVISIONING_TARGETS: tuple[str, ...] = ("chatbot", "estoque")


def enqueue_store_snapshot(
    session_factory: Callable[[], Any],
    store_ref: StoreRef,
    *,
    targets: Sequence[str] = DEFAULT_PROVISIONING_TARGETS,
) -> int:
    """Monta snapshot e enfileira um item por destino. Retorna quantos rows novos/existentes."""
    # Imports locais evitam ciclo stores ↔ provisioning.
    from app.control.provisioning import ProvisioningControl
    from app.control.provisioning_outbox import enqueue_delivery, resolve_loja_slug

    if not targets:
        return 0
    snapshot = ProvisioningControl(session_factory).snapshot(store_ref)
    if not snapshot.operational:
        return 0
    loja_id = snapshot.operational[0].loja_id
    enqueued = 0
    with session_factory() as db:
        loja_slug = resolve_loja_slug(db, loja_id)
        if not loja_slug:
            logger.warning(
                "provisioning_hooks: slug ausente loja_id=%s", loja_id
            )
            return 0
        for destination in targets:
            enqueue_delivery(
                db,
                loja_id=loja_id,
                loja_slug=loja_slug,
                destination=destination,
                snapshot=snapshot,
            )
            enqueued += 1
        db.commit()
    return enqueued


def safe_enqueue_store_snapshot(
    session_factory: Callable[[], Any],
    store_ref: StoreRef,
    *,
    targets: Sequence[str] = DEFAULT_PROVISIONING_TARGETS,
) -> None:
    """Enqueue best-effort: loga e engole erro para não quebrar a mutação."""
    try:
        enqueue_store_snapshot(session_factory, store_ref, targets=targets)
    except Exception:
        logger.exception(
            "provisioning_hooks: falha ao enfileirar store=%s",
            store_ref.id or store_ref.slug,
        )
