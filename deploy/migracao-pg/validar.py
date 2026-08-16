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

from tipos import ler_cru

IGNORADAS = {"alembic_version", "alembic_version_revy_trafego"}


def _soma_crua(conn, tabela: str, coluna: str, schema: str | None = None) -> Decimal:
    """Soma lendo CRU dos dois lados (ver `tipos.ler_cru`).

    `select(func.sum(col))` infere o `Numeric(12,2)` e arredonda **na leitura
    da validação** — exatamente o mesmo arredondamento que o Postgres aplicou
    na carga. Os dois lados batem, o portão imprime "Corte liberado" e os
    centavos já foram embora. Somando cru, `10.00567` na origem contra `10.01`
    no destino vira divergência, que é o que ela é.

    Sem tolerância, de propósito: depois de `verificar.py` barrar casas
    decimais a mais no pré-voo, as duas somas têm que ser **exatamente** iguais.
    Uma tolerância aqui seria um número escolhido para o teste passar, e é
    justamente isso que este portão existe para não fazer.
    """
    total = Decimal("0")
    for (valor,) in ler_cru(conn, tabela, [coluna], schema=schema):
        if valor is not None:
            total += Decimal(str(valor))
    return total


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

    alvos = [t for t in md_destino.sorted_tables if t.name not in IGNORADAS]
    nomes_dst = {t.name for t in alvos}
    nomes_org = set(por_nome_org) - IGNORADAS

    # Não comparar nada não é o mesmo que não achar divergência. Com `--schema`
    # errado (typo, ou o schema do outro produto), ou rodando antes do
    # `alembic upgrade head`, o `reflect` devolve zero tabela SEM erro: a lista
    # sairia vazia, o exit code seria 0 e o portão liberaria o corte tendo
    # comparado exatamente nada.
    if not alvos:
        divergencias.append(
            "o destino nao tem tabela nenhuma"
            + (f" no schema `{schema}`" if schema else "")
            + " — schema errado ou `alembic upgrade head` nao rodou; "
            "nada foi comparado"
        )

    # Só-na-origem nunca era visitado: o laço itera o DESTINO. Uma tabela que
    # exista no `.db` e não na cadeia de migrations sumiria em silêncio.
    for so_na_origem in sorted(nomes_org - nomes_dst):
        divergencias.append(
            f"`{so_na_origem}` existe na origem e nao no destino — "
            f"a carga nao levou essa tabela"
        )

    with origem_engine.connect() as org, destino_engine.connect() as dst:
        for t_dst in alvos:
            t_org = por_nome_org.get(t_dst.name)
            if t_org is None:
                divergencias.append(f"`{t_dst.name}` nao existe na origem")
                continue

            for col_so_na_origem in sorted(
                set(t_org.columns.keys()) - set(t_dst.columns.keys())
            ):
                divergencias.append(
                    f"`{t_dst.name}.{col_so_na_origem}` existe na origem e nao "
                    f"no destino — a carga descartou esses valores"
                )

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
                    s_org = _soma_crua(org, t_org.name, col_org.name)
                    s_dst = _soma_crua(dst, t_dst.name, col.name, schema=schema)
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
