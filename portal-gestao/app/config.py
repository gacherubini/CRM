import os
from dataclasses import dataclass


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- Revy Loja (flags default OFF; leem env em runtime para testes/monkeypatch) ---


def revy_loja_shell_enabled() -> bool:
    """Shell com nav Vendas/Estoque. Default off = UI legada do portal."""
    return _env_bool("REVY_LOJA_SHELL_ENABLED", "0")


def revy_loja_entitlements_enabled() -> bool:
    """Gates de módulo via projeção/Control. Default off = fail-open legado."""
    return _env_bool("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


def revy_loja_atendimento_enabled() -> bool:
    """Workspace unificado de Atendimento (F4+). Default off."""
    return _env_bool("REVY_LOJA_ATENDIMENTO_ENABLED", "0")


def revy_loja_whatsapp_enabled() -> bool:
    """Tela de números de WhatsApp em Ajustes da Loja. Default off.

    Só age com ``REVY_LOJA_SHELL_ENABLED=1`` (gate duplo nas rotas).
    """
    return _env_bool("REVY_LOJA_WHATSAPP_ENABLED", "0")


def revy_loja_copiloto_enabled() -> bool:
    """Seção Copiloto de Vendas da Loja. Default off.

    É kill-switch global do deploy: quem libera loja a loja é o entitlement
    (``Module.COPILOTO``). Só age com ``REVY_LOJA_SHELL_ENABLED=1``.
    """
    return _env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")


def revy_loja_redirect_legacy_enabled() -> bool:
    """Redirects 303 de rotas legadas → shell Loja (F8 cutover). Default off.

    Só age com ``REVY_LOJA_SHELL_ENABLED=1``. Ver
    ``portal-gestao/docs/revy-loja-cutover.md``.
    """
    return _env_bool("REVY_LOJA_REDIRECT_LEGACY", "0")


def seller_ai_enabled() -> bool:
    """Seller AI (F7+). Default off."""
    return _env_bool("SELLER_AI_ENABLED", "0")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("PORTAL_DATABASE_URL", "sqlite:///./portal.db")
    session_secret: str = os.getenv("PORTAL_SESSION_SECRET", "dev-troque-esta-chave")
    identity_hmac_secret: str = (
        os.getenv("PORTAL_IDENTITY_HMAC_SECRET")
        or os.getenv("PORTAL_SESSION_SECRET", "dev-troque-esta-chave")
    )
    # Chave Fernet dedicada para token CAPI (E10). Preferir PORTAL_ENCRYPTION_KEY;
    # em dev o módulo app.cripto usa fallback se ausente (nunca em PORTAL_ENV=production).
    encryption_key: str = os.getenv("PORTAL_ENCRYPTION_KEY", "")
    secure_cookie: bool = os.getenv("PORTAL_SECURE_COOKIE", "0") == "1"
    estoque_url: str = os.getenv("ESTOQUE_API_URL", "http://estoque-api:8000")
    estoque_token: str = os.getenv("ESTOQUE_API_TOKEN", "")
    chatbot_url: str = os.getenv("CHATBOT_API_URL", "http://chatbot-api:8000")
    chatbot_token: str = os.getenv("CHATBOT_API_TOKEN", "")
    motor_url: str = (
        os.getenv("MOTOR_URL")
        or os.getenv("MOTOR_API_URL", "http://motor-simulacao:8000")
    )
    motor_token: str = (
        os.getenv("MOTOR_TOKEN") or os.getenv("MOTOR_API_TOKEN", "")
    )
    request_timeout: float = float(os.getenv("PORTAL_HTTP_TIMEOUT", "5"))
    request_retries: int = int(os.getenv("PORTAL_HTTP_RETRIES", "1"))
    request_retry_backoff: float = float(
        os.getenv("PORTAL_HTTP_RETRY_BACKOFF", "0.2")
    )
    timezone: str = os.getenv("PORTAL_TIMEZONE", "America/Sao_Paulo")
    version: str = os.getenv("PORTAL_VERSION", "0.1.0")
    # Job diário de spend Meta (Marketing API). Segredo para POST /internal/jobs/...
    meta_spend_sync_enabled: bool = (
        os.getenv("PORTAL_META_SPEND_SYNC_ENABLED", "1").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    meta_spend_sync_interval_seconds: float = float(
        os.getenv("PORTAL_META_SPEND_SYNC_INTERVAL_SECONDS", "86400")
    )
    meta_spend_sync_initial_delay_seconds: float = float(
        os.getenv("PORTAL_META_SPEND_SYNC_INITIAL_DELAY_SECONDS", "120")
    )
    meta_spend_sync_janela_dias: int = int(
        os.getenv("PORTAL_META_SPEND_SYNC_JANELA_DIAS", "3")
    )
    meta_spend_job_secret: str = os.getenv("PORTAL_META_SPEND_JOB_SECRET", "").strip()
    # Revy Tráfego (Fase 2): resultados e notificação de venda via HTTP.
    revy_trafego_url: str = (
        os.getenv("REVY_TRAFEGO_URL") or os.getenv("PORTAL_REVY_TRAFEGO_URL") or ""
    ).strip().rstrip("/")
    revy_trafego_service_token: str = os.getenv(
        "REVY_TRAFEGO_SERVICE_TOKEN", ""
    ).strip()
    revy_trafego_timeout: float = float(os.getenv("PORTAL_REVY_TRAFEGO_TIMEOUT", "4"))
    revy_trafego_resultados_enabled: bool = (
        os.getenv("PORTAL_REVY_TRAFEGO_RESULTADOS", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    revy_trafego_venda_events_enabled: bool = (
        os.getenv("PORTAL_REVY_TRAFEGO_VENDA_EVENTS", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    # Token de serviço para POST /internal/v1/provisioning/state (Control → Portal).
    # Preferir PORTAL_SERVICE_TOKEN; PORTAL_PROVISIONING_TOKEN é alias.
    service_token: str = (
        os.getenv("PORTAL_SERVICE_TOKEN")
        or os.getenv("PORTAL_PROVISIONING_TOKEN")
        or ""
    ).strip()
    # Convites do Portal. Durante o rollout, reutiliza o SMTP já configurado
    # no bundle do Revy Control quando os equivalentes PORTAL_* não existirem.
    email_backend: str = os.getenv(
        "PORTAL_EMAIL_BACKEND",
        os.getenv("REVY_TRAFEGO_EMAIL_BACKEND", "console"),
    ).strip().lower()
    email_from: str = os.getenv(
        "PORTAL_EMAIL_FROM",
        os.getenv("REVY_TRAFEGO_EMAIL_FROM", "no-reply@revy.local"),
    ).strip()
    email_from_name: str = os.getenv(
        "PORTAL_EMAIL_FROM_NAME",
        os.getenv("REVY_TRAFEGO_EMAIL_FROM_NAME", "Revy"),
    ).strip()
    smtp_host: str = os.getenv(
        "PORTAL_SMTP_HOST", os.getenv("REVY_TRAFEGO_SMTP_HOST", "")
    ).strip()
    smtp_port: int = int(
        os.getenv("PORTAL_SMTP_PORT", os.getenv("REVY_TRAFEGO_SMTP_PORT", "587"))
    )
    smtp_username: str = os.getenv(
        "PORTAL_SMTP_USERNAME", os.getenv("REVY_TRAFEGO_SMTP_USERNAME", "")
    ).strip()
    smtp_password: str = os.getenv(
        "PORTAL_SMTP_PASSWORD", os.getenv("REVY_TRAFEGO_SMTP_PASSWORD", "")
    )
    smtp_use_tls: bool = os.getenv(
        "PORTAL_SMTP_USE_TLS", os.getenv("REVY_TRAFEGO_SMTP_USE_TLS", "1")
    ).strip().lower() in {"1", "true", "yes", "on"}
    public_base_url: str = os.getenv(
        "PORTAL_PUBLIC_BASE_URL",
        os.getenv("REVY_TRAFEGO_PUBLIC_BASE_URL", ""),
    ).strip().rstrip("/")
    # Revy Loja — snapshot no boot (preferir helpers revy_loja_*_enabled() em runtime).
    revy_loja_shell_enabled: bool = _env_bool("REVY_LOJA_SHELL_ENABLED", "0")
    revy_loja_entitlements_enabled: bool = _env_bool(
        "REVY_LOJA_ENTITLEMENTS_ENABLED", "0"
    )
    revy_loja_atendimento_enabled: bool = _env_bool(
        "REVY_LOJA_ATENDIMENTO_ENABLED", "0"
    )
    revy_loja_whatsapp_enabled: bool = _env_bool("REVY_LOJA_WHATSAPP_ENABLED", "0")
    revy_loja_copiloto_enabled: bool = _env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")
    revy_loja_redirect_legacy_enabled: bool = _env_bool(
        "REVY_LOJA_REDIRECT_LEGACY", "0"
    )
    seller_ai_enabled: bool = _env_bool("SELLER_AI_ENABLED", "0")
    # Copiloto de Vendas — provedor de LLM (DeepSeek, API compatível com OpenAI).
    copiloto_llm_url: str = os.getenv(
        "REVY_LOJA_COPILOTO_LLM_URL", "https://api.deepseek.com"
    ).strip().rstrip("/")
    copiloto_llm_key: str = os.getenv("REVY_LOJA_COPILOTO_LLM_KEY", "").strip()
    copiloto_llm_model: str = os.getenv(
        "REVY_LOJA_COPILOTO_LLM_MODEL", "DeepSeek-V4-Flash-0731"
    ).strip()
    copiloto_llm_timeout: float = float(
        os.getenv("REVY_LOJA_COPILOTO_LLM_TIMEOUT", "40")
    )
    copiloto_llm_retries: int = int(os.getenv("REVY_LOJA_COPILOTO_LLM_RETRIES", "1"))
    # Retenção de conversas do Copiloto (dias). Purge ainda não está implementado;
    # este valor é o contrato para quando o job de limpeza existir.
    copiloto_retencao_dias: int = int(
        os.getenv("PORTAL_COPILOTO_RETENCAO_DIAS", "90")
    )

    def absolute_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{self.public_base_url}{normalized}" if self.public_base_url else normalized


settings = Settings()
