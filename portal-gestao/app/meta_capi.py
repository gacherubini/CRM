"""Meta Conversions API (CAPI) — envio best-effort de Purchase (E10).

Falha HTTP/rede **nunca** deve interromper a confirmação de venda.
"""
from __future__ import annotations


import hashlib
import json
import logging
import time
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.cripto import decifrar
from app.models import MetaCapiOutbox, MetaPixelConfig, Venda, agora, novo_id

logger = logging.getLogger(__name__)

GRAPH_EVENTS_URL = "https://graph.facebook.com/v21.0/{pixel_id}/events"
DEFAULT_TIMEOUT = 5.0


def erro_envio_sanitizado(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return f"Meta respondeu HTTP {exc.response.status_code}."
    if isinstance(exc, httpx.RequestError):
        return "Falha de rede ao contatar a Meta."
    return "Falha interna ao enviar o evento para a Meta."


def hash_sha256_normalizado(valor: str | None) -> str | None:
    digitos = "".join(c for c in (valor or "") if c.isdigit())
    if not digitos:
        return None
    return hashlib.sha256(digitos.encode("utf-8")).hexdigest()


def hash_email_normalizado(valor: str | None) -> str | None:
    email = (valor or "").strip().casefold()
    return hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None


def montar_payload_purchase(
    *,
    event_id: str,
    value: Decimal | float | str,
    currency: str = "BRL",
    phone: str | None = None,
    email: str | None = None,
    fbclid: str | None = None,
    fbc: str | None = None,
    test_event_code: str | None = None,
) -> dict[str, Any]:
    user_data: dict[str, Any] = {}
    ph = hash_sha256_normalizado(phone)
    if ph:
        user_data["ph"] = [ph]
    em = hash_email_normalizado(email)
    if em:
        user_data["em"] = [em]
    event_time = int(time.time())
    fbc_normalizado = (fbc or "").strip() or None
    if not fbc_normalizado and (fbclid or "").strip():
        fbc_normalizado = f"fb.1.{event_time}.{fbclid.strip()}"
    if fbc_normalizado:
        user_data["fbc"] = fbc_normalizado
    # Meta exige ao menos um identificador; external_id estável serve como fallback.
    user_data.setdefault(
        "external_id",
        [hashlib.sha256(event_id.encode("utf-8")).hexdigest()],
    )
    event = {
        "event_name": "Purchase",
        "event_time": event_time,
        "event_id": event_id,
        "action_source": "system_generated",
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


def enviar_eventos_capi(
    *,
    pixel_id: str,
    access_token: str,
    body: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    url = GRAPH_EVENTS_URL.format(pixel_id=pixel_id)
    with httpx.Client(timeout=timeout) as client:
        resposta = client.post(url, params={"access_token": access_token}, json=body)
        resposta.raise_for_status()
        return resposta


def _config_loja(db: Session, loja_slug: str) -> MetaPixelConfig | None:
    return (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == loja_slug)
        .first()
    )


def enfileirar_purchase_venda(
    db: Session,
    venda: Venda,
    lead: dict[str, Any] | None = None,
) -> MetaCapiOutbox | None:
    """Persiste outbox Purchase e tenta envio uma vez. Nunca levanta para o caller."""
    try:
        config = _config_loja(db, venda.loja_slug)
        if (
            config is None
            or not config.enviar_purchase
            or not (config.pixel_id or "").strip()
            or not config.token_ciphertext
        ):
            return None

        event_id = f"purchase-{venda.id}"
        existente = (
            db.query(MetaCapiOutbox)
            .filter(MetaCapiOutbox.event_id == event_id)
            .first()
        )
        if existente is not None:
            return existente

        body = montar_payload_purchase(
            event_id=event_id,
            value=venda.preco_venda,
            currency="BRL",
            phone=(lead or {}).get("telefone"),
            email=(lead or {}).get("email"),
            fbclid=(lead or {}).get("fbclid"),
            fbc=(lead or {}).get("fbc"),
            test_event_code=(config.test_event_code or None),
        )
        outbox = MetaCapiOutbox(
            id=novo_id(),
            loja_slug=venda.loja_slug,
            venda_id=venda.id,
            event_id=event_id,
            event_name="Purchase",
            payload_json=json.dumps(body, ensure_ascii=False, sort_keys=True),
            status="pending",
            criada_em=agora(),
            atualizada_em=agora(),
        )
        db.add(outbox)
        db.commit()
        db.refresh(outbox)
        tentar_enviar_outbox(db, outbox, config)
        return outbox
    except Exception:
        logger.exception(
            "meta_capi: falha ao enfileirar Purchase da venda %s (venda já confirmada)",
            getattr(venda, "id", "?"),
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None


def tentar_enviar_outbox(
    db: Session,
    outbox: MetaCapiOutbox,
    config: MetaPixelConfig | None = None,
) -> bool:
    """Tenta enviar um item da outbox. Retorna True se entregue. Não propaga erro."""
    try:
        if config is None:
            config = _config_loja(db, outbox.loja_slug)
        if config is None or not config.token_ciphertext or not config.pixel_id:
            outbox.status = "failed"
            outbox.last_error = "config Meta incompleta"
            outbox.attempts = (outbox.attempts or 0) + 1
            outbox.atualizada_em = agora()
            db.commit()
            return False

        token = decifrar(config.token_ciphertext)
        body = json.loads(outbox.payload_json)
        resposta = enviar_eventos_capi(
            pixel_id=config.pixel_id.strip(),
            access_token=token,
            body=body,
        )
        outbox.status = "delivered"
        outbox.attempts = (outbox.attempts or 0) + 1
        outbox.last_http_status = resposta.status_code
        outbox.last_error = None
        outbox.delivered_at = agora()
        outbox.atualizada_em = agora()
        db.commit()
        return True
    except Exception as exc:
        status_http = (
            exc.response.status_code
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None
            else None
        )
        logger.warning(
            "meta_capi: envio falhou event_id=%s tipo=%s http_status=%s",
            outbox.event_id,
            type(exc).__name__,
            status_http,
        )
        try:
            outbox.status = "failed"
            outbox.attempts = (outbox.attempts or 0) + 1
            outbox.last_error = erro_envio_sanitizado(exc)
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                outbox.last_http_status = exc.response.status_code
            outbox.atualizada_em = agora()
            db.commit()
        except Exception:
            logger.exception("meta_capi: não foi possível marcar outbox como failed")
            try:
                db.rollback()
            except Exception:
                pass
        return False


def processar_outbox_pendentes(
    db: Session,
    loja_slug: str,
    *,
    limite: int = 50,
) -> dict[str, int]:
    """Retenta somente itens da loja, mantendo erros isolados por evento."""
    config = _config_loja(db, loja_slug)
    itens = (
        db.query(MetaCapiOutbox)
        .filter(
            MetaCapiOutbox.loja_slug == loja_slug,
            MetaCapiOutbox.status.in_(("pending", "failed")),
        )
        .order_by(MetaCapiOutbox.criada_em.asc())
        .limit(max(1, min(limite, 100)))
        .all()
    )
    entregues = 0
    for item in itens:
        if tentar_enviar_outbox(db, item, config):
            entregues += 1
    return {"processados": len(itens), "entregues": entregues, "falharam": len(itens) - entregues}
