from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Integer, MetaData, Numeric, String, Table,
    create_engine, insert, select,
)

from tipos import ValorInconvertivel, converter, ler_cru


def test_ler_cru_devolve_o_que_esta_no_arquivo_e_nao_o_que_o_tipo_diz(tmp_path: Path):
    """Guarda do helper: se alguém trocar `ler_cru` por `select()` tipado, a
    ferramenta inteira volta a mentir. `10.00567` numa `Numeric(12,2)` vira
    `10.01` e `2` numa `Boolean` vira `True` — e é exatamente esse par de
    valores sujos que `verificar`/`copiar`/`validar` existem para pegar.
    """
    url = f"sqlite:///{tmp_path / 'cru.db'}"
    engine = create_engine(url)
    md = MetaData()
    linha = Table(
        "linha",
        md,
        Column("id", String(36), primary_key=True),
        Column("valor", Numeric(12, 2)),
        Column("ativo", Boolean()),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO linha (id, valor, ativo) VALUES ('l1', 10.00567, 2)"
        )

    with engine.connect() as conn:
        tipado = conn.execute(select(linha.c.valor, linha.c.ativo)).one()
        cru = list(ler_cru(conn, "linha", ["valor", "ativo"]))

    # O que a camada tipada mostra — arredondado e coagido:
    assert tipado[0] == Decimal("10.01")
    assert tipado[1] is True
    # O que está no arquivo:
    assert cru == [(10.00567, 2)]
    assert Decimal(str(cru[0][0])) == Decimal("10.00567")
    assert cru[0][1] == 2
    assert cru[0][1] is not True


def test_ler_cru_soma_sem_quantizar(tmp_path: Path):
    """`func.sum` tipado quantiza na leitura da validacao, exatamente como o
    Postgres quantizou na carga — por isso os dois lados batem e o portao
    libera o corte com centavo perdido."""
    from sqlalchemy import func

    url = f"sqlite:///{tmp_path / 'soma.db'}"
    engine = create_engine(url)
    md = MetaData()
    linha = Table(
        "linha",
        md,
        Column("id", String(36), primary_key=True),
        Column("valor", Numeric(12, 2)),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO linha (id, valor) VALUES ('l1', 10.00567)")

    with engine.connect() as conn:
        soma_tipada = conn.execute(select(func.sum(linha.c.valor))).scalar_one()
        soma_crua = sum(
            (Decimal(str(v)) for (v,) in ler_cru(conn, "linha", ["valor"])),
            Decimal("0"),
        )
    assert soma_tipada == Decimal("10.01")
    assert soma_crua == Decimal("10.00567")


def test_ler_cru_cita_os_identificadores(tmp_path: Path):
    """Nome de coluna que colide com palavra reservada nao pode quebrar o SQL."""
    url = f"sqlite:///{tmp_path / 'reservado.db'}"
    engine = create_engine(url)
    md = MetaData()
    Table(
        "order",
        md,
        Column("id", String(36), primary_key=True),
        Column("select", String(10)),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(md.tables["order"]), [{"id": "o1", "select": "x"}])
    with engine.connect() as conn:
        assert list(ler_cru(conn, "order", ["id", "select"])) == [("o1", "x")]


def test_none_atravessa_qualquer_tipo():
    assert converter(None, Numeric(12, 2)) is None
    assert converter(None, DateTime(timezone=True)) is None


def test_datetime_naive_ganha_utc():
    naive = datetime(2026, 8, 16, 10, 0, 0)
    convertido = converter(naive, DateTime(timezone=True))
    assert convertido.tzinfo is timezone.utc
    assert convertido.hour == 10  # NAO desloca: o valor guardado ja era UTC


def test_datetime_aware_nao_e_tocado():
    aware = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert converter(aware, DateTime(timezone=True)) == aware


def test_datetime_em_texto_e_lido_como_iso():
    convertido = converter("2026-08-16 10:00:00.000000", DateTime(timezone=True))
    assert convertido == datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)


def test_date_atravessa():
    assert converter(date(2026, 8, 16), Date()) == date(2026, 8, 16)


def test_numeric_de_float_passa_por_str():
    """Decimal(0.1) e 0.1000000000000000055511151231257827...; Decimal(str(0.1)) e 0.1."""
    assert converter(0.1, Numeric(12, 6)) == Decimal("0.1")
    assert converter(118900.0, Numeric(12, 2)) == Decimal("118900.0")


def test_numeric_de_decimal_e_preservado():
    assert converter(Decimal("1234.56"), Numeric(12, 2)) == Decimal("1234.56")


def test_numeric_de_texto_e_preservado():
    assert converter("1234.56", Numeric(12, 2)) == Decimal("1234.56")


def test_boolean_aceita_zero_e_um():
    assert converter(0, Boolean()) is False
    assert converter(1, Boolean()) is True
    assert converter(True, Boolean()) is True


def test_boolean_recusa_valor_fora_de_zero_e_um():
    """SQLite aceita 2 numa coluna booleana. O Postgres nao — e coercao
    silenciosa aqui esconderia um dado ja corrompido."""
    with pytest.raises(ValorInconvertivel):
        converter(2, Boolean())


def test_string_e_integer_atravessam():
    assert converter("abc", String(10)) == "abc"
    assert converter(7, Integer()) == 7
