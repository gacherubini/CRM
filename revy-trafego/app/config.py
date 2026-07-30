import os
import json
from dataclasses import dataclass, field


def _env_flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
    estoque_url: str = os.getenv("ESTOQUE_API_URL", "http://estoque-api:8000")
    estoque_token: str = os.getenv("ESTOQUE_API_TOKEN", "")
    estoque_token_loja: str = os.getenv(
        "REVY_TRAFEGO_ESTOQUE_TOKEN_LOJA", ""
    ).strip()
    estoque_tokens_json: str = os.getenv(
        "REVY_TRAFEGO_ESTOQUE_TOKENS_JSON", ""
    ).strip()
    portal_url: str = os.getenv(
        "PORTAL_API_URL",
        os.getenv("PORTAL_PUBLIC_URL", "http://portal-gestao:8000"),
    )
    portal_service_token: str = (
        os.getenv("PORTAL_SERVICE_TOKEN")
        or os.getenv("PORTAL_PROVISIONING_TOKEN")
        or ""
    ).strip()
    motor_url: str = os.getenv(
        "MOTOR_URL", os.getenv("MOTOR_API_URL", "http://motor-simulacao:8000")
    )
    motor_token: str = (
        os.getenv("MOTOR_TOKEN") or os.getenv("MOTOR_API_TOKEN") or ""
    ).strip()
    motor_token_loja: str = os.getenv("REVY_TRAFEGO_MOTOR_TOKEN_LOJA", "").strip()
    motor_tokens_json: str = os.getenv("REVY_TRAFEGO_MOTOR_TOKENS_JSON", "").strip()
    catalogo_url: str = os.getenv(
        "CATALOGO_PUBLIC_URL",
        os.getenv("CATALOGO_API_URL", "http://catalogo-publico:8000"),
    )
    catalogo_service_token: str = (
        os.getenv("CATALOGO_SERVICE_TOKEN")
        or os.getenv("CATALOGO_PROVISIONING_TOKEN")
        or ""
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
    google_ads_sync_enabled: bool = field(
        default_factory=lambda: _env_flag("GOOGLE_ADS_SYNC_ENABLED")
    )
    google_conversions_enabled: bool = field(
        default_factory=lambda: _env_flag("GOOGLE_CONVERSIONS_ENABLED")
    )
    # OAuth multiusuário Google Ads (secret manager / env; nunca no repositório).
    google_ads_oauth_client_id: str = os.getenv(
        "GOOGLE_ADS_OAUTH_CLIENT_ID", ""
    ).strip()
    google_ads_oauth_client_secret: str = os.getenv(
        "GOOGLE_ADS_OAUTH_CLIENT_SECRET", ""
    ).strip()
    google_ads_oauth_redirect_uri: str = os.getenv(
        "GOOGLE_ADS_OAUTH_REDIRECT_URI", ""
    ).strip()
    # Developer token da Google Ads API (API Center do manager Revy).
    google_ads_developer_token: str = os.getenv(
        "GOOGLE_ADS_DEVELOPER_TOKEN", ""
    ).strip()
    # Versão REST da Google Ads API (ex.: v19). Data Manager usa /v1 fixo.
    google_ads_api_version: str = (
        os.getenv("GOOGLE_ADS_API_VERSION", "v19").strip() or "v19"
    )
    # Bases HTTP injetáveis (testes / proxy). Vazias usam defaults oficiais.
    google_ads_api_base_url: str = os.getenv(
        "GOOGLE_ADS_API_BASE_URL", ""
    ).strip()
    google_data_manager_base_url: str = os.getenv(
        "GOOGLE_DATA_MANAGER_BASE_URL", ""
    ).strip()
    google_oauth_token_url: str = os.getenv(
        "GOOGLE_OAUTH_TOKEN_URL", ""
    ).strip()
    multi_whatsapp_enabled: bool = field(
        default_factory=lambda: _env_flag("MULTI_WHATSAPP_ENABLED")
    )
    revy_control_dashboard_enabled: bool = field(
        default_factory=lambda: _env_flag("REVY_CONTROL_DASHBOARD_ENABLED")
    )
    # Worker de entrega da outbox de provisionamento (default off; sem thread nesta fatia).
    revy_control_provisioning_delivery_enabled: bool = field(
        default_factory=lambda: _env_flag(
            "REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED"
        )
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
        return self._token_para_slug(
            loja_slug,
            tokens_json=self.chatbot_tokens_json,
            token_loja=self.chatbot_token_loja,
            token=self.chatbot_token,
        )

    def estoque_token_para(self, loja_slug: str) -> str:
        """Resolve credencial Estoque por loja (mesmo modelo do Chatbot)."""
        return self._token_para_slug(
            loja_slug,
            tokens_json=self.estoque_tokens_json,
            token_loja=self.estoque_token_loja,
            token=self.estoque_token,
        )

    def motor_token_para(self, loja_slug: str) -> str:
        """Resolve credencial Motor por loja (Bearer do cliente API)."""
        return self._token_para_slug(
            loja_slug,
            tokens_json=self.motor_tokens_json,
            token_loja=self.motor_token_loja,
            token=self.motor_token,
        )

    def _token_para_slug(
        self,
        loja_slug: str,
        *,
        tokens_json: str,
        token_loja: str,
        token: str,
    ) -> str:
        slug = (loja_slug or "").strip()
        if tokens_json:
            try:
                tokens = json.loads(tokens_json)
            except (TypeError, ValueError):
                return ""
            if isinstance(tokens, dict):
                return str(tokens.get(slug) or "").strip()
            return ""
        if token_loja:
            return token if token_loja == slug else ""
        lojas = {
            item.strip()
            for item in (os.getenv("REVY_TRAFEGO_LOJAS") or "").replace(";", ",").split(",")
            if item.strip()
        }
        if len(lojas) == 1 and slug in lojas:
            return token
        return ""


settings = Settings()
