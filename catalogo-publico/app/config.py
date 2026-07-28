import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    version: str = os.getenv("CATALOGO_VERSION", "0.1.0")
    inventory_url: str = os.getenv(
        "ESTOQUE_PUBLIC_API_URL", "http://estoque-api:8000"
    ).rstrip("/")
    inventory_token: str = os.getenv("ESTOQUE_PUBLIC_API_TOKEN", "")
    provider_timeout: float = float(os.getenv("CATALOGO_PROVIDER_TIMEOUT", "5"))
    database_path: str = os.getenv("CATALOGO_DATABASE_PATH", "data/catalogo.db")
    page_size: int = max(1, min(48, int(os.getenv("CATALOGO_PAGE_SIZE", "12"))))
    public_base_url: str = os.getenv("CATALOGO_PUBLIC_BASE_URL", "").rstrip("/")
    # Prefixo de path quando o catálogo é exposto atrás de reverse-proxy
    # (ex.: 3-VM em https://app2037.fly.dev/loja → "/loja").
    url_prefix_raw: str = os.getenv("CATALOGO_URL_PREFIX", "").strip()
    default_store_slug: str = os.getenv(
        "CATALOGO_DEFAULT_STORE_SLUG", "moto-center"
    ).strip()
    secure_cookie: bool = os.getenv("CATALOGO_SECURE_COOKIE", "0") == "1"
    events_url: str = os.getenv("CATALOGO_EVENTS_URL", "").rstrip("/")
    # No bundle 3-VM, Portal e Catálogo podem reutilizar a credencial interna
    # tenant-scoped do Chatbot. Deploys separados continuam podendo fornecer uma
    # credencial dedicada por CATALOGO_EVENTS_TOKEN.
    events_token: str = (
        os.getenv("CATALOGO_EVENTS_TOKEN")
        or os.getenv("CHATBOT_API_TOKEN")
        or ""
    )
    events_timeout: float = float(os.getenv("CATALOGO_EVENTS_TIMEOUT", "5"))
    events_max_attempts: int = max(1, int(os.getenv("CATALOGO_EVENTS_MAX_ATTEMPTS", "5")))
    events_worker_interval: float = max(
        0.5, float(os.getenv("CATALOGO_EVENTS_WORKER_INTERVAL", "5"))
    )
    # Meta Pixel browser (E10). Fonte da verdade: config por loja.
    # Preferência: REVY_TRAFEGO_PUBLIC_URL (Fase 2) → PORTAL_PUBLIC_URL → PORTAL_PIXEL_URL.
    # Token CAPI NÃO vive no catálogo.
    portal_public_url: str = (
        os.getenv("REVY_TRAFEGO_PUBLIC_URL")
        or os.getenv("PORTAL_PUBLIC_URL")
        or os.getenv("PORTAL_PIXEL_URL")
        or ""
    ).strip().rstrip("/")
    # Compatibilidade para instalações antigas em que Portal e Catálogo usam
    # slugs diferentes para a mesma loja.
    portal_store_slug: str = os.getenv("CATALOGO_PORTAL_STORE_SLUG", "").strip()
    portal_pixel_timeout: float = float(os.getenv("CATALOGO_PORTAL_PIXEL_TIMEOUT", "2"))
    portal_pixel_cache_ttl: float = float(
        os.getenv("CATALOGO_PORTAL_PIXEL_CACHE_TTL", "60")
    )
    meta_pixel_id: str = (os.getenv("META_PIXEL_ID") or "").strip()
    meta_pixel_enabled_raw: str = os.getenv("META_PIXEL_ENABLED", "").strip().lower()

    @property
    def inventory_url_valid(self) -> bool:
        parsed = urlparse(self.inventory_url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @property
    def url_prefix(self) -> str:
        """Prefixo público sem barra final ('' ou '/loja')."""
        raw = self.url_prefix_raw
        if not raw and self.public_base_url:
            path = urlparse(self.public_base_url).path.rstrip("/")
            if path and path != "/":
                raw = path
        if not raw or raw == "/":
            return ""
        if not raw.startswith("/"):
            raw = "/" + raw
        return raw.rstrip("/")

    @property
    def meta_pixel_disabled(self) -> bool:
        return self.meta_pixel_enabled_raw in {"0", "false", "no", "off"}

    @property
    def meta_pixel_csp_needed(self) -> bool:
        """CSP do Facebook se o catálogo pode servir Pixel (Portal ou env)."""
        if self.meta_pixel_disabled:
            return False
        return bool(self.meta_pixel_id or self.portal_public_url)

    @property
    def meta_pixel_enabled(self) -> bool:
        """Compat: True se env fallback tem Pixel e não foi desligado."""
        if self.meta_pixel_disabled or not self.meta_pixel_id:
            return False
        return True


settings = Settings()
