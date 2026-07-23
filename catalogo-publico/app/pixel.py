"""Resolve Meta Pixel ID por loja a partir do Portal (fonte da verdade).

O dono configura o Pixel uma vez em Portal → Tráfego. O catálogo consulta
``GET {PORTAL_PUBLIC_URL}/public/v1/lojas/{slug}/pixel`` e usa o ``pixel_id``
público no browser. Token CAPI **nunca** passa por aqui.

Fallback: ``META_PIXEL_ID`` (env) se o Portal estiver offline ou não configurado.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)
_PIXEL_ID_RE = re.compile(r"^[0-9]{5,32}$")


def _pixel_id_publico(valor: object) -> str:
    pixel_id = str(valor or "").strip()
    return pixel_id if _PIXEL_ID_RE.fullmatch(pixel_id) else ""


@dataclass(frozen=True)
class PixelConfig:
    pixel_id: str = ""
    enabled: bool = False
    enviar_page_view: bool = True
    enviar_lead: bool = True


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
        self.fallback_pixel_id = _pixel_id_publico(fallback_pixel_id)
        self.transport = transport
        self._cache: dict[str, tuple[float, Optional[PixelConfig]]] = {}
        self._lock = threading.Lock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def resolve(self, loja_slug: str) -> str:
        """Compatibilidade: retorna somente o Pixel ID da loja."""
        return self.resolve_config(loja_slug).pixel_id

    def resolve_config(self, loja_slug: str) -> PixelConfig:
        """Retorna Pixel ID e os eventos browser habilitados no Portal."""
        slug = (loja_slug or "").strip()
        if not slug:
            return self._fallback()

        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(slug)
            if hit is not None and hit[0] > now:
                cached = hit[1]
                if cached is not None:
                    return cached
                return self._fallback()

        from_portal = self._fetch(slug)
        with self._lock:
            # None = falha/sem URL → reconsultar cedo; str = resposta do Portal.
            ttl = self.cache_ttl if from_portal is not None else min(10.0, self.cache_ttl)
            self._cache[slug] = (now + ttl, from_portal)

        if from_portal is not None:
            return from_portal
        return self._fallback()

    def _fallback(self) -> PixelConfig:
        return PixelConfig(
            pixel_id=self.fallback_pixel_id,
            enabled=bool(self.fallback_pixel_id),
        )

    def _fetch(self, slug: str) -> Optional[PixelConfig]:
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
        pixel_id = _pixel_id_publico(payload.get("pixel_id"))
        return PixelConfig(
            pixel_id=pixel_id,
            enabled=bool(payload.get("enabled", bool(pixel_id))) and bool(pixel_id),
            enviar_page_view=bool(payload.get("enviar_page_view", True)),
            enviar_lead=bool(payload.get("enviar_lead", True)),
        )
