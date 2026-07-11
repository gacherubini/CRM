# Chatbot Standalone — subir e ir ao ar

Pacote completo do Chatbot: `chatbot-api` + **Estoque Lite** + Postgres + Redis + **n8n** +
**Evolution API**. Sobe tudo com um comando; a conversa é montada no n8n usando **Gemini** (grátis).

## Pré-requisitos

- Docker Desktop ligado.
- Um **número de WhatsApp dedicado** (um chip só pro bot).
- Uma **chave do Gemini** (grátis em https://aistudio.google.com → *Get API key*).

## 1. Subir a infra

```bash
cd deploy/chatbot-standalone
cp .env.example .env
# edite .env: defina EVOLUTION_API_KEY e N8N_ENCRYPTION_KEY (invente strings)
docker compose up -d --build
```

Portas: chatbot-api `:8000`, estoque `:8100`, Evolution `:8080`, n8n `:5678`.

## 2. Criar a loja (nos dois serviços, com o MESMO slug)

```bash
# no Estoque (retorna TOKEN do estoque)
docker compose exec estoque-api python -m app.cli criar-loja \
  --nome "Moto Center" --slug moto-center --whatsapp 5511999999999

# no Chatbot (retorna TOKEN do chatbot; instance = nome da instância Evolution)
docker compose exec chatbot-api python -m app.cli criar-loja \
  --nome "Moto Center" --slug moto-center --instance loja1 --whatsapp 5511999999999
```

Cadastre alguns veículos no Estoque (use o TOKEN do estoque) e publique — ver
`deploy/estoque-standalone/README.md`.

## 3. Conectar o WhatsApp (Evolution)

```bash
# criar a instância (mesmo nome usado em --instance acima: loja1)
curl -s -X POST http://localhost:8080/instance/create \
  -H "apikey: SUA_EVOLUTION_API_KEY" -H "Content-Type: application/json" \
  -d '{"instanceName":"loja1","integration":"WHATSAPP-BAILEYS","qrcode":true}'
```

Abra o **Evolution Manager** em `http://localhost:8080/manager` (login com a API key),
escaneie o **QR** com o WhatsApp do número dedicado. Status deve virar `open`.

## 4. Montar o fluxo no n8n (`http://localhost:5678`)

1. Credencial **Google Gemini** → cole sua chave do AI Studio.
2. Webhook (POST, path `whatsapp`) → registre na Evolution:
   ```bash
   curl -s -X POST http://localhost:8080/webhook/set/loja1 \
     -H "apikey: SUA_EVOLUTION_API_KEY" -H "Content-Type: application/json" \
     -d '{"webhook":{"enabled":true,"url":"http://n8n:5678/webhook/whatsapp","events":["MESSAGES_UPSERT"]}}'
   ```
3. Nó **AI Agent** com **Google Gemini Chat Model** e as ferramentas (HTTP Request Tool)
   apontando para o `chatbot-api` (`http://chatbot-api:8000`), todas com header
   `Authorization: Bearer TOKEN_DO_CHATBOT`:
   - `consultar_estoque` → `GET /v1/estoque/buscar?termo={termo}`
   - `registrar_consentimento` → `POST /v1/consentimentos`
   - `registrar_lead` → `POST /v1/leads`
   - `simular` → `POST /v1/simular` (só na edição Financiamento)
   - gate de handoff → `GET /v1/conversas/{telefone}/estado` antes de responder
4. Responder no WhatsApp: nó HTTP Request → `POST http://evolution:8080/message/sendText/loja1`.

O system prompt deve exigir **consentimento antes de dados pessoais**, e nunca inventar
veículo/parcela (sempre usar as ferramentas). O workflow pronto será versionado em `n8n/`.

## Edições

- **Atendimento:** `SIMULATION_PROVIDER=none` (bot qualifica e encaminha, sem simular).
- **Financiamento (demo):** `SIMULATION_PROVIDER=mock` (padrão) — simula com taxas fictícias.
- **Financiamento (real):** `SIMULATION_PROVIDER=http` + `MOTOR_URL` do Motor de Simulação.

## Operação

- **Logs:** `docker compose logs -f chatbot-api`
- **Leads (CSV):** `curl -H "Authorization: Bearer TOKEN" http://localhost:8000/v1/leads.csv`
- **Parar:** `docker compose down` (dados nos volumes).
