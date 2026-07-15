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
        # Dual-path: API OpenAPI (todos os campos) OU portal do lojista (só
        # usuario+senha). Só usuario/senha são obrigatórios para o provedor
        # "estar completo"; os demais são exclusivos do caminho API e o próprio
        # PanDriver valida a completude deles (pan_configuracao_incompleta).
        "modo": "api",
        "campos_credencial": [
            {"nome": "usuario", "rotulo": "Usuário/CPF do lojista", "secreto": False},
            {"nome": "senha", "rotulo": "Senha do portal/NPV", "secreto": True},
            {"nome": "api_key", "rotulo": "API Key", "secreto": True, "obrigatorio": False},
            {"nome": "secret_key", "rotulo": "Secret Key", "secreto": True, "obrigatorio": False},
            {"nome": "id_loja", "rotulo": "ID da loja", "secreto": False, "obrigatorio": False},
            {"nome": "tipo_id_loja", "rotulo": "Tipo do ID da loja", "secreto": False, "obrigatorio": False},
            {"nome": "codigo_produto", "rotulo": "Código do produto", "secreto": False, "obrigatorio": False},
            {"nome": "tipo_calculo", "rotulo": "Tipo de cálculo", "secreto": False, "obrigatorio": False},
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
