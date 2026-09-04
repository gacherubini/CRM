"""Catálogo canônico dos provedores reais do Motor.

O nome canônico (minúsculo) é usado em solicitações e credenciais. Rótulos de
apresentação nunca participam do roteamento, evitando colisão com os bancos mock.
"""
from __future__ import annotations

from typing import Any


PROVEDORES_REAIS: dict[str, dict[str, Any]] = {
    "santander": {
        "nome": "santander",
        "rotulo": "Santander",
        "habilitado": True,
        "real": True,
        "modo": "playwright",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "CPF/usuário do portal", "secreto": False},
            {"nome": "senha", "rotulo": "Senha do portal", "secreto": True},
        ],
    },
    "fontecred": {
        "nome": "fontecred",
        "rotulo": "Fontecred",
        "habilitado": True,
        "real": True,
        "modo": "playwright",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "E-mail do portal", "secreto": False},
            {"nome": "senha", "rotulo": "Senha do portal", "secreto": True},
        ],
    },
    "bradesco": {
        "nome": "bradesco",
        "rotulo": "Bradesco",
        "habilitado": True,
        "real": True,
        "modo": "playwright",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "CPF do lojista", "secreto": False},
            {"nome": "senha", "rotulo": "Senha do portal", "secreto": True},
        ],
    },
    "pan": {
        "nome": "pan",
        "rotulo": "Banco PAN",
        "habilitado": True,
        "real": True,
        # Operação atual: portal go!PAN via Playwright (mesmo slot 2GB sob demanda).
        # O dispatcher ainda aceita config OpenAPI se existir no blob cifrado, mas
        # a UI de Acessos só pede usuário/senha do portal.
        "modo": "playwright",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "Usuário/CPF do portal go!PAN", "secreto": False},
            {"nome": "senha", "rotulo": "Senha do portal", "secreto": True},
        ],
    },
    "motrix": {
        "nome": "motrix",
        "rotulo": "Motrix",
        "habilitado": True,
        "real": True,
        # Plataforma joinbank. Tem API REST por trás do SPA, mas as chamadas exigem
        # um header assinado pelo JS da página — ver o docstring de app/motor/motrix.py.
        "modo": "playwright",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "Usuário/CPF do portal Motrix", "secreto": False},
            {"nome": "senha", "rotulo": "Senha do portal", "secreto": True},
        ],
    },
}


def normalizar_provedor(nome: str) -> str:
    return (nome or "").strip().lower()


def obter_provedor(nome: str) -> dict[str, Any] | None:
    return PROVEDORES_REAIS.get(normalizar_provedor(nome))


def nomes_provedores_reais() -> list[str]:
    return list(PROVEDORES_REAIS)


def listar_provedores() -> list[dict[str, Any]]:
    return [dict(meta) for meta in PROVEDORES_REAIS.values()]


def campos_credencial_obrigatorios(nome: str) -> set[str]:
    meta = obter_provedor(nome) or {}
    return {
        campo["nome"]
        for campo in meta.get("campos_credencial", [])
        if campo.get("obrigatorio", True)
    }
