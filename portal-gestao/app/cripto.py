"""Cifra simétrica para segredos em repouso (token CAPI Meta — E10).

Chave: ``PORTAL_ENCRYPTION_KEY`` (Fernet urlsafe base64).
Gere com ``python -m app.cli gerar-chave-cifragem`` e guarde fora do git.

Em produção (``PORTAL_ENV=production``) a chave é obrigatória; em dev há fallback
determinístico marcado como inseguro (somente testes/local).
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet

_DEV_SEED = b"portal-dev-key-NAO-USAR-EM-PRODUCAO"


def _chave() -> bytes:
    valor = os.getenv("PORTAL_ENCRYPTION_KEY")
    if valor:
        return valor.encode() if isinstance(valor, str) else valor
    if os.getenv("PORTAL_ENV") == "production":
        raise RuntimeError("PORTAL_ENCRYPTION_KEY é obrigatória em produção")
    return base64.urlsafe_b64encode(hashlib.sha256(_DEV_SEED).digest())


def cifrar(texto: str) -> str:
    return Fernet(_chave()).encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    return Fernet(_chave()).decrypt(token.encode()).decode()


def gerar_chave() -> str:
    return Fernet.generate_key().decode()
