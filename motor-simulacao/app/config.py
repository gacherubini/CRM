"""Configuração tipada do Motor de Simulação.

Milestone 1: constantes com override por variável de ambiente. Endurecimento
(pydantic-settings, proibir defaults em produção) entra na Task de scaffold/qualidade.
"""
import os

VERSAO = os.getenv("MOTOR_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("MOTOR_SCHEMA_VERSAO", "0")

IDADE_MINIMA = int(os.getenv("IDADE_MINIMA", "18"))
PRAZO_MIN = int(os.getenv("PRAZO_MIN", "6"))
PRAZO_MAX = int(os.getenv("PRAZO_MAX", "60"))

# Categorias de veículo versionadas (Plano #1A, Task 2).
CATEGORIAS = ("moto", "carro", "leve")
