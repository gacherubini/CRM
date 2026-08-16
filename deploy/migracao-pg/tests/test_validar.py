from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column, DateTime, MetaData, Numeric, String, Table, create_engine, insert,
)

from copiar import copiar
from validar import validar


def _banco(tmp_path: Path, nome: str):
    url = f"sqlite:///{tmp_path / nome}"
    engine = create_engine(url)
    md = MetaData()
    Table(
        "vendas",
        md,
        Column("id", String(36), primary_key=True),
        Column("valor", Numeric(12, 2)),
        Column("criado_em", DateTime(timezone=True)),
    )
    md.create_all(engine)
    return url, engine, md


def test_carga_correta_nao_reporta_divergencia(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, _, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [
                {"id": "v1", "valor": 1000.50,
                 "criado_em": datetime(2026, 8, 16, 10, 0)},
                {"id": "v2", "valor": 250.25,
                 "criado_em": datetime(2026, 8, 16, 11, 0)},
            ],
        )
    copiar(origem_url, destino_url, schema=None)
    assert validar(origem_url, destino_url, schema=None) == []


def test_acha_linha_faltando(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 10.0, "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    divergencias = validar(origem_url, destino_url, schema=None)
    assert any("vendas" in d and "linha" in d for d in divergencias)


def test_acha_centavo_perdido(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 1000.50,
              "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    with destino.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 1000.49,
              "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    divergencias = validar(origem_url, destino_url, schema=None)
    assert any("vendas.valor" in d for d in divergencias)
