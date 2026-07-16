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
JOB_LEASE_SECONDS = int(os.getenv("MOTOR_JOB_LEASE_SECONDS", "480"))
DRIVER_TIMEOUT_SECONDS = int(os.getenv("MOTOR_DRIVER_TIMEOUT_SECONDS", "420"))
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
BROWSER_TIMEOUT_MS = int(os.getenv("MOTOR_BROWSER_TIMEOUT_MS", "90000"))
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
BRADESCO_LOGIN_URL = os.getenv(
    "MOTOR_BRADESCO_LOGIN_URL",
    "https://turbo.bradesco/originacaolojista/login",
)
PAN_PORTAL_LOGIN_URL = os.getenv(
    "MOTOR_PAN_PORTAL_LOGIN_URL",
    "https://veiculos.bancopan.com.br/login",
)

# Banco PAN OpenAPI Veículos. Sandbox é o default deliberado; produção exige
# override explícito depois da homologação comercial do parceiro.
PAN_BASE_URL = os.getenv("MOTOR_PAN_BASE_URL", "https://sandbox-hml.bancopan.com.br")
PAN_TIMEOUT_SECONDS = float(os.getenv("MOTOR_PAN_TIMEOUT_SECONDS", "30"))

# Categorias de veículo versionadas (Plano #1A, Task 2).
CATEGORIAS = ("moto", "carro", "leve")

# Fan-out multi-banco + workers sob demanda (plano 2026-07-14).
# Defaults desligados: com flags off o pipeline se comporta como antes.
def _flag(nome: str, default: str = "0") -> bool:
    return (os.getenv(nome) or default).strip().lower() in ("1", "true", "yes", "on")


FANOUT_ENABLED = _flag("MOTOR_FANOUT_ENABLED", "0")
FLY_AUTOSCALE_ENABLED = _flag("MOTOR_FLY_AUTOSCALE_ENABLED", "0")
# Default 4: um slot por banco Playwright (santander/fontecred/bradesco/pan).
MAX_BROWSER_WORKERS = int(os.getenv("MOTOR_MAX_BROWSER_WORKERS", "4"))
WORKER_IDLE_STOP_SECONDS = int(os.getenv("MOTOR_WORKER_IDLE_STOP_SECONDS", "60"))
WORKER_PROVEDOR = (os.getenv("MOTOR_WORKER_PROVEDOR") or "").strip().lower() or None
WORKER_SLOT_ID = (os.getenv("MOTOR_WORKER_SLOT_ID") or "").strip() or None
# Worker sob demanda: após idle grace encerra com exit 0 (Machine para com restart on-failure).
WORKER_ON_DEMAND = _flag("MOTOR_WORKER_ON_DEMAND", "0") or bool(WORKER_PROVEDOR)
# Filtro opcional de tipos: "api,playwright,mock" (vazio = todos).
_WORKER_TIPOS_RAW = (os.getenv("MOTOR_WORKER_TIPOS") or "").strip().lower()
WORKER_TIPOS: frozenset[str] | None = (
    frozenset(p.strip() for p in _WORKER_TIPOS_RAW.split(",") if p.strip())
    if _WORKER_TIPOS_RAW
    else None
)
TASK_LEASE_SECONDS = int(
    os.getenv("MOTOR_TASK_LEASE_SECONDS") or os.getenv("MOTOR_JOB_LEASE_SECONDS", "300")
)

# Fly Machines API (orquestrador na API — nunca no worker on-demand).
FLY_API_BASE = (os.getenv("FLY_API_BASE") or "https://api.machines.dev").rstrip("/")
FLY_APP_NAME = (os.getenv("FLY_APP_NAME") or os.getenv("FLY_APP") or "motor2037").strip()
# Token app-scoped; vazio desliga wake real (fake em testes / lab sem token).
FLY_API_TOKEN = (os.getenv("FLY_API_TOKEN") or os.getenv("MOTOR_FLY_API_TOKEN") or "").strip()
FLY_START_TIMEOUT_SECONDS = float(os.getenv("MOTOR_FLY_START_TIMEOUT_SECONDS", "8"))
# Quantos starts HTTP em paralelo (acordar todos os bancos de uma simulação).
FLY_START_BURST = int(os.getenv("MOTOR_FLY_START_BURST", "4"))
