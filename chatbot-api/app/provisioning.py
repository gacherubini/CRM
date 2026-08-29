"""Consome snapshots de provisionamento do Control e aplica projeção monotônica."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models_db import LojaOperacionalProjecao, WhatsAppCanal, _agora


def apply_payload(db: Session, loja_id: str, payload: dict[str, Any]) -> list[str]:
    """Aplica envelopes operacionais de forma monotônica e idempotente.

    Regras por aggregate (iguais a revy-trafego apply_snapshot):
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
        reasons.append(_apply_envelope(db, loja_id, envelope, str(aggregate)))
    return reasons


def allows_processing(
    db: Session, loja_id: str, module: str | None = None
) -> bool:
    """Gate mínimo: Loja ativa e, se pedido, módulo contratado e ativo.

    Fail-closed quando a projeção da loja não existe.
    """
    loja = db.get(LojaOperacionalProjecao, (loja_id, "loja"))
    if loja is None or loja.state != "ativa":
        return False
    if module is None:
        return True
    assigned = db.get(LojaOperacionalProjecao, (loja_id, module))
    return assigned is not None and assigned.state == "ativo"


def is_store_operational(db: Session, loja_id: str) -> bool:
    """True quando a Loja está projetada como ``ativa`` (fail-closed)."""
    return allows_processing(db, loja_id)


def is_module_operational(db: Session, loja_id: str, module: str) -> bool:
    """True quando Loja ativa e o módulo está contratado e ``ativo``."""
    return allows_processing(db, loja_id, module=module)


def allows_outbound_whatsapp(db: Session, loja_id: str) -> bool:
    """Envio WhatsApp (bot/humano via automação): exige Loja operacional (v1)."""
    return is_store_operational(db, loja_id)


def capture_only(
    db: Session, loja_id: str, *, module: str | None = None
) -> bool:
    """True quando o ingresso deve ser só capturado, sem processar o domínio.

    ``module`` restringe ao módulo exigido (ex.: ``estoque`` para grupo/cadastro).
    Sem módulo, basta a Loja não operacional.
    """
    return not allows_processing(db, loja_id, module)


def _liberar_canal_cloud(db: Session, loja_id: str) -> None:
    """Portão do Control (spec §9): liberar a loja ativa o canal que esperava.

    Só sobe de ``cloud_pendente``. Canal restrito ou banido pela Meta não volta
    por decisão nossa, e canal já ativo não é tocado.
    """
    canais = (
        db.query(WhatsAppCanal)
        .filter(
            WhatsAppCanal.loja_id == loja_id,
            WhatsAppCanal.waba_id.isnot(None),
            WhatsAppCanal.estado == "cloud_pendente",
        )
        .all()
    )
    for canal in canais:
        canal.estado = "cloud_ativo"


def _apply_envelope(
    db: Session,
    loja_id: str,
    envelope: dict[str, Any],
    aggregate: str,
) -> str:
    version = int(envelope.get("version") or 0)
    state = str(envelope.get("state") or "")
    event_id = str(envelope.get("event_id") or "")

    existing = db.get(LojaOperacionalProjecao, (loja_id, aggregate))
    if existing is not None:
        if existing.version > version:
            return "stale"
        if existing.version == version and existing.state == state:
            return "idempotent"
        existing.version = version
        existing.state = state
        existing.event_id = event_id
        existing.atualizado_em = _agora()
        if aggregate == "whatsapp_modo" and state == "2":
            _liberar_canal_cloud(db, loja_id)
        return "applied"

    db.add(
        LojaOperacionalProjecao(
            loja_id=loja_id,
            aggregate=aggregate,
            version=version,
            state=state,
            event_id=event_id,
            atualizado_em=_agora(),
        )
    )
    if aggregate == "whatsapp_modo" and state == "2":
        _liberar_canal_cloud(db, loja_id)
    return "applied"
