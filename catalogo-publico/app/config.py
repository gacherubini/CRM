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
    events_token: str = os.getenv("CATALOGO_EVENTS_TOKEN", "")
    events_timeout: float = float(os.getenv("CATALOGO_EVENTS_TIMEOUT", "5"))
    events_max_attempts: int = max(1, int(os.getenv("CATALOGO_EVENTS_MAX_ATTEMPTS", "5")))
    events_worker_interval: float = max(
        0.5, float(os.getenv("CATALOGO_EVENTS_WORKER_INTERVAL", "5"))
    )
    # Meta Pixel browser (E10). Pixel ID é público; token CAPI NÃO vive no catálogo.
    # Deve coincidir com o Pixel ID configurado no Portal (aba Tráfego).
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
    def meta_pixel_enabled(self) -> bool:
        if not self.meta_pixel_id:
            return False
        if self.meta_pixel_enabled_raw in {"0", "false", "no", "off"}:
            return False
        if self.meta_pixel_enabled_raw in {"1", "true", "yes", "on"}:
            return True
        # default: ligado quando há Pixel ID
        return True


settings = Settings()
