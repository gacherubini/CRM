"""Projecao local de vendas recebidas do Portal.

O Portal continua dono da venda. Este modulo mantem somente o snapshot minimo
necessario a ROI e rejeita entregas antigas, permitindo retry e reordenacao.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import VendaProjetada


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


@dataclass(frozen=True)
class VendaSnapshot:
    venda_id: str
    loja_slug: str
    status: str
    valor: Decimal
    atualizada_em: datetime
    lead_ref: str | None = None
    criada_em: datetime | None = None
    confirmada_em: datetime | None = None
    custo_veiculo: Decimal | None = None
    custos_diretos_total: Decimal = Decimal("0")
    campanha_id_first: str | None = None
    campanha_id_last: str | None = None
    utm_campaign_first: str | None = None
    utm_campaign_last: str | None = None


@dataclass(frozen=True)
class ProjecaoResultado:
    venda: VendaProjetada
    aplicada: bool
    motivo: str


def projetar_venda(db: Session, snapshot: VendaSnapshot) -> ProjecaoResultado:
    """Insere/atualiza uma venda por versao, sem commit implicito."""
    versao = _utc(snapshot.atualizada_em)
    existente = db.get(VendaProjetada, (snapshot.venda_id, snapshot.loja_slug))
    if existente is not None:
        versao_existente = _utc(existente.atualizada_em)
        if versao_existente > versao:
            return ProjecaoResultado(existente, False, "evento_antigo")
        if versao_existente == versao and existente.status == snapshot.status:
            return ProjecaoResultado(existente, False, "idempotente")
        venda = existente
    else:
        venda = VendaProjetada(
            id=snapshot.venda_id,
            loja_slug=snapshot.loja_slug,
        )
        db.add(venda)

    venda.loja_slug = snapshot.loja_slug
    venda.lead_ref = snapshot.lead_ref
    venda.preco_venda = snapshot.valor
    venda.custo_veiculo = snapshot.custo_veiculo
    venda.custos_diretos_total = snapshot.custos_diretos_total
    venda.status = snapshot.status
    venda.criada_em = _utc(
        snapshot.criada_em or snapshot.confirmada_em or snapshot.atualizada_em
    )
    venda.confirmada_em = (
        _utc(snapshot.confirmada_em) if snapshot.confirmada_em else None
    )
    venda.atualizada_em = versao
    venda.campanha_id_first = snapshot.campanha_id_first
    venda.campanha_id_last = snapshot.campanha_id_last
    venda.utm_campaign_first = snapshot.utm_campaign_first
    venda.utm_campaign_last = snapshot.utm_campaign_last
    db.flush()
    return ProjecaoResultado(venda, True, "aplicada")
