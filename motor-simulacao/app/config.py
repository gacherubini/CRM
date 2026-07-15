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
DRIVER_TIMEOUT_SECONDS = int(os.getenv("MOTOR_DRIVER_TIMEOUT_SECONDS", "240"))
EVENT_SCREENSHOTS = (os.getenv("MOTOR_EVENT_SCREENSHOTS") or "1").strip().lower() in (
    "1", "true", "yes", "on"
)
SCREENSHOT_RETENTION_DAYS = int(os.getenv("MOTOR_SCREENSHOT_RETENTION_DAYS", "7"))

# Prazos padrão multi-opção (CRM / driver real).
# Portal Santander costuma listar 12/24/36/48; 60 pode exigir "Simular outro prazo".
PRAZOS_PADRAO_MESES: list[int] = [24, 36, 48, 60]
PRAZOS_PADRAO = PRAZOS_PADRAO_MESES  # alias Task 12
# Screenshots / sessão browser (fora do git em produção).
SCREENSHOT_DIR = os.getenv("MOTOR_SCREENSHOT_DIR", "data/screenshots")
STORAGE_STATE_DIR = os.getenv("MOTOR_STORAGE_STATE_DIR", "data/storage_state")
BROWSER_TIMEOUT_MS = int(os.getenv("MOTOR_BROWSER_TIMEOUT_MS", "45000"))
# Headless=1 usa chromium headless_shell (muito bloqueado por Akamai).
# Padrão 0 = headed; no Docker o worker sobe com Xvfb (display virtual).
BROWSER_HEADLESS = (os.getenv("MOTOR_BROWSER_HEADLESS") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
SANTANDER_LOGIN_URL = os.getenv(
    "MOTOR_SANTANDER_LOGIN_URL",
    "https://financiamentos.santander.com.br/originacao-auto/login",
)
FONTECRED_LOGIN_URL = os.getenv(
    "MOTOR_FONTECRED_LOGIN_URL",
    "https://app.fontecred.com.br/login#step-1",
)

# Banco PAN OpenAPI Veículos. Sandbox é o default deliberado; produção exige
# override explícito depois da homologação comercial do parceiro.
PAN_BASE_URL = os.getenv("MOTOR_PAN_BASE_URL", "https://sandbox-hml.bancopan.com.br")
PAN_TIMEOUT_SECONDS = float(os.getenv("MOTOR_PAN_TIMEOUT_SECONDS", "30"))

# Categorias de veículo versionadas (Plano #1A, Task 2).
CATEGORIAS = ("moto", "carro", "leve")
