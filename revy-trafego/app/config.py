import os
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "REVY_TRAFEGO_DATABASE_URL",
        "sqlite:///./revy_trafego.db",
    )
    session_secret: str = os.getenv("REVY_TRAFEGO_SESSION_SECRET", "dev-trafego-troque")
    encryption_key: str = (
        os.getenv("REVY_TRAFEGO_ENCRYPTION_KEY")
        or os.getenv("PORTAL_ENCRYPTION_KEY", "")
    )
    secure_cookie: bool = os.getenv("REVY_TRAFEGO_SECURE_COOKIE", "0") == "1"
    chatbot_url: str = os.getenv("CHATBOT_API_URL", "http://chatbot-api:8000")
    chatbot_token: str = os.getenv("CHATBOT_API_TOKEN", "")
    chatbot_token_loja: str = os.getenv(
        "REVY_TRAFEGO_CHATBOT_TOKEN_LOJA", ""
    ).strip()
    chatbot_tokens_json: str = os.getenv(
        "REVY_TRAFEGO_CHATBOT_TOKENS_JSON", ""
    ).strip()
    request_timeout: float = float(os.getenv("REVY_TRAFEGO_HTTP_TIMEOUT", "5"))
    request_retries: int = int(os.getenv("REVY_TRAFEGO_HTTP_RETRIES", "1"))
    request_retry_backoff: float = float(
        os.getenv("REVY_TRAFEGO_HTTP_RETRY_BACKOFF", "0.2")
    )
    timezone: str = os.getenv("REVY_TRAFEGO_TIMEZONE", "America/Sao_Paulo")
    version: str = os.getenv("REVY_TRAFEGO_VERSION", "0.1.0")
    bootstrap_email: str = os.getenv(
        "REVY_TRAFEGO_BOOTSTRAP_EMAIL", "trafego@revy.local"
    )
    bootstrap_senha: str = os.getenv("REVY_TRAFEGO_BOOTSTRAP_SENHA", "troque-isto")
    bootstrap_nome: str = os.getenv("REVY_TRAFEGO_BOOTSTRAP_NOME", "Equipe Tráfego")
    # Workers OFF por padrão na Fase 1 (portal ainda processa CAPI/spend).
    meta_spend_sync_enabled: bool = (
        os.getenv("REVY_TRAFEGO_META_SPEND_SYNC_ENABLED", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    run_capi_worker: bool = (
        os.getenv("REVY_TRAFEGO_CAPI_WORKER", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    revy_control_enabled: bool = (
        os.getenv("REVY_CONTROL_ENABLED", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    revy_control_rbac_enabled: bool = (
        os.getenv("REVY_CONTROL_RBAC_ENABLED", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    job_secret: str = os.getenv("REVY_TRAFEGO_JOB_SECRET", "").strip()
    # Token entre portal/catálogo e este app (header X-Service-Token).
    service_token: str = os.getenv("REVY_TRAFEGO_SERVICE_TOKEN", "").strip()
    # Prefixo público no edge (ex.: /trafego no app2037). Vazio em local puro.
    url_prefix_raw: str = os.getenv("REVY_TRAFEGO_URL_PREFIX", "").strip()

    @property
    def url_prefix(self) -> str:
        raw = (self.url_prefix_raw or "").strip()
        if not raw:
            return ""
        if not raw.startswith("/"):
            raw = "/" + raw
        return raw.rstrip("/")

    def chatbot_token_para(self, loja_slug: str) -> str:
        """Resolve credencial por loja; falha fechado se o escopo for ambiguo."""
        slug = (loja_slug or "").strip()
        if self.chatbot_tokens_json:
            try:
                tokens = json.loads(self.chatbot_tokens_json)
            except (TypeError, ValueError):
                return ""
            if isinstance(tokens, dict):
                return str(tokens.get(slug) or "").strip()
            return ""
        if self.chatbot_token_loja:
            return self.chatbot_token if self.chatbot_token_loja == slug else ""
        lojas = {
            item.strip()
            for item in (os.getenv("REVY_TRAFEGO_LOJAS") or "").replace(";", ",").split(",")
            if item.strip()
        }
        if len(lojas) == 1 and slug in lojas:
            return self.chatbot_token
        return ""


settings = Settings()
