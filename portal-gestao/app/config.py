import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("PORTAL_DATABASE_URL", "sqlite:///./portal.db")
    session_secret: str = os.getenv("PORTAL_SESSION_SECRET", "dev-troque-esta-chave")
    identity_hmac_secret: str = (
        os.getenv("PORTAL_IDENTITY_HMAC_SECRET")
        or os.getenv("PORTAL_SESSION_SECRET", "dev-troque-esta-chave")
    )
    secure_cookie: bool = os.getenv("PORTAL_SECURE_COOKIE", "0") == "1"
    estoque_url: str = os.getenv("ESTOQUE_API_URL", "http://estoque-api:8000")
    estoque_token: str = os.getenv("ESTOQUE_API_TOKEN", "")
    chatbot_url: str = os.getenv("CHATBOT_API_URL", "http://chatbot-api:8000")
    chatbot_token: str = os.getenv("CHATBOT_API_TOKEN", "")
    request_timeout: float = float(os.getenv("PORTAL_HTTP_TIMEOUT", "5"))
    version: str = os.getenv("PORTAL_VERSION", "0.1.0")


settings = Settings()
