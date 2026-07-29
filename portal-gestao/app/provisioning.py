"""Consome snapshots de provisionamento do Control e aplica projeção monotônica."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import LojaOperacionalProjecao, agora


def apply_payload(db: Session, loja_slug: str, payload: dict[str, Any]) -> list[str]:
    """Aplica envelopes operacionais de forma monotônica e idempotente.

    Regras por aggregate (iguais a chatbot/estoque apply_snapshot):
    - versão menor que a local → ``stale`` (não reativa)
    - mesma versão e mesmo estado → ``idempotent``
    - demais casos → ``applied``
    """
    reasons: list[str] = []
    for envelope in payload.get("operational") or []:
        if not isinstance(envelope, dict):
            continue
        aggregate = envelope.get("aggregate")
        if not aggregate:
            continue
        reasons.append(_apply_envelope(db, loja_slug, envelope, str(aggregate)))
    return reasons


def allows_processing(
    db: Session, loja_slug: str, module: str | None = None
) -> bool:
    """Gate mínimo: Loja ativa e, se pedido, módulo contratado e ativo.

    Fail-closed quando a projeção da loja não existe.
    """
    loja = db.get(LojaOperacionalProjecao, (loja_slug, "loja"))
    if loja is None or loja.state != "ativa":
        return False
    if module is None:
        return True
    assigned = db.get(LojaOperacionalProjecao, (loja_slug, module))
    return assigned is not None and assigned.state == "ativo"


def _apply_envelope(
    db: Session,
    loja_slug: str,
    envelope: dict[str, Any],
    aggregate: str,
) -> str:
    version = int(envelope.get("version") or 0)
    state = str(envelope.get("state") or "")
    event_id = str(envelope.get("event_id") or "")

    existing = db.get(LojaOperacionalProjecao, (loja_slug, aggregate))
    if existing is not None:
        if existing.version > version:
            return "stale"
        if existing.version == version and existing.state == state:
            return "idempotent"
        existing.version = version
        existing.state = state
        existing.event_id = event_id
        existing.atualizado_em = agora()
        return "applied"

    db.add(
        LojaOperacionalProjecao(
            loja_slug=loja_slug,
            aggregate=aggregate,
            version=version,
            state=state,
            event_id=event_id,
            atualizado_em=agora(),
        )
    )
    return "applied"
