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

# Áudio recebido: download autenticado na Evolution e transcrição opcional.
AUDIO_EVOLUTION_URL = os.getenv("CHATBOT_AUDIO_EVOLUTION_URL", "")
AUDIO_EVOLUTION_API_KEY = os.getenv("CHATBOT_AUDIO_EVOLUTION_API_KEY", "")
AUDIO_TRANSCRIPTION_PROVIDER = os.getenv("CHATBOT_AUDIO_TRANSCRIPTION_PROVIDER", "none")
AUDIO_TRANSCRIPTION_URL = os.getenv("CHATBOT_AUDIO_TRANSCRIPTION_URL", "")
AUDIO_TRANSCRIPTION_TOKEN = os.getenv("CHATBOT_AUDIO_TRANSCRIPTION_TOKEN", "")
# Obrigatório no Groq e em qualquer API compatível com a da OpenAI. Default
# `whisper-large-v3` e não o `-turbo`: o turbo é destilado e perde justamente em
# língua que não é inglês, e aqui o bot **age** sobre o que ouviu — errar o que
# o cliente disse custa mais que a diferença de preço, que no volume do piloto é
# de centavos por dia. Trocar é só esta variável.
AUDIO_TRANSCRIPTION_MODEL = os.getenv(
    "CHATBOT_AUDIO_TRANSCRIPTION_MODEL", "whisper-large-v3"
)
AUDIO_MAX_BYTES = int(os.getenv("CHATBOT_AUDIO_MAX_BYTES", str(8 * 1024 * 1024)))
AUDIO_MAX_DURATION_SECONDS = int(os.getenv("CHATBOT_AUDIO_MAX_DURATION_SECONDS", "180"))
AUDIO_DOWNLOAD_TIMEOUT = float(os.getenv("CHATBOT_AUDIO_DOWNLOAD_TIMEOUT", "10"))
AUDIO_TRANSCRIPTION_TIMEOUT = float(
    os.getenv("CHATBOT_AUDIO_TRANSCRIPTION_TIMEOUT", "15")
)
AUDIO_FALLBACK_TEXT = os.getenv(
    "CHATBOT_AUDIO_FALLBACK_TEXT",
    "Não consegui entender o áudio. Pode me enviar por texto?",
)[:160]

# Gate de confiança pós-transcrição (§5.10). Os tetos são os do próprio Whisper —
# são os mesmos que o decoder usa para descartar um segmento — e não se inventa
# outro valor aqui. Acima/abaixo deles a transcrição é evidência de alucinação e
# o áudio cai no fallback "manda por texto". Sem sinal no payload, o texto passa.
AUDIO_NO_SPEECH_PROB_MAX = float(os.getenv("CHATBOT_AUDIO_NO_SPEECH_PROB_MAX", "0.6"))
AUDIO_AVG_LOGPROB_MIN = float(os.getenv("CHATBOT_AUDIO_AVG_LOGPROB_MIN", "-1.0"))
AUDIO_COMPRESSION_RATIO_MAX = float(
    os.getenv("CHATBOT_AUDIO_COMPRESSION_RATIO_MAX", "2.4")
)

# Cloud API (Modo 2). Token de System User — nunca o temporário de 24 h do painel.
# O token é do Revy (um app na Meta, spec §6.2): global, aqui, nunca no banco.
# Já número e template são POR LOJA e moram em ``whatsapp_canais``; as duas
# variáveis abaixo são só o fallback da loja piloto, que não tem canal Cloud
# cadastrado. Quem resolve é ``app.cloud_canal`` — não leia daqui no outbound.
GRAPH_BASE_URL = os.getenv("CHATBOT_GRAPH_BASE_URL", "https://graph.facebook.com/v21.0")
GRAPH_TOKEN = os.getenv("CHATBOT_GRAPH_TOKEN", "")
GRAPH_PHONE_NUMBER_ID = os.getenv("CHATBOT_GRAPH_PHONE_NUMBER_ID", "")
GRAPH_TEMPLATE_OFERTA = os.getenv("CHATBOT_GRAPH_TEMPLATE_OFERTA", "chama_vendedor")

# Webhook da Meta (Modo 2). App Secret assina o corpo; verify token fecha o GET.
META_APP_SECRET = os.getenv("CHATBOT_META_APP_SECRET", "")
META_VERIFY_TOKEN = os.getenv("CHATBOT_META_VERIFY_TOKEN", "")

# Imagem de veículo recebida de número autorizado. O binário só transita pela
# API e é enviado ao Estoque; não é persistido no Chatbot/n8n.
IMAGE_EVOLUTION_URL = os.getenv(
    "CHATBOT_IMAGE_EVOLUTION_URL", AUDIO_EVOLUTION_URL
)
IMAGE_EVOLUTION_API_KEY = os.getenv(
    "CHATBOT_IMAGE_EVOLUTION_API_KEY", AUDIO_EVOLUTION_API_KEY
)
IMAGE_MAX_BYTES = int(os.getenv("CHATBOT_IMAGE_MAX_BYTES", str(10 * 1024 * 1024)))
IMAGE_DOWNLOAD_TIMEOUT = float(os.getenv("CHATBOT_IMAGE_DOWNLOAD_TIMEOUT", "10"))
IMAGE_SESSION_TTL_SECONDS = max(
    0, int(os.getenv("CHATBOT_IMAGE_SESSION_TTL_SECONDS", "600"))
)

# Evolution genérica (envio de texto humano / atendimento). Preferir estas;
# se vazias, reutiliza IMAGE_* (mesmo host/apikey já usados em lab/prod).
EVOLUTION_URL = (
    os.getenv("CHATBOT_EVOLUTION_URL", "").strip() or IMAGE_EVOLUTION_URL
)
EVOLUTION_API_KEY = (
    os.getenv("CHATBOT_EVOLUTION_API_KEY", "").strip() or IMAGE_EVOLUTION_API_KEY
)
EVOLUTION_SEND_TIMEOUT = float(os.getenv("CHATBOT_EVOLUTION_SEND_TIMEOUT", "10"))
CADASTRO_SESSION_TTL_SECONDS = max(
    0, int(os.getenv("CHATBOT_CADASTRO_SESSION_TTL_SECONDS", "1800"))
)

# Base do Portal/Loja para links operacionais (alerta de simulação no grupo).
PORTAL_BASE_URL = os.getenv(
    "CHATBOT_PORTAL_BASE_URL", "https://app2037.fly.dev"
).rstrip("/")

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
ESTOQUE_MEDIA_ALLOWED_HOSTS = tuple(
    host.strip().lower().rstrip(".")
    for host in os.getenv("ESTOQUE_MEDIA_ALLOWED_HOSTS", "").split(",")
    if host.strip()
)

# Prazos padrão multi-opção quando o cliente não escolhe um único prazo (CRM WhatsApp).
PRAZOS_PADRAO_MESES: list[int] = [24, 36, 48, 60]

# Rollout do Modo 2 (central Cloud API). Default OFF: invariante do projeto.
MODO2_ENABLED = os.getenv("CHATBOT_WHATSAPP_MODO2_ENABLED", "").lower() in {"1", "true", "yes"}

# Multi-WhatsApp: vários canais por loja. Default off — só 1 canal legado permitido.
MULTI_WHATSAPP_ENABLED = os.getenv("MULTI_WHATSAPP_ENABLED", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Provider de conexão de canal: stub (default, sem rede) | evolution (real).
WHATSAPP_PROVIDER = os.getenv("CHATBOT_WHATSAPP_PROVIDER", "stub").strip().lower()
# URL do webhook n8n gravada em instância nova. Um workflow serve N instâncias.
EVOLUTION_WEBHOOK_URL = os.getenv("CHATBOT_EVOLUTION_WEBHOOK_URL", "").strip()

# Preview da config do agente: webhook do `workflow-preview.json`, no mesmo
# n8n2037. Vazio = a rota responde 503 e a tela some com o botão Testar — é
# default seguro, não bug: sem o workflow importado não há o que chamar.
AGENTE_PREVIEW_URL = os.getenv("CHATBOT_AGENTE_PREVIEW_URL", "").strip()
# Generoso de propósito: o agente pode encadear consulta ao estoque e ainda
# pensar. Curto demais mostra "o preview não respondeu" para um agente que
# respondeu — e o lojista conclui que a configuração dele está errada.
AGENTE_PREVIEW_TIMEOUT = float(os.getenv("CHATBOT_AGENTE_PREVIEW_TIMEOUT", "45"))
