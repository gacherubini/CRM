from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx


_METODOS_IDEMPOTENTES = frozenset({"GET", "HEAD", "OPTIONS"})
_STATUS_TRANSITORIOS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _tem_chave_idempotencia(headers: object) -> bool:
    if not isinstance(headers, Mapping):
        return False
    return any(
        str(nome).lower() == "idempotency-key" and bool(valor)
        for nome, valor in headers.items()
    )


def requisicao_com_retry(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    retries: int,
    backoff: float,
    sleeper: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """Executa retries apenas quando repetir a operação é seguro.

    GET/HEAD/OPTIONS são idempotentes por contrato HTTP. Qualquer outro método só
    pode ser repetido se o chamador enviar explicitamente ``Idempotency-Key``.
    O helper não registra request, URL, headers ou payload para evitar vazamento de
    credenciais e dados pessoais.
    """

    retries = max(0, int(retries))
    backoff = max(0.0, float(backoff))
    metodo = method.upper()
    pode_repetir = metodo in _METODOS_IDEMPOTENTES or _tem_chave_idempotencia(
        kwargs.get("headers")
    )

    for tentativa in range(retries + 1):
        try:
            resposta = client.request(metodo, path, **kwargs)
        except httpx.RequestError:
            if not pode_repetir or tentativa >= retries:
                raise
        else:
            if (
                not pode_repetir
                or resposta.status_code not in _STATUS_TRANSITORIOS
                or tentativa >= retries
            ):
                return resposta
            resposta.close()

        sleeper(backoff * (2**tentativa))

    raise RuntimeError("estado de retry inválido")  # pragma: no cover
