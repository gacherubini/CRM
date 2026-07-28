import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "REVY_TRAFEGO_DATABASE_URL",
        os.getenv("PORTAL_DATABASE_URL", "sqlite:///./revy_trafego.db"),
    )
    session_secret: str = os.getenv("REVY_TRAFEGO_SESSION_SECRET", "dev-trafego-troque")
    encryption_key: str = (
        os.getenv("REVY_TRAFEGO_ENCRYPTION_KEY")
        or os.getenv("PORTAL_ENCRYPTION_KEY", "")
    )
    secure_cookie: bool = os.getenv("REVY_TRAFEGO_SECURE_COOKIE", "0") == "1"
    chatbot_url: str = os.getenv("CHATBOT_API_URL", "http://chatbot-api:8000")
    chatbot_token: str = os.getenv("CHATBOT_API_TOKEN", "")
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
    job_secret: str = os.getenv("REVY_TRAFEGO_JOB_SECRET", "").strip()


settings = Settings()
