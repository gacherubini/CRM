from decimal import Decimal

import pytest

from app.motor.amortizacao import calcula_parcela_price


def test_parcela_taxa_zero():
    assert calcula_parcela_price(1200, 0, 12) == Decimal("100.00")


def test_parcela_price_conhecida():
    # PV=1000, i=1% a.m., n=12 -> ~88.85
    assert calcula_parcela_price(1000, Decimal("0.01"), 12) == Decimal("88.85")


def test_parcela_n_invalido():
    with pytest.raises(ValueError):
        calcula_parcela_price(1000, Decimal("0.01"), 0)
