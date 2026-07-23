"""Meta CAPI for Business Messaging (CTWA) — Purchase com ctwa_clid.

Usa o mesmo Pixel ID + token CAPI da loja; payload com action_source messaging.
Falha nunca propaga para confirmação de venda.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.cripto import decifrar
from app.meta_capi import (
    DEFAULT_TIMEOUT,
    erro_envio_sanitizado,
    hash_email_normalizado,
    hash_sha256_normalizado,
    tentar_enviar_outbox,
)
from app.models import MetaCapiOutbox, MetaPixelConfig, agora, novo_id

logger = logging.getLogger(__name__)


def montar_payload_purchase_messaging(
    *,
    event_id: str,
    value: Decimal | float | str,
    currency: str = "BRL",
    ctwa_clid: str,
    phone: str | None = None,
    email: str | None = None,
    test_event_code: str | None = None,
) -> dict[str, Any]:
    """Payload Graph Events com action_source business_messaging + ctwa_clid."""
    user_data: dict[str, Any] = {
        "ctwa_clid": ctwa_clid.strip(),
    }
    ph = hash_sha256_normalizado(phone)
    if ph:
        user_data["ph"] = [ph]
    em = hash_email_normalizado(email)
    if em:
        user_data["em"] = [em]
    user_data.setdefault(
        "external_id",
        [hashlib.sha256(event_id.encode("utf-8")).hexdigest()],
    )
    event = {
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "business_messaging",
        "messaging_channel": "whatsapp",
        "user_data": user_data,
        "custom_data": {
            "value": float(value),
            "currency": currency,
        },
    }
    body: dict[str, Any] = {"data": [event]}
    if test_event_code:
        body["test_event_code"] = test_event_code
    return body


def enfileirar_purchase_messaging(
    db: Session,
    *,
    loja_slug: str,
    venda_id: str,
    event_id: str,
    value: Decimal | float | str,
    currency: str = "BRL",
    ctwa_clid: str | None,
    phone: str | None = None,
    email: str | None = None,
) -> MetaCapiOutbox | None:
    """Outbox Purchase messaging. No-op se não houver ctwa_clid ou config CAPI."""
    try:
        clid = (ctwa_clid or "").strip()
        if not clid:
            return None
        config = (
            db.query(MetaPixelConfig)
            .filter(MetaPixelConfig.loja_slug == loja_slug)
            .first()
        )
        if (
            config is None
            or not config.enviar_purchase
            or not (config.pixel_id or "").strip()
            or not config.token_ciphertext
        ):
            return None

        existente = (
            db.query(MetaCapiOutbox)
            .filter(MetaCapiOutbox.event_id == event_id)
            .first()
        )
        if existente is not None:
            return existente

        body = montar_payload_purchase_messaging(
            event_id=event_id,
            value=value,
            currency=currency,
            ctwa_clid=clid,
            phone=phone,
            email=email,
            test_event_code=(config.test_event_code or None),
        )
        outbox = MetaCapiOutbox(
            id=novo_id(),
            loja_slug=loja_slug,
            venda_id=venda_id,
            event_id=event_id,
            event_name="Purchase",
            payload_json=json.dumps(body, ensure_ascii=False, sort_keys=True),
            status="pending",
            criada_em=agora(),
            atualizada_em=agora(),
        )
        db.add(outbox)
        try:
            from app.pixel_capi_auditoria import flags_do_payload_capi, registrar_auditoria_pixel

            flags = flags_do_payload_capi(body)
            registrar_auditoria_pixel(
                db,
                loja_slug=loja_slug,
                origem="purchase_messaging",
                event_name="Purchase",
                event_id=event_id,
                pixel_id=config.pixel_id,
                modo="messaging",
                tem_ph=flags["tem_ph"],
                tem_em=flags["tem_em"],
                tem_fbclid=False,
                tem_fbc=flags["tem_fbc"],
                tem_ctwa_clid=flags["tem_ctwa_clid"],
                tem_external_id=flags["tem_external_id"],
                tem_test_event_code=bool(config.test_event_code),
                status="enfileirado",
                venda_id=venda_id,
            )
        except Exception:
            logger.warning("meta_capi_messaging: auditoria ignored")
        db.commit()
        db.refresh(outbox)
        # Reusa envio HTTP do meta_capi (mesmo endpoint Graph /events).
        tentar_enviar_outbox(db, outbox, config)
        return outbox
    except Exception:
        logger.exception(
            "meta_capi_messaging: falha ao enfileirar venda %s (venda já confirmada)",
            venda_id,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None
