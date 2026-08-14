"""Entrada do webhook da Cloud API (spec §6.1)."""
from __future__ import annotations

import hashlib
import hmac

_PREFIXO = "sha256="


def assinatura_valida(corpo_cru: bytes, header: str, *, app_secret: str) -> bool:
    """Confere ``X-Hub-Signature-256`` sobre o corpo **cru**.

    Recebe ``bytes`` de propósito: calcular o HMAC sobre o JSON re-serializado
    é o erro clássico dessa integração — ordem de chave e escape de unicode
    mudam os bytes e a assinatura nunca bate. O tipo impede o erro.

    Fail-closed: sem ``app_secret`` configurado, nada passa.
    """
    if not app_secret or not header.startswith(_PREFIXO):
        return False
    recebida = header[len(_PREFIXO):].strip()
    esperada = hmac.new(app_secret.encode("utf-8"), corpo_cru, hashlib.sha256).hexdigest()
    return hmac.compare_digest(recebida, esperada)
