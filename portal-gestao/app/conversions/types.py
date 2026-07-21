"""Contratos estáveis dos eventos de conversão outbound."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


class ConversionKind(str, Enum):
    """Tipos de conversão entendidos pelo bus."""

    PURCHASE = "purchase"


@dataclass(frozen=True)
class PurchaseConversion:
    """Snapshot mínimo de uma venda confirmada para adapters externos."""

    loja_slug: str
    venda_id: str
    event_id: str
    value: Decimal
    currency: str = "BRL"
    lead_ref: str | None = None
    phone: str | None = None
    email: str | None = None
    fbclid: str | None = None
    fbc: str | None = None
    gclid: str | None = None

    @classmethod
    def from_sale(
        cls,
        sale: Any,
        lead: Mapping[str, Any] | None = None,
    ) -> "PurchaseConversion":
        """Cria um snapshot sem acoplar o contrato ao model SQLAlchemy."""

        lead_data = lead or {}
        venda_id = str(sale.id)
        return cls(
            loja_slug=str(sale.loja_slug),
            venda_id=venda_id,
            event_id=f"purchase-{venda_id}",
            value=Decimal(str(sale.preco_venda)),
            lead_ref=getattr(sale, "lead_ref", None),
            phone=lead_data.get("telefone"),
            email=lead_data.get("email"),
            fbclid=lead_data.get("fbclid"),
            fbc=lead_data.get("fbc"),
            gclid=lead_data.get("gclid"),
        )
