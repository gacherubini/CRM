"""Canais WhatsApp da loja (Fase 5 multi-WA — esqueleto).

Chatbot é dono de `whatsapp_canais`. Número/instância nunca muda de loja:
`loja_id` é imutável após o registro. Inativação é lógica (sem delete).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import config
from app.models_db import Loja, WhatsAppCanal


def _canal_dict(canal: WhatsAppCanal) -> dict[str, Any]:
    return {
        "id": canal.id,
        "loja_id": canal.loja_id,
        "e164_or_label": canal.e164_or_label,
        "evolution_instance": canal.evolution_instance,
        "ativo": canal.ativo,
        "criado_em": canal.criado_em.isoformat() if canal.criado_em else None,
    }


def list_channels(db: Session, loja_id: str) -> list[dict[str, Any]]:
    """Lista canais da loja (ativos e inativos), ordenados por criação."""
    rows = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja_id)
        .order_by(WhatsAppCanal.criado_em.asc())
        .all()
    )
    return [_canal_dict(c) for c in rows]


def register_channel(
    db: Session,
    loja_id: str,
    instance: str,
    label: str,
) -> dict[str, Any]:
    """Registra um canal na loja.

    Com MULTI_WHATSAPP desligado, só permite 1 canal ativo por loja.
    Instância já existente em qualquer loja → 409 (número nunca troca de loja).
    """
    instance = (instance or "").strip()
    label = (label or "").strip()
    if not instance:
        raise HTTPException(status_code=422, detail="evolution_instance é obrigatório")
    if not label:
        raise HTTPException(status_code=422, detail="e164_or_label é obrigatório")

    loja = db.get(Loja, loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")

    existente = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == instance)
        .first()
    )
    if existente is not None:
        if existente.loja_id != loja_id:
            raise HTTPException(
                status_code=409,
                detail="instância já vinculada a outra loja",
            )
        # Idempotente: mesma loja + mesma instância devolve o canal existente.
        return _canal_dict(existente)

    if not config.MULTI_WHATSAPP_ENABLED:
        ativos = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.loja_id == loja_id, WhatsAppCanal.ativo.is_(True))
            .count()
        )
        if ativos >= 1:
            raise HTTPException(
                status_code=409,
                detail="multi-whatsapp desabilitado: apenas 1 canal por loja",
            )

    canal = WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label=label,
        evolution_instance=instance,
        ativo=True,
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def inactivate_channel(db: Session, loja_id: str, canal_id: str) -> dict[str, Any]:
    """Inativa o canal (não apaga histórico). loja_id deve bater."""
    canal = db.get(WhatsAppCanal, canal_id)
    if canal is None or canal.loja_id != loja_id:
        raise HTTPException(status_code=404, detail="canal não encontrado")
    if not canal.ativo:
        return _canal_dict(canal)
    canal.ativo = False
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def backfill_legacy_from_loja(db: Session, loja_id: str) -> dict[str, Any] | None:
    """Cria canal legado a partir de Loja.evolution_instance + whatsapp.

    Idempotente: se a instância já existe em canais, devolve o existente.
    Não cria se a loja não tiver evolution_instance.
    """
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")

    instance = (loja.evolution_instance or "").strip()
    if not instance:
        return None

    existente = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == instance)
        .first()
    )
    if existente is not None:
        return _canal_dict(existente)

    label = (loja.whatsapp or "").strip() or "legado"
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja.id,
        e164_or_label=label,
        evolution_instance=instance,
        ativo=True,
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def get_channel_by_instance(db: Session, instance: str) -> WhatsAppCanal | None:
    """Busca canal pela instância Evolution (qualquer loja)."""
    if not instance:
        return None
    return (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == instance)
        .first()
    )
