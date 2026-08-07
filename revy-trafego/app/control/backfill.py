from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Connection


TABELAS_LEGADAS_COM_LOJA = (
    "vendas_projetadas",
    "meta_pixel_config",
    "meta_ads_config",
    "pixel_capi_auditoria",
    "meta_capi_outbox",
    "campanhas",
    "campanha_gastos",
)
_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def slug_canonico(valor: str) -> str:
    slug = (valor or "").strip().lower()
    if len(slug) > 120 or not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"loja_slug inválido para backfill: {valor!r}")
    return slug


def religar_vendas_orfas(connection: Connection) -> int:
    """Preenche ``vendas_projetadas.loja_id`` onde ficou nulo; devolve quantas.

    A projecao so gravava ``loja_slug``, entao vendas recebidas do Portal depois
    da 0002 sumiam da Visao Geral do Control, que filtra por ``loja_id``.
    Vinculos ja existentes nunca sao sobrescritos.
    """
    inspector = sa.inspect(connection)
    tabelas = set(inspector.get_table_names())
    if "vendas_projetadas" not in tabelas or "lojas" not in tabelas:
        return 0

    metadata = sa.MetaData()
    vendas = sa.Table("vendas_projetadas", metadata, autoload_with=connection)
    lojas = sa.Table("lojas", metadata, autoload_with=connection)
    if "loja_id" not in vendas.c:
        return 0

    loja_id = (
        sa.select(lojas.c.id)
        .where(lojas.c.slug == sa.func.lower(sa.func.trim(vendas.c.loja_slug)))
        .scalar_subquery()
    )
    resultado = connection.execute(
        sa.update(vendas)
        .where(vendas.c.loja_id.is_(None), loja_id.is_not(None))
        .values(loja_id=loja_id)
    )
    return int(resultado.rowcount or 0)


def backfill_lojas_confirmadas(
    connection: Connection,
    slugs_confirmados: Iterable[str] = (),
) -> dict[str, str]:
    """Cria lojas ausentes e liga dados legados sem sobrescrever vínculos existentes."""
    inspector = sa.inspect(connection)
    tabelas_existentes = set(inspector.get_table_names())
    slugs = {slug_canonico(slug) for slug in slugs_confirmados}

    metadata = sa.MetaData()
    tabelas: list[sa.Table] = []
    for nome in TABELAS_LEGADAS_COM_LOJA:
        if nome not in tabelas_existentes:
            continue
        tabela = sa.Table(nome, metadata, autoload_with=connection)
        tabelas.append(tabela)
        valores = connection.execute(
            sa.select(tabela.c.loja_slug).distinct()
        ).scalars()
        slugs.update(slug_canonico(valor) for valor in valores if valor)

    lojas = sa.Table("lojas", metadata, autoload_with=connection)
    ids_por_slug = dict(
        connection.execute(sa.select(lojas.c.slug, lojas.c.id)).all()
    )
    agora = datetime.now(timezone.utc)
    faltantes = sorted(slugs - ids_por_slug.keys())
    if faltantes:
        connection.execute(
            sa.insert(lojas),
            [
                {
                    "id": str(uuid.uuid4()),
                    "slug": slug,
                    "nome": slug,
                    "status": "rascunho",
                    "criada_em": agora,
                    "atualizada_em": agora,
                }
                for slug in faltantes
            ],
        )
        ids_por_slug.update(
            connection.execute(
                sa.select(lojas.c.slug, lojas.c.id).where(lojas.c.slug.in_(faltantes))
            ).all()
        )

    for tabela in tabelas:
        if "loja_id" not in tabela.c:
            continue
        slug_da_linha = sa.func.lower(sa.func.trim(tabela.c.loja_slug))
        loja_id = (
            sa.select(lojas.c.id)
            .where(lojas.c.slug == slug_da_linha)
            .scalar_subquery()
        )
        connection.execute(
            sa.update(tabela)
            .where(tabela.c.loja_id.is_(None), loja_id.is_not(None))
            .values(loja_id=loja_id)
        )

    return {slug: ids_por_slug[slug] for slug in sorted(slugs)}
