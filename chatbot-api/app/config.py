"""Configuração do Chatbot API (Plano #2A)."""
import os

VERSAO = os.getenv("CHATBOT_VERSAO", "0.1.0")
SCHEMA_VERSAO = os.getenv("CHATBOT_SCHEMA_VERSAO", "0")

# Provider de simulação: none (Atendimento) | mock (demo) | http (Motor real)
SIMULATION_PROVIDER = os.getenv("SIMULATION_PROVIDER", "none")
MOTOR_URL = os.getenv("MOTOR_URL", "")
