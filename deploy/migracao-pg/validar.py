"""O portão do corte: compara os dois lados e devolve toda divergência.

Enquanto esta lista não estiver vazia, produção continua nos `.db` e nada foi
perdido. Qualquer item aqui aborta o corte.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy import types as sqltypes

IGNORADAS = {"alembic_version", "alembic_version_revy_trafego"}


def _decimal(valor) -> Decimal:
    return Decimal("0") if valor is None else Decimal(str(valor))


def _utc_naive(valor):
    """Compara instantes sem depender de tzinfo: o SQLite devolve naive (UTC) e
    o Postgres devolve aware (UTC)."""
    if valor is None:
        return None
    return valor.replace(tzinfo=None) if valor.tzinfo else valor


def validar(origem_url: str, destino_url: str, schema: str | None) -> list[str]:
    origem_engine = create_engine(origem_url)
    destino_engine = create_engine(destino_url)

    md_origem = MetaData()
    md_origem.reflect(bind=origem_engine)
    md_destino = MetaData()
    md_destino.reflect(bind=destino_engine, schema=schema)

    por_nome_org = {t.name: t for t in md_origem.tables.values()}
    divergencias: list[str] = []

    with origem_engine.connect() as org, destino_engine.connect() as dst:
        for t_dst in md_destino.sorted_tables:
            if t_dst.name in IGNORADAS:
                continue
            t_org = por_nome_org.get(t_dst.name)
            if t_org is None:
                divergencias.append(f"`{t_dst.name}` nao existe na origem")
                continue

            n_org = org.execute(select(func.count()).select_from(t_org)).scalar_one()
            n_dst = dst.execute(select(func.count()).select_from(t_dst)).scalar_one()
            if n_org != n_dst:
                divergencias.append(
                    f"`{t_dst.name}`: {n_org} linha(s) na origem, {n_dst} no destino"
                )

            for col in t_dst.columns:
                col_org = t_org.columns.get(col.name)
                if col_org is None:
                    continue

                if isinstance(col.type, sqltypes.Numeric) and not isinstance(
                    col.type, sqltypes.Float
                ):
                    s_org = _decimal(
                        org.execute(select(func.sum(col_org))).scalar_one()
                    )
                    s_dst = _decimal(
                        dst.execute(select(func.sum(col))).scalar_one()
                    )
                    if s_org != s_dst:
                        divergencias.append(
                            f"`{t_dst.name}.{col.name}`: soma {s_org} na origem, "
                            f"{s_dst} no destino (diferenca {s_dst - s_org})"
                        )

                if isinstance(col.type, sqltypes.DateTime):
                    m_org = _utc_naive(
                        org.execute(select(func.max(col_org))).scalar_one()
                    )
                    m_dst = _utc_naive(
                        dst.execute(select(func.max(col))).scalar_one()
                    )
                    if m_org != m_dst:
                        divergencias.append(
                            f"`{t_dst.name}.{col.name}`: max {m_org} na origem, "
                            f"{m_dst} no destino"
                        )

    return divergencias


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    divergencias = validar(args.origem, args.destino, args.schema)
    for d in divergencias:
        print(f"DIVERGENCIA: {d}")
    if divergencias:
        print(f"\n{len(divergencias)} divergencia(s). NAO LIBERAR O CORTE.")
        return 1
    print("\nSem divergencia. Corte liberado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
