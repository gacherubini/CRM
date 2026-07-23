"""Adapter Meta CAPI sobre o outbox já existente."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import meta_capi
from app.conversions.types import ConversionKind, PurchaseConversion


class MetaAdapter:
    """Traduz PurchaseConversion para o outbox Meta compatível com a Fase A."""

    name = "meta"

    def handle(
        self,
        kind: ConversionKind,
        payload: PurchaseConversion,
        db: Session,
    ) -> object:
        if kind is not ConversionKind.PURCHASE:
            return None
        # Uma venda CTWA pertence ao canal Business Messaging. Enviar também o
        # Purchase web criaria duas conversões com event_ids distintos.
        if (payload.ctwa_clid or "").strip():
            return None
        lead = {
            "telefone": payload.phone,
            "email": payload.email,
            "fbclid": payload.fbclid,
            "fbc": payload.fbc,
            # ctwa_clid não vai no CAPI web; messaging adapter trata à parte
        }
        return meta_capi.enfileirar_purchase(
            db,
            loja_slug=payload.loja_slug,
            venda_id=payload.venda_id,
            event_id=payload.event_id,
            value=payload.value,
            currency=payload.currency,
            lead=lead,
        )
