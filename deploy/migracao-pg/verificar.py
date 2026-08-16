"""Pré-voo: encontra, antes da janela, tudo que o Postgres vai recusar.

Roda contra a CÓPIA do SQLite e contra o Postgres já migrado e vazio — os tipos,
as FKs e os NOT NULL de verdade vêm de lá, não de um modelo importado.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy import types as sqltypes


def _tabelas(md: MetaData) -> dict:
    return {t.name: t for t in md.tables.values()}


def verificar(origem_url: str, destino_url: str, schema: str | None) -> list[str]:
    origem_engine = create_engine(origem_url)
    destino_engine = create_engine(destino_url)

    md_origem = MetaData()
    md_origem.reflect(bind=origem_engine)
    md_destino = MetaData()
    md_destino.reflect(bind=destino_engine, schema=schema)

    origem = _tabelas(md_origem)
    destino = _tabelas(md_destino)
    problemas: list[str] = []

    ignoradas = {"alembic_version", "alembic_version_revy_trafego"}

    for nome in sorted(set(origem) - set(destino) - ignoradas):
        problemas.append(f"tabela `{nome}` existe na origem e nao no destino")
    for nome in sorted(set(destino) - set(origem) - ignoradas):
        problemas.append(f"tabela `{nome}` existe no destino e nao na origem")

    with origem_engine.connect() as conn:
        for nome in sorted(set(origem) & set(destino) - ignoradas):
            t_org = origem[nome]
            t_dst = destino[nome]

            for col_dst in t_dst.columns:
                col_org = t_org.columns.get(col_dst.name)
                if col_org is None:
                    problemas.append(
                        f"coluna `{nome}.{col_dst.name}` existe no destino e nao na origem"
                    )
                    continue

                if not col_dst.nullable:
                    nulos = conn.execute(
                        select(func.count()).select_from(t_org).where(col_org.is_(None))
                    ).scalar_one()
                    if nulos:
                        problemas.append(
                            f"`{nome}.{col_dst.name}` e NOT NULL no destino e tem "
                            f"{nulos} linha(s) NULL na origem"
                        )

                tipo = col_dst.type
                if isinstance(tipo, sqltypes.String) and tipo.length:
                    longos = conn.execute(
                        select(func.count())
                        .select_from(t_org)
                        .where(func.length(col_org) > tipo.length)
                    ).scalar_one()
                    if longos:
                        problemas.append(
                            f"`{nome}.{col_dst.name}` e VARCHAR({tipo.length}) e tem "
                            f"{longos} valor(es) maior(es) na origem"
                        )

                if isinstance(tipo, sqltypes.Boolean):
                    # exec_driver_sql pula o result-processor do tipo Boolean, que
                    # coagiria qualquer inteiro truthy (ex.: 2) para True antes do
                    # `not in` rodar e esconderia o valor sujo de verdade.
                    linhas = conn.exec_driver_sql(
                        f'SELECT DISTINCT "{col_dst.name}" FROM "{nome}" '
                        f'WHERE "{col_dst.name}" IS NOT NULL'
                    )
                    for (valor,) in linhas:
                        if valor not in (0, 1, False, True):
                            problemas.append(
                                f"`{nome}.{col_dst.name}` e booleano e tem o valor "
                                f"{valor!r} na origem"
                            )

                if isinstance(tipo, sqltypes.Numeric) and not isinstance(
                    tipo, sqltypes.Float
                ):
                    escala = tipo.scale
                    if escala is not None:
                        demais = 0
                        for (valor,) in conn.execute(
                            select(col_org).where(col_org.isnot(None))
                        ):
                            try:
                                exp = Decimal(str(valor)).as_tuple().exponent
                            except InvalidOperation:
                                problemas.append(
                                    f"`{nome}.{col_dst.name}` tem valor nao numerico "
                                    f"{valor!r} na origem"
                                )
                                continue
                            if isinstance(exp, int) and exp < -escala:
                                demais += 1
                        if demais:
                            problemas.append(
                                f"`{nome}.{col_dst.name}` e NUMERIC(escala={escala}) e "
                                f"tem {demais} valor(es) com mais casas — o Postgres vai "
                                f"arredondar e a soma da validacao vai divergir"
                            )

            for fk in t_dst.foreign_keys:
                col_filha = t_org.columns.get(fk.parent.name)
                mae_nome = fk.column.table.name
                t_mae = origem.get(mae_nome)
                if col_filha is None or t_mae is None:
                    continue
                col_mae = t_mae.columns.get(fk.column.name)
                if col_mae is None:
                    continue
                orfas = conn.execute(
                    select(func.count())
                    .select_from(t_org)
                    .where(
                        col_filha.isnot(None),
                        col_filha.notin_(select(col_mae)),
                    )
                ).scalar_one()
                if orfas:
                    problemas.append(
                        f"`{nome}.{fk.parent.name}` tem {orfas} linha(s) orfa(s) "
                        f"apontando para `{mae_nome}.{fk.column.name}` — o SQLite nao "
                        f"verifica FK, o Postgres verifica"
                    )

    return problemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    problemas = verificar(args.origem, args.destino, args.schema)
    for p in problemas:
        print(f"PROBLEMA: {p}")
    print(f"\n{len(problemas)} problema(s).")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
