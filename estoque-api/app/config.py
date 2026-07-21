"""Configuração do Estoque API (Plano #4A)."""
import os
from pathlib import Path

VERSAO = os.getenv("ESTOQUE_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("ESTOQUE_SCHEMA_VERSAO", "0")

TIPOS = ("moto", "carro")
STATUS = ("disponivel", "reservado", "vendido", "indisponivel")
PAPEIS = ("dono", "gerente", "operador", "leitor")
PUBLIC_RATE_LIMIT_PER_MINUTE = int(os.getenv("ESTOQUE_PUBLIC_RATE_LIMIT", "120"))
SESSION_SECRET = os.getenv("ESTOQUE_SESSION_SECRET", "dev-troque-esta-chave")
SESSION_SECURE_COOKIE = os.getenv("ESTOQUE_SESSION_SECURE_COOKIE", "0") == "1"

# Fotos ficam fora do banco: volume persistente no MVP ou object storage em
# escala. O banco guarda somente URL e metadados, nunca base64/binário.
# ``PUBLIC_BASE_URL`` materializa uma URL estável sem expor paths internos.
MEDIA_PUBLIC_BASE_URL = os.getenv("ESTOQUE_MEDIA_PUBLIC_BASE_URL", "").rstrip("/")
MEDIA_MAX_FOTOS = int(os.getenv("ESTOQUE_MEDIA_MAX_FOTOS", "20"))
MEDIA_MAX_BYTES = int(os.getenv("ESTOQUE_MEDIA_MAX_BYTES", str(10 * 1024 * 1024)))
MEDIA_ORPHAN_GRACE_SECONDS = max(
    0, int(os.getenv("ESTOQUE_MEDIA_ORPHAN_GRACE_SECONDS", "3600"))
)
MEDIA_URL_MAX_CHARS = int(os.getenv("ESTOQUE_MEDIA_URL_MAX_CHARS", "2048"))
MEDIA_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
MEDIA_ALLOWED_HOSTS = tuple(
    host.strip().lower().rstrip(".")
    for host in os.getenv("ESTOQUE_MEDIA_ALLOWED_HOSTS", "").split(",")
    if host.strip()
)
# Upload automático recebido do WhatsApp. O diretório deve apontar para volume
# persistente; a URL pública deve terminar na rota /public/v1/media (ou em um
# proxy/CDN que sirva exatamente as mesmas chaves).
MEDIA_STORAGE_DIR = Path(
    os.getenv("ESTOQUE_MEDIA_STORAGE_DIR", "/data/media")
).resolve()
