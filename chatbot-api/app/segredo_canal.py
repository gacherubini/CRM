"""Cifra em repouso dos segredos que pertencem a cada loja (spec §8).

Token de negócio e PIN de duas etapas chegam pelo embedded signup e são da
loja, não do Revy — o que é do Revy (App Secret, verify token) continua em
variável de ambiente e nunca encosta aqui.

Fail-closed: sem ``CHATBOT_CANAL_SECRET_KEY`` a operação levanta em vez de
guardar em claro. Secret esquecido vira erro visível, não vazamento calado.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app import config


class SegredoIndisponivel(RuntimeError):
    """Chave de cifra ausente ou inválida."""


def _fernet() -> Fernet:
    chave = (config.CANAL_SECRET_KEY or "").strip()
    if not chave:
        raise SegredoIndisponivel("CHATBOT_CANAL_SECRET_KEY não configurada")
    try:
        return Fernet(chave.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SegredoIndisponivel("CHATBOT_CANAL_SECRET_KEY inválida") from exc


def cifrar(valor: str) -> str:
    return _fernet().encrypt(valor.encode("utf-8")).decode("utf-8")


def decifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SegredoIndisponivel("valor cifrado não abre com esta chave") from exc
