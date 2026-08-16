from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String

from tipos import ValorInconvertivel, converter


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
