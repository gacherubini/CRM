"""Probe da Graph API (Meta) — valida token de forma injetável/mockável.

`GraphProbe` é o contrato usado por `integrations_health.check_meta`.
`HttpGraphProbe` é a implementação real (httpx); testes usam um fake local
(`FakeGraphProbe`, definido nos próprios testes) para nunca bater na rede.

Nunca loga nem retorna o token — apenas (ok, motivo) para exibição segura.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class GraphProbe(Protocol):
    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        """Retorna (True, None) se o token é válido; (False, motivo) senão."""
        ...


class HttpGraphProbe:
    """Probe real via Graph API.

    Se ``pixel_id`` for informado, valida o token consultando o próprio
    objeto do Pixel (``GET /{pixel_id}``); caso contrário (uso genérico, ex.
    Meta Ads), valida via ``GET /me``. Em ambos os casos o único uso do
    token é como parâmetro da chamada HTTP — nunca é logado ou incluído no
    motivo de erro devolvido.
    """

    def __init__(
        self,
        timeout: float | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout = (
            timeout if timeout is not None else settings.integracoes_health_timeout_seg
        )
        # Injetável apenas para testes (httpx.MockTransport) — nunca bate na
        # rede real quando informado. Default None preserva o comportamento
        # atual (transporte HTTP real do httpx).
        self._transport = transport

    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        token = (token or "").strip()
        if not token:
            return False, "token ausente"

        alvo = (pixel_id or "").strip() or "me"
        url = f"{GRAPH_BASE}/{alvo}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(url, params={"access_token": token, "fields": "id"})
        except httpx.RequestError:
            logger.warning("graph_probe.request_error alvo=%s", alvo)
            return False, "Falha de rede ao contatar a Graph API."

        if 200 <= response.status_code < 300:
            return True, None
        return False, _motivo_erro(response)


def _motivo_erro(response: httpx.Response) -> str:
    motivo: str | None = None
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        erro = data.get("error")
        if isinstance(erro, dict):
            mensagem = erro.get("message")
            if isinstance(mensagem, str) and mensagem.strip():
                motivo = mensagem.strip()
    if motivo:
        return motivo[:200]
    return f"Graph API respondeu HTTP {response.status_code}."
