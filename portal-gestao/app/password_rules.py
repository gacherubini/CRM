from __future__ import annotations

SENHA_MINIMA = 12
SENHA_MAXIMA = 256


class SenhaInvalida(ValueError):
    pass


def validar_nova_senha(senha: str | None, confirmacao: str | None) -> str:
    senha = senha or ""
    if len(senha) < SENHA_MINIMA:
        raise SenhaInvalida(f"A senha deve ter pelo menos {SENHA_MINIMA} caracteres.")
    if len(senha) > SENHA_MAXIMA:
        raise SenhaInvalida(f"A senha deve ter no máximo {SENHA_MAXIMA} caracteres.")
    if senha != (confirmacao or ""):
        raise SenhaInvalida("A confirmação da senha não confere.")
    return senha
