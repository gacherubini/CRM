"""Descoberta de loja_slug a partir das tabelas de mídia/vendas (Fase 1)."""
from __future__ import annotations

import os

from sqlalchemy import distinct, text
from sqlalchemy.orm import Session

from app.models import Campanha, MetaAdsConfig, MetaPixelConfig, Venda


def _parse_lista_env(raw: str) -> set[str]:
    out: set[str] = set()
    for part in (raw or "").replace(";", ",").split(","):
        s = part.strip()
        if s:
            out.add(s)
    return out


def _slugs_env_explicitos() -> set[str]:
    """Só envs explícitos de lista (sempre unem ao resultado)."""
    return _parse_lista_env(
        os.getenv("REVY_TRAFEGO_LOJAS") or os.getenv("PORTAL_LOJAS") or ""
    )


def _slugs_fallback_catalogo() -> set[str]:
    """Fallback quando o DB ainda não tem lojas de mídia/vendas."""
    seeds: set[str] = set()
    for key in (
        "CATALOGO_DEFAULT_STORE_SLUG",
        "CATALOGO_PORTAL_STORE_SLUG",
        "PORTAL_DEFAULT_LOJA_SLUG",
    ):
        v = (os.getenv(key) or "").strip()
        if v:
            seeds.add(v)
    if not seeds:
        seeds.update({"loja1", "moto-center"})
    return seeds


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
    try:
        for (slug,) in db.execute(
            text("SELECT DISTINCT loja_slug FROM usuarios WHERE loja_slug IS NOT NULL")
        ):
            if slug and str(slug).strip():
                slugs.add(str(slug).strip())
    except Exception:
        pass
    slugs |= _slugs_env_explicitos()
    if not slugs:
        slugs |= _slugs_fallback_catalogo()
    return sorted(slugs)
