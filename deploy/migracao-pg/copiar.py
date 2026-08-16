"""Carga SQLite → Postgres, tabela a tabela, em ordem topológica de FK."""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import MetaData, create_engine, func, insert, select

from tipos import converter, ler_cru

IGNORADAS = {"alembic_version", "alembic_version_revy_trafego"}


class CargaRecusada(Exception):
    """O destino não estava vazio. Carregar duas vezes duplicaria tudo."""


def copiar(
    origem_url: str, destino_url: str, schema: str | None, lote: int = 500
) -> dict[str, int]:
    origem_engine = create_engine(origem_url)
    destino_engine = create_engine(destino_url)

    md_origem = MetaData()
    md_origem.reflect(bind=origem_engine)
    md_destino = MetaData()
    md_destino.reflect(bind=destino_engine, schema=schema)

    por_nome = {t.name: t for t in md_origem.tables.values()}
    alvos = [t for t in md_destino.sorted_tables if t.name not in IGNORADAS]

    # Recusa ANTES de escrever qualquer coisa: uma segunda carga por cima é
    # indistinguível de dado legítimo depois do fato.
    with destino_engine.connect() as conn:
        for t_dst in alvos:
            existentes = conn.execute(
                select(func.count()).select_from(t_dst)
            ).scalar_one()
            if existentes:
                raise CargaRecusada(
                    f"`{t_dst.name}` ja tem {existentes} linha(s) no destino"
                )

    contagem: dict[str, int] = {}
    with origem_engine.connect() as org, destino_engine.begin() as dst:
        for t_dst in alvos:
            t_org = por_nome.get(t_dst.name)
            if t_org is None:
                contagem[t_dst.name] = 0
                continue

            colunas = [c for c in t_dst.columns if c.name in t_org.columns]
            # Leitura CRUA (ver `tipos.ler_cru`), na mesma ordem de `colunas`.
            # Com `select()` tipado, `converter()` receberia o que o SQLAlchemy
            # já decidiu — `True` onde o arquivo tem `2`, um Decimal já
            # arredondado onde o arquivo tem mais casas — e `ValorInconvertivel`
            # nunca dispararia fora dos testes unitários: a carga coagiria em
            # silêncio. Só lendo cru a conversão passa a ser de verdade dirigida
            # pelo tipo de DESTINO.
            resultado = ler_cru(org, t_org.name, [c.name for c in colunas])
            total = 0
            while True:
                bloco = resultado.fetchmany(lote)
                if not bloco:
                    break
                dst.execute(
                    insert(t_dst),
                    [
                        {
                            c.name: converter(valor, c.type)
                            for c, valor in zip(colunas, linha)
                        }
                        for linha in bloco
                    ],
                )
                total += len(bloco)
            contagem[t_dst.name] = total

    return contagem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--lote", type=int, default=500)
    args = parser.parse_args()
    contagem = copiar(args.origem, args.destino, args.schema, lote=args.lote)
    for nome in sorted(contagem):
        print(f"{nome}: {contagem[nome]}")
    print(f"\n{len(contagem)} tabela(s), {sum(contagem.values())} linha(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
