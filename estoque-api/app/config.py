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
