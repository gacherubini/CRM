"""InventoryProvider — consulta o Estoque Lite pela API pública (Plano #2A Task 2A).

O chatbot só responde com veículos reais. Se o estoque estiver indisponível/vazio,
o provider devolve lista vazia e o chamador oferece fallback/handoff (nunca inventa).
"""
import os
from typing import Protocol

import httpx


class InventoryProvider(Protocol):
    def buscar(self, slug: str, termo: str | None = None) -> list[dict]: ...


class HttpInventoryProvider:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or os.getenv("ESTOQUE_PUBLIC_URL", "")).rstrip("/")
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


def get_inventory_provider() -> InventoryProvider:
    return HttpInventoryProvider()
