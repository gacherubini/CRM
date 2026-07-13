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

Portas: chatbot-api `:8001`, estoque `:8100`, Evolution `:8080`, n8n `:5678`.

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

## 4. Importar/configurar o fluxo no n8n (`http://localhost:5678`)

O template versionado é `n8n/workflow-ai-nao-salvos.json`. Ele aplica, nesta ordem:

1. ignora grupos/status e mensagens sem texto;
2. registra/deduplica a mensagem na Chatbot API;
3. respeita `bot_ativo=false` (handoff);
4. consulta `POST /chat/findChats/{instance}` na Evolution;
5. chama a IA somente quando `isSaved === false`;
6. registra a saída do bot para diferenciar respostas automáticas das manuais.

1. Importe o workflow e substitua `__INSTANCE__`, `__EVOLUTION_KEY__` e `__CHATBOT_TOKEN__`.
2. Selecione a credencial no nó **Google Gemini Chat Model**. As ferramentas
   HTTP do AI Agent apontam para a `chatbot-api` (`http://chatbot-api:8000`) com header
   `Authorization: Bearer TOKEN_DO_CHATBOT`:
   - `consultar_estoque` → `GET /v1/estoque/buscar?termo={termo}`
   - `registrar_consentimento` → `POST /v1/consentimentos`
   - `registrar_lead` → `POST /v1/leads`
   - `simular` → `POST /v1/simular` (só na edição Financiamento)
   - `solicitar_handoff` → `PATCH /v1/conversas/{telefone}/estado`
   - `adicionar_veiculo` → `POST /v1/operacao/veiculos` (só números autorizados; ver E5 abaixo)
3. Publique o workflow e registre o novo webhook na Evolution:
   ```bash
   curl -s -X POST http://localhost:8080/webhook/set/loja1 \
     -H "apikey: SUA_EVOLUTION_API_KEY" -H "Content-Type: application/json" \
     -d '{"webhook":{"enabled":true,"url":"http://n8n:5678/webhook/whatsapp-ai","events":["MESSAGES_UPSERT"]}}'
   ```

Não use o sufixo `@lid` para decidir se o contato é salvo: a Evolution pode ter chats salvos com
`@lid`. O campo canônico usado pelo gate é `isSaved` retornado por `findChats`.

O system prompt deve exigir **consentimento antes de dados pessoais**, e nunca inventar
veículo/parcela (sempre usar as ferramentas). O workflow pronto será versionado em `n8n/`.

## E5 — Cadastro de veículo via WhatsApp (Chatbot-only)

Caminho canônico de estoque **sem Portal**: o dono/vendedor manda os dados no WhatsApp;
o n8n extrai os campos e chama a Chatbot API, que grava no **Estoque** (HTTP privado).

### Env vars (chatbot-api)

| Variável | Uso |
|----------|-----|
| `ESTOQUE_PUBLIC_URL` | Leitura da vitrine (`GET /public/v1/...`) |
| `ESTOQUE_API_URL` | Base da API privada do Estoque (ex.: `http://estoque-api:8000`) |
| `ESTOQUE_API_TOKEN` | Token de serviço **da loja no estoque-api** (escrita) |
| `ESTOQUE_REQUEST_TIMEOUT` | Timeout HTTP (default 8s) |

### 1. Autorizar telefones da equipe

```bash
# CLI
docker compose exec chatbot-api python -m app.cli autorizar-numero \
  --slug moto-center --telefone 5511999999999 --papel dono

# ou API (token do chatbot)
curl -s -X POST http://localhost:8001/v1/operacao/numeros-autorizados \
  -H "Authorization: Bearer TOKEN_DO_CHATBOT" -H "Content-Type: application/json" \
  -d '{"telefone":"5511999999999","papel":"dono"}'
```

### 2. Ferramenta n8n `adicionar_veiculo` (schema)

```http
POST http://chatbot-api:8000/v1/operacao/veiculos
Authorization: Bearer TOKEN_DO_CHATBOT
Idempotency-Key: {{ $json.messageId || uuid }}
Content-Type: application/json

{
  "telefone_solicitante": "5511999999999",
  "tipo": "moto",
  "marca": "Honda",
  "modelo": "CG 160",
  "ano_modelo": 2023,
  "preco": 16000,
  "km": 12000,
  "placa": "ABC1D23",
  "foto_url": null
}
```

**Sucesso (201):**
```json
{
  "ok": true,
  "mensagem": "Veículo cadastrado: Honda CG 160 2023 — R$ 16.000,00 — placa ABC1D23",
  "veiculo": {
    "id": "...", "tipo": "moto", "marca": "Honda", "modelo": "CG 160",
    "ano_modelo": 2023, "preco": 16000.0, "km": 12000, "placa": "ABC1D23",
    "status": "disponivel", "publicado": false, "foto_url": null
  },
  "solicitante": "5511999999999"
}
```

**Erros legíveis (para o bot falar no WhatsApp):**
- `403` `{"detail":"não autorizado"}` — cliente comum tentou cadastrar
- `422` `{"detail":"faltou valor"}` / `"placa inválida ..."` / `"faltou marca"`
- `503` escrita no Estoque não configurada (`ESTOQUE_API_URL`/`TOKEN`)

> Fase 1: só texto + `foto_url` opcional. Upload de mídia WhatsApp = Fase 2 (E6).
> A extração LLM dos campos fica no n8n; a API só recebe JSON estruturado.

## Edições

- **Atendimento:** `SIMULATION_PROVIDER=none` (bot qualifica e encaminha, sem simular).
- **Financiamento (demo):** `SIMULATION_PROVIDER=mock` (padrão) — simula com taxas fictícias.
- **Financiamento (real):** `SIMULATION_PROVIDER=http` + `MOTOR_URL` do Motor de Simulação.

## Operação

- **Logs:** `docker compose logs -f chatbot-api`
- **Leads (CSV):** `curl -H "Authorization: Bearer TOKEN" http://localhost:8001/v1/leads.csv`
- **Parar:** `docker compose down` (dados nos volumes).
