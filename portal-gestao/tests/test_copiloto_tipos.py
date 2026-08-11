from datetime import date

import pytest

from app.loja.copiloto.tipos import Cobertura, CopilotoContexto


def test_cobertura_completa_nao_e_parcial():
    c = Cobertura(com_dado=14, total=14)
    assert c.completa is True
    assert c.parcial is False
    assert c.to_dict() == {"com_dado": 14, "total": 14}


def test_cobertura_parcial_quando_falta_dado():
    c = Cobertura(com_dado=6, total=14)
    assert c.completa is False
    assert c.parcial is True


def test_cobertura_vazia_nao_e_parcial():
    """Zero de zero é vazio, não parcial — senão a tela grita à toa."""
    c = Cobertura(com_dado=0, total=0)
    assert c.parcial is False
    assert c.completa is True


def test_cobertura_recusa_com_dado_maior_que_total():
    with pytest.raises(ValueError):
        Cobertura(com_dado=3, total=2)


def test_contexto_normaliza_papel_e_email():
    ctx = CopilotoContexto(
        loja_slug="loja-teste",
        papel=" Dono ",
        ator_email="Dono@Loja.Test",
        hoje=date(2026, 8, 11),
    )
    assert ctx.papel == "dono"
    assert ctx.ator_email == "dono@loja.test"
    assert ctx.pode_ver_margem is True


def test_contexto_vendedor_nao_ve_margem():
    ctx = CopilotoContexto(
        loja_slug="loja-teste",
        papel="vendedor",
        ator_email="v@loja.test",
        hoje=date(2026, 8, 11),
    )
    assert ctx.pode_ver_margem is False
