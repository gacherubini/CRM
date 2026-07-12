"""Configuração do Chatbot API (Plano #2A)."""
import os

VERSAO = os.getenv("CHATBOT_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("CHATBOT_SCHEMA_VERSAO", "0")

# Segredo compartilhado com a Evolution/n8n para autenticar o webhook.
# Vazio = webhook aberto (comportamento atual); PRODUÇÃO DEVE definir isto.
WEBHOOK_TOKEN = os.getenv("CHATBOT_WEBHOOK_TOKEN", "")

# Provider de simulação: none (Atendimento) | mock (demo) | http (Motor real)
SIMULATION_PROVIDER = os.getenv("SIMULATION_PROVIDER", "none")
MOTOR_URL = os.getenv("MOTOR_URL", "")
MOTOR_TOKEN = os.getenv("MOTOR_TOKEN", "")
MOTOR_REQUEST_TIMEOUT = float(os.getenv("MOTOR_REQUEST_TIMEOUT", "5"))
MOTOR_POLL_TIMEOUT = float(os.getenv("MOTOR_POLL_TIMEOUT", "20"))
MOTOR_POLL_INTERVAL = float(os.getenv("MOTOR_POLL_INTERVAL", "0.5"))
