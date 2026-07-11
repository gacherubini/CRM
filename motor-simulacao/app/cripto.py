"""Cifra de dados pessoais em repouso + índice cego (Plano #1A Task 7 / Plano #0).

- `cifrar`/`decifrar`: Fernet (AES) com chave em `MOTOR_ENCRYPTION_KEY`.
- `indice_cego`: HMAC-SHA256 do CPF normalizado, para igualdade/dedup sem expor o valor.

Em produção (`MOTOR_ENV=production`) a chave é obrigatória; em dev há um fallback
determinístico claramente marcado como inseguro.
"""
import base64
import hashlib
import hmac
import os
import re

from cryptography.fernet import Fernet

_DEV_SEED = b"motor-dev-key-NAO-USAR-EM-PRODUCAO"


def _chave() -> bytes:
    valor = os.getenv("MOTOR_ENCRYPTION_KEY")
    if valor:
        return valor.encode()
    if os.getenv("MOTOR_ENV") == "production":
        raise RuntimeError("MOTOR_ENCRYPTION_KEY é obrigatória em produção")
    return base64.urlsafe_b64encode(hashlib.sha256(_DEV_SEED).digest())


def cifrar(texto: str) -> str:
    return Fernet(_chave()).encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    return Fernet(_chave()).decrypt(token.encode()).decode()


def indice_cego(cpf: str) -> str:
    normalizado = re.sub(r"\D", "", cpf or "")
    chave_hmac = hashlib.sha256(_chave() + b":indice-cego").digest()
    return hmac.new(chave_hmac, normalizado.encode(), hashlib.sha256).hexdigest()
