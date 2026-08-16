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


def test_acha_centavo_que_o_arredondamento_da_carga_comeu(tmp_path):
    """O falso "Corte liberado".

    A origem tem `10.00567` numa `NUMERIC(12,2)`; a carga gravou `10.01`. Com
    `select(func.sum(...))` tipado dos dois lados, a leitura da validacao
    aplicava o MESMO arredondamento na origem — 10.01 contra 10.01, lista
    vazia, exit 0, centavos perdidos.
    """
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO vendas (id, valor, criado_em) "
            "VALUES ('v1', 10.00567, '2026-08-16 10:00:00.000000')"
        )
    with destino.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO vendas (id, valor, criado_em) "
            "VALUES ('v1', 10.01, '2026-08-16 10:00:00.000000')"
        )
    divergencias = validar(origem_url, destino_url, schema=None)
    assert any(
        "vendas.valor" in d and "10.00567" in d for d in divergencias
    ), divergencias


def test_destino_sem_tabela_nenhuma_nao_libera_o_corte(tmp_path):
    """`--schema` errado ou `alembic upgrade head` que nao rodou: o reflect
    devolve zero tabela SEM erro. Antes, isso virava lista vazia e exit 0 —
    o portao liberava o corte tendo comparado exatamente nada."""
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 10.0, "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    vazio_url = f"sqlite:///{tmp_path / 'vazio.db'}"
    create_engine(vazio_url).connect().close()  # cria o arquivo, sem tabela

    divergencias = validar(origem_url, vazio_url, schema=None)
    assert divergencias, "destino sem tabela nao pode devolver lista vazia"
    assert any("nao tem tabela nenhuma" in d for d in divergencias), divergencias


def test_acha_tabela_que_so_existe_na_origem(tmp_path):
    """O laco itera o DESTINO: uma tabela que exista no `.db` e nao na cadeia
    de migrations nunca era visitada e sumia em silencio."""
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    md_extra = MetaData()
    Table(
        "esquecida",
        md_extra,
        Column("id", String(36), primary_key=True),
    )
    md_extra.create_all(origem)
    with origem.begin() as conn:
        conn.execute(insert(md_extra.tables["esquecida"]), [{"id": "e1"}])

    divergencias = validar(origem_url, destino_url, schema=None)
    assert any(
        "esquecida" in d and "existe na origem e nao no destino" in d
        for d in divergencias
    ), divergencias


def test_acha_coluna_que_so_existe_na_origem(tmp_path):
    """Irmao do caso acima, um nivel abaixo: `copiar.py` filtra as colunas pelo
    destino e descarta a coluna so-na-origem sem uma linha de log."""
    origem_url = f"sqlite:///{tmp_path / 'origem.db'}"
    origem = create_engine(origem_url)
    md_origem = MetaData()
    Table(
        "vendas",
        md_origem,
        Column("id", String(36), primary_key=True),
        Column("valor", Numeric(12, 2)),
        Column("criado_em", DateTime(timezone=True)),
        Column("comissao", Numeric(12, 2)),
    )
    md_origem.create_all(origem)
    destino_url, _, _ = _banco(tmp_path, "destino.db")

    divergencias = validar(origem_url, destino_url, schema=None)
    assert any(
        "vendas.comissao" in d and "existe na origem e nao no destino" in d
        for d in divergencias
    ), divergencias
