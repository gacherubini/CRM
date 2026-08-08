# Chatbot Standalone — subir e ir ao ar

Pacote revendível: `chatbot-api` + **Estoque Lite** + Postgres + Redis + **n8n** +
**Evolution API**. Funciona sem Portal e sem Catálogo Público.

**Pré-requisitos:** Docker Desktop, um número de WhatsApp dedicado, uma chave do Gemini
(grátis em https://aistudio.google.com → *Get API key*).

## 1. Subir

```bash
cd deploy/chatbot-standalone
cp .env.example .env
# defina EVOLUTION_API_KEY e N8N_ENCRYPTION_KEY (strings inventadas)
docker compose up -d --build
```

Portas: chatbot-api `:8001`, estoque `:8100`, Evolution `:8080`, n8n `:5678`.

## 2. Criar a loja nos dois serviços (mesmo slug)

```bash
docker compose exec estoque-api python -m app.cli criar-loja \
  --nome "Moto Center" --slug moto-center --whatsapp 5511999999999

docker compose exec chatbot-api python -m app.cli criar-loja \
  --nome "Moto Center" --slug moto-center --instance loja1 --whatsapp 5511999999999
```

Cada comando imprime um TOKEN. Cadastre veículos no Estoque e publique — ver
[`../estoque-standalone/README.md`](../estoque-standalone/README.md).

## 3. Conectar o WhatsApp

```bash
curl -s -X POST http://localhost:8080/instance/create \
  -H "apikey: SUA_EVOLUTION_API_KEY" -H "Content-Type: application/json" \
  -d '{"instanceName":"loja1","integration":"WHATSAPP-BAILEYS","qrcode":true}'
```

Abra o Evolution Manager em `http://localhost:8080/manager` (login com a API key) e
escaneie o QR com o número dedicado. Status deve virar `open`.

## 4. Importar o fluxo no n8n (`http://localhost:5678`)

Template versionado: `n8n/workflow-ai-nao-salvos.json`. Substitua `__EVOLUTION_KEY__`,
`__CHATBOT_TOKEN__` e `__CHATBOT_WEBHOOK_TOKEN__` — este último tem de ter **exatamente** o
mesmo valor de `CHATBOT_WEBHOOK_TOKEN` no `.env` (autentica entrada e registro da saída).

A instance **não** é fixa no JSON: cada evento traz `body.instance` e o workflow usa esse
valor (multi-WhatsApp com um único workflow).

Selecione a credencial no nó **Google Gemini Chat Model**. As tools do AI Agent apontam
para `http://chatbot-api:8000` com `Authorization: Bearer TOKEN_DO_CHATBOT`:

| Tool | Endpoint |
|---|---|
| `consultar_estoque` | `GET /v1/estoque/buscar?termo={termo}` |
| `enviar_foto_veiculo` | resolve a capa pelo ID e envia mídia pela Evolution |
| `registrar_consentimento` | `POST /v1/consentimentos` |
| `registrar_lead` | `POST /v1/leads` |
| `simular` | `POST /v1/simulacoes/solicitar` — descarta a resposta técnica e pausa o bot |
| `solicitar_handoff` | `PATCH /v1/conversas/{telefone}/estado` |
| `adicionar_veiculo` | `POST /v1/operacao/veiculos` (só números autorizados) |

Publique o workflow e registre o webhook na Evolution:

```bash
curl -s -X POST http://localhost:8080/webhook/set/loja1 \
  -H "apikey: SUA_EVOLUTION_API_KEY" -H "Content-Type: application/json" \
  -d '{"webhook":{"enabled":true,"url":"http://n8n:5678/webhook/whatsapp-ai","events":["MESSAGES_UPSERT"]}}'
```

## Armadilhas

- **Não use o sufixo `@lid` para decidir se o contato é salvo.** A Evolution pode ter chats
  salvos com `@lid`. O campo canônico é `isSaved` de `findChats`, consumido por
  `POST /v1/operacao/roteamento` — não um gate solto no n8n.
- **O cliente nunca recebe parcela, taxa ou banco do bot.** Depois de solicitar a
  simulação, a conversa é pausada e o resultado é entregue por um vendedor.
- **O system prompt não pode inventar veículo nem parcela.**
- **Não desligue o rate limit do webhook em produção** (`CHATBOT_WEBHOOK_RATE_LIMIT_*`);
  o corpo é limitado a 32 KiB e payload inválido não é ecoado.
- **O LLM não escolhe identidade autorizada.** `telefone_solicitante` e `Idempotency-Key`
  são montados pelo Code Tool a partir do webhook real.
- **A credencial do transcritor fica só no Chatbot**, nunca no workflow.

Roteamento (3 casos) e fail-closed: ver [`../../README.md`](../../README.md).

## Cadastro de veículo por WhatsApp (E5)

Caminho de estoque **sem Portal**: a equipe manda os dados no WhatsApp, o n8n extrai os
campos e chama a Chatbot API, que grava no Estoque e já publica.

Env da `chatbot-api`: `ESTOQUE_PUBLIC_URL` (leitura), `ESTOQUE_API_URL` +
`ESTOQUE_API_TOKEN` (escrita), `ESTOQUE_REQUEST_TIMEOUT` (8s),
`CHATBOT_IMAGE_SESSION_TTL_SECONDS` (600s, janela de fotos em lote).

Autorizar telefones da equipe:

```bash
docker compose exec chatbot-api python -m app.cli autorizar-numero \
  --slug moto-center --telefone 5511999999999 --papel dono
```

Requisição da tool:

```http
POST http://chatbot-api:8000/v1/operacao/veiculos
Authorization: Bearer TOKEN_DO_CHATBOT
Idempotency-Key: {{ providerMessageId_do_webhook }}

{"tipo":"moto","marca":"Honda","modelo":"CG 160","ano_modelo":2023,
 "preco":16000,"km":12000,"placa":"ABC1D23"}
```

Erros legíveis para o bot falar: `403` não autorizado · `422` faltou valor / placa
inválida / faltou marca · `503` escrita no Estoque não configurada.

**Fotos:** após o cadastro em texto abre uma sessão de 10 min para enviar várias fotos sem
repetir a placa. Para veículo já existente, a primeira foto usa a placa na legenda. O
workflow valida o telefone, baixa a imagem server-side, faz upload binário no Estoque e
confirma quando Estoque+Catálogo estiverem atualizados. Aceita JPEG/PNG/WebP até 10 MiB;
reentrega da mesma mensagem não duplica. Configure:

```env
ESTOQUE_MEDIA_PUBLIC_BASE_URL=https://estoque.seudominio.com/public/v1/media
ESTOQUE_MEDIA_ALLOWED_HOSTS=estoque.seudominio.com
```

Essa URL precisa ser HTTPS e acessível pelo navegador **e** pela Evolution. O n8n/LLM nunca
recebe base64 nem escolhe path/URL.

## Áudio recebido

O ramo `E audio1` manda só instância, ID da mensagem, MIME e duração. A API baixa o
conteúdo pela Evolution com `apikey` server-side, aceita só MIME de áudio, limita a
8 MiB/180 s e apaga o diretório temporário a cada tentativa. n8n e banco não guardam o
binário. Sem provider (`CHATBOT_AUDIO_TRANSCRIPTION_PROVIDER=none`) ou em qualquer falha, o
cliente recebe um pedido curto para mandar por texto.

Transcritor real: `CHATBOT_AUDIO_TRANSCRIPTION_PROVIDER=http` + URL e token. Contrato
`multipart/form-data`, campo `file` + `language=pt-BR`, resposta JSON com `text` ou `texto`.

## Edições e operação

| Edição | Config |
|---|---|
| Atendimento (sem simular) | `SIMULATION_PROVIDER=none` |
| Financiamento demo | `SIMULATION_PROVIDER=mock` (padrão) |
| Financiamento real | `SIMULATION_PROVIDER=http` + `MOTOR_URL` |

```bash
docker compose logs -f chatbot-api
curl -H "Authorization: Bearer TOKEN" http://localhost:8001/v1/leads.csv
docker compose down     # dados ficam nos volumes
```
