"""Adapter Meta CAPI messaging (CTWA)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import meta_capi_messaging
from app.conversions.types import ConversionKind, PurchaseConversion


class MetaMessagingAdapter:
    """Envia Purchase com ctwa_clid quando o lead veio de Click-to-WhatsApp."""

    name = "meta_messaging"

    def handle(
        self,
        kind: ConversionKind,
        payload: PurchaseConversion,
        db: Session,
    ) -> object:
        if kind is not ConversionKind.PURCHASE:
            return None
        if not (payload.ctwa_clid or "").strip():
            return None
        return meta_capi_messaging.enfileirar_purchase_messaging(
            db,
            loja_slug=payload.loja_slug,
            venda_id=payload.venda_id,
            event_id=f"purchase-msg-{payload.venda_id}",
            value=payload.value,
            currency=payload.currency,
            ctwa_clid=payload.ctwa_clid,
            phone=payload.phone,
            email=payload.email,
        )
