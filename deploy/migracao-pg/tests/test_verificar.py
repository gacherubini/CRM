from pathlib import Path

import pytest
from sqlalchemy import (
    Boolean, Column, ForeignKey, MetaData, String, Table, create_engine, insert,
)

from verificar import verificar


def _monta(tmp_path: Path, nome: str):
    url = f"sqlite:///{tmp_path / nome}"
    engine = create_engine(url)
    md = MetaData()
    Table("mae", md, Column("id", String(36), primary_key=True))
    Table(
        "filha",
        md,
        Column("id", String(36), primary_key=True),
        Column("mae_id", String(36), ForeignKey("mae.id")),
        Column("rotulo", String(5), nullable=False),
        Column("ativo", Boolean()),
    )
    md.create_all(engine)
    return url, engine, md


def test_banco_limpo_nao_reporta_nada(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
        conn.execute(
            insert(md.tables["filha"]),
            [{"id": "f1", "mae_id": "m1", "rotulo": "ok", "ativo": 1}],
        )
    assert verificar(origem_url, destino_url, schema=None) == []


def test_acha_orfao_de_fk(tmp_path):
    """O SQLite nao verifica FK por default: a linha existe hoje."""
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(
            insert(md.tables["filha"]),
            [{"id": "f1", "mae_id": "sumida", "rotulo": "ok", "ativo": 1}],
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.mae_id" in p and "orfa" in p for p in problemas)


def test_acha_string_maior_que_a_coluna(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
        conn.execute(
            insert(md.tables["filha"]),
            [{"id": "f1", "mae_id": "m1", "rotulo": "cabe-nao", "ativo": 1}],
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.rotulo" in p and "5" in p for p in problemas)


def test_acha_null_em_not_null(tmp_path):
    """A origem nao pode ter a NOT NULL declarada, senao o INSERT sujo nem
    entra no SQLite (que, ao contrario de FK, sempre valida NOT NULL). So o
    destino tem a restricao de verdade — como em producao, onde a coluna as
    vezes foi adicionada depois sem NOT NULL no SQLite de origem."""
    origem_url = f"sqlite:///{tmp_path / 'origem.db'}"
    origem_engine = create_engine(origem_url)
    md_origem = MetaData()
    Table("mae", md_origem, Column("id", String(36), primary_key=True))
    Table(
        "filha",
        md_origem,
        Column("id", String(36), primary_key=True),
        Column("mae_id", String(36), ForeignKey("mae.id")),
        Column("rotulo", String(5)),
        Column("ativo", Boolean()),
    )
    md_origem.create_all(origem_engine)
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with origem_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO filha (id, mae_id, rotulo, ativo) VALUES ('f1', NULL, NULL, 1)"
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.rotulo" in p and "NULL" in p for p in problemas)


def test_acha_booleano_fora_de_zero_e_um(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
        conn.exec_driver_sql(
            "INSERT INTO filha (id, mae_id, rotulo, ativo) "
            "VALUES ('f1', 'm1', 'ok', 2)"
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.ativo" in p for p in problemas)


def test_acha_tabela_que_falta_no_destino(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, destino_engine, _ = _monta(tmp_path, "destino.db")
    md_extra = MetaData()
    Table("sobrando", md_extra, Column("id", String(36), primary_key=True))
    md_extra.create_all(engine)
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("sobrando" in p for p in problemas)
