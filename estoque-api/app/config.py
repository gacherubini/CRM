"""Configuração do Estoque API (Plano #4A)."""
import os

VERSAO = os.getenv("ESTOQUE_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("ESTOQUE_SCHEMA_VERSAO", "0")

TIPOS = ("moto", "carro")
STATUS = ("disponivel", "reservado", "vendido", "indisponivel")
PAPEIS = ("dono", "gerente", "operador", "leitor")
PUBLIC_RATE_LIMIT_PER_MINUTE = int(os.getenv("ESTOQUE_PUBLIC_RATE_LIMIT", "120"))
SESSION_SECRET = os.getenv("ESTOQUE_SESSION_SECRET", "dev-troque-esta-chave")
SESSION_SECURE_COOKIE = os.getenv("ESTOQUE_SESSION_SECURE_COOKIE", "0") == "1"

# Fotos ficam em object storage/CDN. O banco guarda somente URL e metadados,
# nunca base64/binário. ``PUBLIC_BASE_URL`` permite receber uma storage_key e
# materializar uma URL estável, sem expor paths internos do servidor.
MEDIA_PUBLIC_BASE_URL = os.getenv("ESTOQUE_MEDIA_PUBLIC_BASE_URL", "").rstrip("/")
MEDIA_MAX_FOTOS = int(os.getenv("ESTOQUE_MEDIA_MAX_FOTOS", "20"))
MEDIA_MAX_BYTES = int(os.getenv("ESTOQUE_MEDIA_MAX_BYTES", str(10 * 1024 * 1024)))
MEDIA_URL_MAX_CHARS = int(os.getenv("ESTOQUE_MEDIA_URL_MAX_CHARS", "2048"))
MEDIA_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
MEDIA_ALLOWED_HOSTS = tuple(
    host.strip().lower().rstrip(".")
    for host in os.getenv("ESTOQUE_MEDIA_ALLOWED_HOSTS", "").split(",")
    if host.strip()
)
