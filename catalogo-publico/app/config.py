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
    secure_cookie: bool = os.getenv("CATALOGO_SECURE_COOKIE", "0") == "1"

    @property
    def inventory_url_valid(self) -> bool:
        parsed = urlparse(self.inventory_url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


settings = Settings()
