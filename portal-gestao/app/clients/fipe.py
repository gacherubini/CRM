"""Client da tabela FIPE. Read-only, fonte externa (MCP-nativa)."""
from __future__ import annotations

from typing import Any

import httpx


class FipeIndisponivel(RuntimeError):
    """Fonte externa fora. Nunca vira valor aproximado."""


class FipeClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _get(self, caminho: str) -> Any:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                resposta = client.get(caminho)
            if resposta.status_code != 200:
                raise FipeIndisponivel(f"FIPE respondeu {resposta.status_code}")
            return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FipeIndisponivel("não foi possível consultar a FIPE") from exc

    def marcas(self, tipo: str) -> list[dict]:
        return self._get(f"/{tipo}/marcas")

    def modelos(self, tipo: str, marca_codigo: str) -> list[dict]:
        bruto = self._get(f"/{tipo}/marcas/{marca_codigo}/modelos")
        return bruto.get("modelos", []) if isinstance(bruto, dict) else bruto

    def anos(self, tipo: str, marca_codigo: str, modelo_codigo: str) -> list[dict]:
        return self._get(
            f"/{tipo}/marcas/{marca_codigo}/modelos/{modelo_codigo}/anos"
        )

    def valor(
        self, tipo: str, marca_codigo: str, modelo_codigo: str, ano_codigo: str
    ) -> dict:
        return self._get(
            f"/{tipo}/marcas/{marca_codigo}/modelos/{modelo_codigo}/anos/{ano_codigo}"
        )
