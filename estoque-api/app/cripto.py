"""Cifra simétrica para segredos em repouso (ex.: segredo HMAC do webhook da outbox).

A chave vem de ``ESTOQUE_OUTBOX_KEY`` (uma chave Fernet urlsafe base64). Gere com
``python -m app.cli gerar-chave-outbox`` e guarde fora do versionamento.
"""
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    chave = os.getenv("ESTOQUE_OUTBOX_KEY")
    if not chave:
        raise RuntimeError(
            "ESTOQUE_OUTBOX_KEY não configurada: gere com `python -m app.cli gerar-chave-outbox`"
        )
    return Fernet(chave.encode())


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def gerar_chave() -> str:
    return Fernet.generate_key().decode()
