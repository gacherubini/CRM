"""Canais WhatsApp da loja (Fase 5 multi-WA).

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
from app.whatsapp_provider import (
    ESTADO_CONECTADO,
    ESTADO_INATIVO,
    ESTADO_PENDENTE,
    WhatsAppProvider,
    get_whatsapp_provider,
)


def _canal_dict(canal: WhatsAppCanal) -> dict[str, Any]:
    return {
        "id": canal.id,
        "loja_id": canal.loja_id,
        "e164_or_label": canal.e164_or_label,
        "evolution_instance": canal.evolution_instance,
        "ativo": canal.ativo,
        "estado": canal.estado,
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
        estado=ESTADO_PENDENTE,
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
    if not canal.ativo and canal.estado == ESTADO_INATIVO:
        return _canal_dict(canal)
    canal.ativo = False
    canal.estado = ESTADO_INATIVO
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def get_channel_for_loja(
    db: Session, loja_id: str, canal_id: str
) -> WhatsAppCanal:
    canal = db.get(WhatsAppCanal, canal_id)
    if canal is None or canal.loja_id != loja_id:
        raise HTTPException(status_code=404, detail="canal não encontrado")
    return canal


def connect_channel(
    db: Session,
    loja_id: str,
    canal_id: str,
    provider: WhatsAppProvider | None = None,
) -> dict[str, Any]:
    """Inicia conexão/pareamento. Devolve QR efêmero (sem log)."""
    if not config.MULTI_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="multi-whatsapp desabilitado")
    canal = get_channel_for_loja(db, loja_id, canal_id)
    if not canal.ativo or canal.estado == ESTADO_INATIVO:
        raise HTTPException(status_code=409, detail="canal inativo")
    prov = provider or get_whatsapp_provider()
    result = prov.connect(canal)
    db.commit()
    db.refresh(canal)
    out = _canal_dict(canal)
    out["estado"] = result.estado
    if result.qr_payload is not None:
        out["qr_payload"] = result.qr_payload
    if result.expires_in_seconds is not None:
        out["expires_in_seconds"] = result.expires_in_seconds
    if result.pairing_code is not None:
        out["pairing_code"] = result.pairing_code
    return out


def channel_status(
    db: Session,
    loja_id: str,
    canal_id: str,
    provider: WhatsAppProvider | None = None,
) -> dict[str, Any]:
    """Consulta estado do canal."""
    if not config.MULTI_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="multi-whatsapp desabilitado")
    canal = get_channel_for_loja(db, loja_id, canal_id)
    prov = provider or get_whatsapp_provider()
    st = prov.status(canal)
    out = _canal_dict(canal)
    out["estado"] = st.estado
    out["ativo"] = st.ativo
    return out


def disconnect_channel(
    db: Session,
    loja_id: str,
    canal_id: str,
    provider: WhatsAppProvider | None = None,
) -> dict[str, Any]:
    """Desconecta o canal (permanece na loja; reconectável)."""
    if not config.MULTI_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="multi-whatsapp desabilitado")
    canal = get_channel_for_loja(db, loja_id, canal_id)
    if not canal.ativo or canal.estado == ESTADO_INATIVO:
        raise HTTPException(status_code=409, detail="canal inativo")
    prov = provider or get_whatsapp_provider()
    st = prov.disconnect(canal)
    db.commit()
    db.refresh(canal)
    out = _canal_dict(canal)
    out["estado"] = st.estado
    return out


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
        estado=ESTADO_CONECTADO,  # legado já em operação
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


def resolve_canal_for_instance(db: Session, instancia: str) -> WhatsAppCanal:
    """Resolve canal pela instância; backfill legado se só existir em Loja.

    Instância desconhecida → 404 (alerta operacional / n8n).
    """
    instancia = (instancia or "").strip()
    if not instancia:
        raise HTTPException(status_code=404, detail="instância não reconhecida")

    canal = get_channel_by_instance(db, instancia)
    if canal is not None:
        return canal

    loja = (
        db.query(Loja).filter(Loja.evolution_instance == instancia).first()
    )
    if loja is None:
        raise HTTPException(status_code=404, detail="instância não reconhecida")

    backfill_legacy_from_loja(db, loja.id)
    canal = get_channel_by_instance(db, instancia)
    if canal is None:
        raise HTTPException(status_code=404, detail="instância não reconhecida")
    return canal
