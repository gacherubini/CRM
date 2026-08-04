"""Sincroniza os ad_ids cadastrados à mão em uma campanha (Fase 1)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.meta_ads_spend import normalizar_meta_campaign_id
from app.models import CampanhaAnuncio, novo_id


def parse_ad_ids(texto: str | None) -> list[str]:
    """Um ad_id por linha; normaliza (só dígitos), descarta vazios e duplicados."""
    vistos: list[str] = []
    for linha in (texto or "").splitlines():
        n = normalizar_meta_campaign_id(linha)
        if n and n not in vistos:
            vistos.append(n)
    return vistos


def sincronizar_anuncios(db: Session, campanha, texto: str | None) -> list[str]:
    """Insere os ad_ids novos e remove os ausentes. Retorna a lista final ordenada."""
    desejados = set(parse_ad_ids(texto))
    atuais = {
        a.ad_id: a
        for a in db.query(CampanhaAnuncio)
        .filter(CampanhaAnuncio.campanha_id == campanha.id)
        .all()
    }
    for ad_id, obj in atuais.items():
        if ad_id not in desejados:
            db.delete(obj)
    for ad_id in desejados:
        if ad_id not in atuais:
            db.add(
                CampanhaAnuncio(
                    id=novo_id(),
                    loja_slug=campanha.loja_slug,
                    campanha_id=campanha.id,
                    ad_id=ad_id,
                )
            )
    return sorted(desejados)
