"""Configuração do Estoque API (Plano #4A)."""
import os

VERSAO = os.getenv("ESTOQUE_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("ESTOQUE_SCHEMA_VERSAO", "0")

TIPOS = ("moto", "carro")
STATUS = ("disponivel", "reservado", "vendido", "indisponivel")
PAPEIS = ("dono", "gerente", "operador")
