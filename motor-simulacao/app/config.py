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
METRICS_TOKEN = os.getenv("MOTOR_METRICS_TOKEN", "")
JOB_LEASE_SECONDS = int(os.getenv("MOTOR_JOB_LEASE_SECONDS", "120"))

# Prazos padrão multi-opção (CRM / driver real).
PRAZOS_PADRAO_MESES: list[int] = [24, 36, 48, 60]
# Screenshots de falha do Playwright (fora do git em produção).
SCREENSHOT_DIR = os.getenv("MOTOR_SCREENSHOT_DIR", "data/screenshots")
STORAGE_STATE_DIR = os.getenv("MOTOR_STORAGE_STATE_DIR", "data/storage_state")

# Categorias de veículo versionadas (Plano #1A, Task 2).
CATEGORIAS = ("moto", "carro", "leve")