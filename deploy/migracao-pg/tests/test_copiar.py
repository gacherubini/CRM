from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, MetaData, Numeric, String, Table,
    create_engine, insert, select,
)

from copiar import CargaRecusada, copiar


def _esquema():
    md = MetaData()
    Table("mae", md, Column("id", String(36), primary_key=True))
    Table(
        "filha",
        md,
        Column("id", String(36), primary_key=True),
        Column("mae_id", String(36), ForeignKey("mae.id")),
        Column("valor", Numeric(12, 2)),
        Column("quando", DateTime(timezone=True)),
        Column("ativo", Boolean()),
    )
    return md


def _banco(tmp_path: Path, nome: str):
    url = f"sqlite:///{tmp_path / nome}"
    engine = create_engine(url)
    md = _esquema()
    md.create_all(engine)
    return url, engine, md


def test_copia_respeitando_a_ordem_de_fk(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}, {"id": "m2"}])
        conn.execute(
            insert(md.tables["filha"]),
            [
                {"id": "f1", "mae_id": "m1", "valor": 118900.0,
                 "quando": datetime(2026, 8, 16, 10, 0), "ativo": 1},
                {"id": "f2", "mae_id": "m2", "valor": 0.1,
                 "quando": datetime(2026, 8, 16, 11, 0), "ativo": 0},
            ],
        )

    contagem = copiar(origem_url, destino_url, schema=None)
    assert contagem == {"mae": 2, "filha": 2}

    with destino.connect() as conn:
        linhas = conn.execute(
            select(md.tables["filha"]).order_by(md.tables["filha"].c.id)
        ).mappings().all()
    assert linhas[0]["valor"] == Decimal("118900.00")
    assert linhas[1]["valor"] == Decimal("0.10")
    assert linhas[0]["ativo"] is True
    assert linhas[1]["ativo"] is False


def test_recusa_carregar_por_cima_de_tabela_com_linha(tmp_path):
    """Rodar duas vezes duplicaria tudo. Tem que parar antes de escrever."""
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
    with destino.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "ja-estava"}])

    with pytest.raises(CargaRecusada):
        copiar(origem_url, destino_url, schema=None)


def test_tabela_vazia_na_origem_nao_quebra(tmp_path):
    origem_url, _, _ = _banco(tmp_path, "origem.db")
    destino_url, _, _ = _banco(tmp_path, "destino.db")
    assert copiar(origem_url, destino_url, schema=None) == {"mae": 0, "filha": 0}


def test_lote_menor_que_o_total_copia_tudo(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["mae"]), [{"id": f"m{i}"} for i in range(25)]
        )
    assert copiar(origem_url, destino_url, schema=None, lote=7)["mae"] == 25
