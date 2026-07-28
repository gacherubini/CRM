"""Descoberta de loja_slug a partir das tabelas de mídia/vendas (Fase 1)."""
from __future__ import annotations

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.models import Campanha, MetaAdsConfig, MetaPixelConfig, Venda


def listar_loja_slugs(db: Session) -> list[str]:
    slugs: set[str] = set()
    for model, col in (
        (Campanha, Campanha.loja_slug),
        (MetaPixelConfig, MetaPixelConfig.loja_slug),
        (MetaAdsConfig, MetaAdsConfig.loja_slug),
        (Venda, Venda.loja_slug),
    ):
        try:
            for (slug,) in db.query(distinct(col)).all():
                if slug and str(slug).strip():
                    slugs.add(str(slug).strip())
        except Exception:
            # Tabela pode não existir ainda em DB vazio de testes isolados.
            continue
    return sorted(slugs)
