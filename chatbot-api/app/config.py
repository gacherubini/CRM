"""Configuração do Chatbot API (Plano #2A)."""
import os

VERSAO = os.getenv("CHATBOT_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("CHATBOT_SCHEMA_VERSAO", "0")

# Segredo compartilhado com a Evolution/n8n para autenticar o webhook.
# Vazio = webhook aberto (comportamento atual); PRODUÇÃO DEVE definir isto.
WEBHOOK_TOKEN = os.getenv("CHATBOT_WEBHOOK_TOKEN", "")

# Hardening da entrada do webhook. O limite de requisições é por processo e por
# origem de rede; zero desliga o rate limit (útil somente em desenvolvimento).
WEBHOOK_MAX_PAYLOAD_BYTES = int(os.getenv("CHATBOT_WEBHOOK_MAX_PAYLOAD_BYTES", "32768"))
WEBHOOK_MAX_TEXT_CHARS = int(os.getenv("CHATBOT_WEBHOOK_MAX_TEXT_CHARS", "4096"))
WEBHOOK_MAX_INSTANCE_CHARS = int(os.getenv("CHATBOT_WEBHOOK_MAX_INSTANCE_CHARS", "120"))
WEBHOOK_MAX_PROVIDER_MESSAGE_ID_CHARS = int(
    os.getenv("CHATBOT_WEBHOOK_MAX_PROVIDER_MESSAGE_ID_CHARS", "255")
)
WEBHOOK_MAX_EVENT_TYPE_CHARS = int(
    os.getenv("CHATBOT_WEBHOOK_MAX_EVENT_TYPE_CHARS", "64")
)
WEBHOOK_RATE_LIMIT_REQUESTS = int(
    os.getenv("CHATBOT_WEBHOOK_RATE_LIMIT_REQUESTS", "600")
)
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS = float(
    os.getenv("CHATBOT_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS", "60")
)
WEBHOOK_RATE_LIMIT_MAX_BUCKETS = int(
    os.getenv("CHATBOT_WEBHOOK_RATE_LIMIT_MAX_BUCKETS", "10000")
)

# Provider de simulação: none (Atendimento) | mock (demo) | http (Motor real)
SIMULATION_PROVIDER = os.getenv("SIMULATION_PROVIDER", "none")
MOTOR_URL = os.getenv("MOTOR_URL", "")
MOTOR_TOKEN = os.getenv("MOTOR_TOKEN", "")
MOTOR_REQUEST_TIMEOUT = float(os.getenv("MOTOR_REQUEST_TIMEOUT", "5"))
MOTOR_POLL_TIMEOUT = float(os.getenv("MOTOR_POLL_TIMEOUT", "20"))
MOTOR_POLL_INTERVAL = float(os.getenv("MOTOR_POLL_INTERVAL", "0.5"))

# Estoque: público (busca catálogo) e privado (por-placa + escrita E5).
# ESTOQUE_PUBLIC_URL: GET /public/v1/... (sem token).
# ESTOQUE_API_URL + ESTOQUE_API_TOKEN: GET por-placa e POST /v1/veiculos.
ESTOQUE_PUBLIC_URL = os.getenv("ESTOQUE_PUBLIC_URL", "")
ESTOQUE_API_URL = os.getenv("ESTOQUE_API_URL", "")
ESTOQUE_API_TOKEN = os.getenv("ESTOQUE_API_TOKEN", "")
ESTOQUE_REQUEST_TIMEOUT = float(os.getenv("ESTOQUE_REQUEST_TIMEOUT", "8"))

# Prazos padrão multi-opção quando o cliente não escolhe um único prazo (CRM WhatsApp).
PRAZOS_PADRAO_MESES: list[int] = [24, 36, 48, 60]
