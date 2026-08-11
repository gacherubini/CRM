from datetime import date

from app.loja.copiloto.periodo import Janela, janela_anterior, janela_do_periodo


def test_janela_do_periodo_aceita_iso_e_date():
    j = janela_do_periodo("2026-08-01", "2026-08-31")
    assert j == Janela(inicio=date(2026, 8, 1), fim=date(2026, 8, 31))
    assert janela_do_periodo(date(2026, 8, 1), date(2026, 8, 31)) == j


def test_janela_conta_dias_inclusivos():
    assert janela_do_periodo("2026-08-01", "2026-08-31").dias == 31
    assert janela_do_periodo("2026-08-11", "2026-08-11").dias == 1


def test_mes_cheio_compara_com_o_mes_anterior_cheio():
    """Agosto inteiro compara com julho inteiro — não com 31 dias corridos."""
    anterior = janela_anterior(janela_do_periodo("2026-08-01", "2026-08-31"))
    assert anterior == Janela(inicio=date(2026, 7, 1), fim=date(2026, 7, 31))


def test_mes_cheio_de_marco_compara_com_fevereiro_curto():
    anterior = janela_anterior(janela_do_periodo("2026-03-01", "2026-03-31"))
    assert anterior == Janela(inicio=date(2026, 2, 1), fim=date(2026, 2, 28))


def test_janela_parcial_recua_o_mesmo_numero_de_dias():
    """Do dia 1 ao 11 compara com os 11 dias imediatamente anteriores."""
    anterior = janela_anterior(janela_do_periodo("2026-08-01", "2026-08-11"))
    assert anterior == Janela(inicio=date(2026, 7, 21), fim=date(2026, 7, 31))


def test_rotulo_do_mes_cheio_e_legivel():
    assert janela_do_periodo("2026-08-01", "2026-08-31").rotulo == "agosto/2026"


def test_rotulo_de_janela_parcial_mostra_as_datas():
    assert (
        janela_do_periodo("2026-08-01", "2026-08-11").rotulo
        == "01/08/2026 a 11/08/2026"
    )
