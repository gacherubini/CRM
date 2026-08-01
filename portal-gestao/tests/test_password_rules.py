import pytest

from app.password_rules import SENHA_MINIMA, SenhaInvalida, validar_nova_senha


def test_valida_senha_ok():
    assert validar_nova_senha("senha-super-segura", "senha-super-segura") == "senha-super-segura"


def test_senha_curta_rejeitada():
    curta = "a" * (SENHA_MINIMA - 1)
    with pytest.raises(SenhaInvalida):
        validar_nova_senha(curta, curta)


def test_confirmacao_diferente_rejeitada():
    with pytest.raises(SenhaInvalida):
        validar_nova_senha("senha-super-segura", "outra-coisa-diferente")


def test_senha_none_rejeitada():
    with pytest.raises(SenhaInvalida):
        validar_nova_senha(None, None)


def test_senha_no_limite_maximo_ok():
    from app.password_rules import SENHA_MAXIMA
    senha = "a" * SENHA_MAXIMA
    assert validar_nova_senha(senha, senha) == senha


def test_senha_acima_do_maximo_rejeitada():
    from app.password_rules import SENHA_MAXIMA
    senha = "a" * (SENHA_MAXIMA + 1)
    with pytest.raises(SenhaInvalida):
        validar_nova_senha(senha, senha)
