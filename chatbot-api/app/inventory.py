"""InventoryProvider — consulta o Estoque Lite (Plano #2A Task 2A + por-placa).

- buscar: API pública (ESTOQUE_PUBLIC_URL)
- obter_por_placa: API privada (ESTOQUE_API_URL + ESTOQUE_API_TOKEN)

O chatbot só responde com veículos reais. Se o estoque estiver indisponível/vazio,
o provider devolve lista vazia / None e o chamador oferece fallback/handoff (nunca inventa).
"""
from typing import Protocol

import httpx

from app import config


class InventoryProvider(Protocol):
    def buscar(self, slug: str, termo: str | None = None) -> list[dict]: ...

    def obter_por_placa(self, placa: str) -> dict | None: ...


class HttpInventoryProvider:
    def __init__(
        self,
        base_url: str | None = None,
        api_url: str | None = None,
        api_token: str | None = None,
        timeout: float = 5.0,
    ):
        self.base_url = (base_url if base_url is not None else config.ESTOQUE_PUBLIC_URL).rstrip("/")
        self.api_url = (api_url if api_url is not None else config.ESTOQUE_API_URL).rstrip("/")
        self.api_token = config.ESTOQUE_API_TOKEN if api_token is None else api_token
        self.timeout = timeout

    def buscar(self, slug: str, termo: str | None = None) -> list[dict]:
        if not self.base_url:
            return []
        url = f"{self.base_url}/public/v1/lojas/{slug}/veiculos"
        try:
            r = httpx.get(url, timeout=self.timeout)
            r.raise_for_status()
            veiculos = r.json().get("veiculos", [])
        except Exception:
            return []
        if termo:
            t = termo.lower()
            veiculos = [
                v
                for v in veiculos
                if t in f"{v.get('marca', '')} {v.get('modelo', '')}".lower()
            ]
        return veiculos

    def obter_por_placa(self, placa: str) -> dict | None:
        """GET privado /v1/veiculos/por-placa/{placa}. 404/erros → None."""
        if not self.api_url or not self.api_token or not placa:
            return None
        placa_limpa = placa.strip()
        if not placa_limpa:
            return None
        url = f"{self.api_url}/v1/veiculos/por-placa/{placa_limpa}"
        try:
            r = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=self.timeout,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            return None


def get_inventory_provider() -> InventoryProvider:
    return HttpInventoryProvider()
