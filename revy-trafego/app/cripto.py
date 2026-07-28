"""Cifra simétrica para tokens CAPI/Ads (compatível com PORTAL_ENCRYPTION_KEY)."""
import base64
import hashlib
import os

from cryptography.fernet import Fernet

_DEV_SEED = b"portal-dev-key-NAO-USAR-EM-PRODUCAO"


def _chave() -> bytes:
    valor = (
        os.getenv("REVY_TRAFEGO_ENCRYPTION_KEY")
        or os.getenv("PORTAL_ENCRYPTION_KEY")
    )
    if valor:
        return valor.encode() if isinstance(valor, str) else valor
    if os.getenv("PORTAL_ENV") == "production" or os.getenv("REVY_TRAFEGO_ENV") == "production":
        raise RuntimeError(
            "REVY_TRAFEGO_ENCRYPTION_KEY ou PORTAL_ENCRYPTION_KEY é obrigatória em produção"
        )
    return base64.urlsafe_b64encode(hashlib.sha256(_DEV_SEED).digest())


def cifrar(texto: str) -> str:
    return Fernet(_chave()).encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    return Fernet(_chave()).decrypt(token.encode()).decode()


def gerar_chave() -> str:
    return Fernet.generate_key().decode()
