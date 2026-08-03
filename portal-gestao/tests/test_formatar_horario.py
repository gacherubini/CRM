"""Horários da UI em America/Sao_Paulo (não UTC cru)."""
from app.main import formatar_horario


def test_formatar_horario_converte_utc_para_brasilia():
    # 20:56 UTC = 17:56 em Brasília (UTC-3, sem horário de verão desde 2019)
    assert formatar_horario("2026-08-03T20:56:25.364790+00:00") == "03/08 17:56"


def test_formatar_horario_aceita_z_suffix():
    assert formatar_horario("2026-08-03T20:56:25Z") == "03/08 17:56"


def test_formatar_horario_naive_trata_como_utc():
    assert formatar_horario("2026-08-03T20:56:25") == "03/08 17:56"


def test_formatar_horario_vazio():
    assert formatar_horario(None) == ""
    assert formatar_horario("") == ""


def test_formatar_horario_invalido_devolve_entrada():
    assert formatar_horario("nao-e-data") == "nao-e-data"
