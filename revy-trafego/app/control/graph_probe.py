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
from app.meta_graph_config import GRAPH_BASE

logger = logging.getLogger(__name__)

class GraphProbe(Protocol):
    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        """Retorna (True, None) se o token é válido; (False, motivo) senão."""
        ...


class HttpGraphProbe:
    """Probe real via Graph API.

    Validação:

    * Sem ``pixel_id`` (ex. Meta Ads): ``GET /me``.
    * Com ``pixel_id``: tenta ``GET /{pixel_id}`` (token Marketing com leitura
      do Pixel). Se a Graph devolver erro de **permissão** (``#100`` Missing
      Permission), faz fallback em ``GET /me``: tokens do Events Manager
      (Conversions API) autenticam e enviam eventos, mas **não** leem o
      objeto Pixel — o health antigo marcava falso negativo.

    O token só viaja como query param; nunca é logado nem incluído no motivo.
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

        pixel = (pixel_id or "").strip()
        if not pixel:
            return self._get_ok(token, "me")

        ok, motivo = self._get_ok(token, pixel)
        if ok:
            return True, None
        if not _eh_erro_permissao(motivo):
            return False, motivo

        # Token CAPI típico: vivo, mas sem ads_read no objeto Pixel.
        ok_me, motivo_me = self._get_ok(token, "me")
        if ok_me:
            return True, None
        return False, motivo_me or motivo

    def _get_ok(self, token: str, alvo: str) -> tuple[bool, str | None]:
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


def _eh_erro_permissao(motivo: str | None) -> bool:
    """Detecta (#100) Missing Permission e variações da Graph."""
    if not motivo:
        return False
    texto = motivo.casefold()
    if "missing permission" in texto:
        return True
    if "(#100)" in texto and "permission" in texto:
        return True
    return False


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
