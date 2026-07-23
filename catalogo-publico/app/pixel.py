"""Resolve Meta Pixel ID por loja a partir do Portal (fonte da verdade).

O dono configura o Pixel uma vez em Portal → Tráfego. O catálogo consulta
``GET {PORTAL_PUBLIC_URL}/public/v1/lojas/{slug}/pixel`` e usa o ``pixel_id``
público no browser. Token CAPI **nunca** passa por aqui.

Fallback: ``META_PIXEL_ID`` (env) se o Portal estiver offline ou não configurado.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class PixelResolver:
    """Cache curto + pull do Portal; fallback de env por loja."""

    def __init__(
        self,
        portal_url: str = "",
        *,
        timeout: float = 2.0,
        cache_ttl: float = 60.0,
        fallback_pixel_id: str = "",
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.portal_url = (portal_url or "").rstrip("/")
        self.timeout = timeout
        self.cache_ttl = max(1.0, float(cache_ttl))
        self.fallback_pixel_id = (fallback_pixel_id or "").strip()
        self.transport = transport
        self._cache: dict[str, tuple[float, Optional[str]]] = {}
        self._lock = threading.Lock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def resolve(self, loja_slug: str) -> str:
        """Retorna Pixel ID para a loja (string vazia = sem pixel)."""
        slug = (loja_slug or "").strip()
        if not slug:
            return self.fallback_pixel_id

        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(slug)
            if hit is not None and hit[0] > now:
                cached = hit[1]
                if cached is not None:
                    return cached
                return self.fallback_pixel_id

        from_portal = self._fetch(slug)
        with self._lock:
            # None = falha/sem URL → reconsultar cedo; str = resposta do Portal.
            ttl = self.cache_ttl if from_portal is not None else min(10.0, self.cache_ttl)
            self._cache[slug] = (now + ttl, from_portal)

        if from_portal is not None:
            return from_portal
        return self.fallback_pixel_id

    def _fetch(self, slug: str) -> Optional[str]:
        if not self.portal_url:
            return None
        url = f"{self.portal_url}/public/v1/lojas/{slug}/pixel"
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.get(url, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            logger.warning("pixel_portal_indisponivel slug=%s err=%s", slug, type(exc).__name__)
            return None

        if response.status_code != 200:
            logger.warning(
                "pixel_portal_http slug=%s status=%s", slug, response.status_code
            )
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        return str(payload.get("pixel_id") or "").strip()
