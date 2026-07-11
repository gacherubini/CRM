from datetime import date

from app.validadores import idade, parse_nascimento, parse_valor, valida_cpf


def test_valida_cpf_valido():
    assert valida_cpf("529.982.247-25") is True


def test_valida_cpf_invalido_digito():
    assert valida_cpf("529.982.247-24") is False


def test_valida_cpf_sequencia_repetida():
    assert valida_cpf("111.111.111-11") is False


def test_valida_cpf_tamanho_errado():
    assert valida_cpf("123") is False


def test_valida_cpf_none():
    assert valida_cpf(None) is False


def test_parse_nascimento_formatos():
    assert parse_nascimento("20/05/1990") == date(1990, 5, 20)
    assert parse_nascimento("1990-05-20") == date(1990, 5, 20)


def test_parse_nascimento_invalido():
    assert parse_nascimento("banana") is None


def test_idade_antes_do_aniversario():
    assert idade(date(2000, 6, 1), hoje=date(2026, 1, 1)) == 25


def test_idade_depois_do_aniversario():
    assert idade(date(2000, 1, 1), hoje=date(2026, 6, 1)) == 26


def test_parse_valor_variacoes():
    assert parse_valor("20 mil") == 20000
    assert parse_valor("R$ 20.000") == 20000
    assert parse_valor("20000") == 20000
    assert parse_valor("20.000,50") == 20000.50


def test_parse_valor_invalido():
    assert parse_valor("abc") is None
