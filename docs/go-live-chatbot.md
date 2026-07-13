# Runbook de go-live do Chatbot WhatsApp

> Estado atual: **NÃO no ar** de propósito. Workflow `wAiNaoSalvos0001` **desativado**.
> Este documento é o checklist para ir ao ar quando você decidir. Nada aqui liga o bot
> sozinho — o passo final (ativar o workflow) é manual.

## 0. O que já está pronto (não precisa refazer)

- Gate "somente não salvos" **fail-closed** (`isSaved === false`) no runtime do n8n. ✅
- Chatbot: webhook com **auth opt-in** (`CHATBOT_WEBHOOK_TOKEN` + header `X-Webhook-Token`)
  e **dedupe no banco** (UNIQUE `mensagens(loja_id, provider_message_id)`, migration `0003`). ✅
- CPF **mascarado** no texto das mensagens (ingestão e saída). ✅
- Consentimento **não é exigido** (decisão de produto). ✅
- Endpoints de conversas/leads e Portal (Leads, Conversas+handoff, Simulação) prontos. ✅
- **E3 auto-pausa:** `from_me` do atendente → `bot_ativo=false` na conversa; saída do bot com
  `origem_bot=true` + mesmo `provider_message_id` não pausa (dedupe do eco Evolution). ✅

## 1. Subir o código novo nos containers

O código acima está commitado na branch `feat/dashboard-leads-conversas`. Os containers em
execução podem estar com imagem antiga. Antes de ir ao ar:

```powershell
git checkout feat/dashboard-leads-conversas   # ou após merge na main
docker compose -f deploy/chatbot-standalone/docker-compose.yml up -d --build chatbot-api
cd portal-gestao; docker compose up -d --build; cd ..
```

## 2. Segurança do canal (webhook)

1. Gerar um segredo forte:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Colocar em `deploy/chatbot-standalone/.env` (arquivo ignorado pelo git):
   ```
   CHATBOT_WEBHOOK_TOKEN=<segredo>
   ```
   e recriar o container: `docker compose -f deploy/chatbot-standalone/docker-compose.yml up -d chatbot-api`
3. No n8n, adicionar o header **`X-Webhook-Token: <segredo>`** nos **dois** nós httpRequest que
   chamam `POST /webhook/mensagem`:
   - `Registrar mensagem e ler handoff1` (mensagem que chega)
   - `Registrar saida do bot1` (resposta do bot)
   Depois: **Publish** o workflow + `docker restart chatbot-standalone-n8n-1`.
   > Enquanto `CHATBOT_WEBHOOK_TOKEN` estiver vazio, o webhook fica aberto (comportamento atual).
   > Definir o segredo SEM adicionar o header no n8n = bot para de registrar mensagens (401).
   > Faça os dois juntos.

## 3. Aplicar a migration do dedupe

```powershell
docker compose -f deploy/chatbot-standalone/docker-compose.yml exec chatbot-api alembic upgrade head
```

Se o banco já tiver mensagens com `(loja_id, provider_message_id)` repetido, a UNIQUE falha ao
aplicar — de-duplicar essas linhas antes (manter a mais antiga).

## 4. Limpeza e config do n8n

- **Apagar** a workflow duplicada `yBL8bLMDJW7IRxS0` na UI (deixar só `wAiNaoSalvos0001`).
- Conferir modelo Gemini em runtime: `models/gemini-3.1-flash-lite` (3.5-flash deu 503 sob carga).
- Conferir que os placeholders foram substituídos no runtime
  (`__INSTANCE__`, `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`) — nunca no JSON versionado.

## 5. Evolution

- Instância `loja1` = **open/connected** (checar no manager `:8080/manager`; reescanear QR se cair).
- **fromMe / auto-pausa (E3):** a instância precisa **emitir** eventos de mensagem com
  `key.fromMe=true` (mensagens enviadas pelo próprio número — app ou API). No webhook da
  Evolution → n8n, **não filtrar** `fromMe` no provedor; o nó `Extrair1` já encaminha
  `fromMe` com texto para `POST /webhook/mensagem` (`from_me`). Ack/status/reaction são
  ignorados (sem texto / evento `messages.update`).
- **Contrato n8n ↔ Chatbot API:**
  1. Inbound (cliente ou atendente): `{ instance, telefone, texto, provider_message_id, from_me }`
  2. Saída do bot (após `sendText`): mesmo webhook com
     `{ ..., from_me: true, origem_bot: true, provider_message_id: <id retornado pela Evolution> }`
     para o eco `fromMe` cair na dedupe e **não** pausar.
  3. Gate: se `fromMe` ou `duplicada` ou `bot_ativo !== true` → não chamar o agente.

## 6. Portal (se o dashboard for junto)

- `.env` do portal em produção com `CHATBOT_API_TOKEN` e `ESTOQUE_API_TOKEN` preenchidos.
- `PORTAL_SECURE_COOKIE=1` e `PORTAL_SESSION_SECRET` forte.
- Trocar a senha do usuário `dono@loja.local` (ou criar o dono real via
  `python -m app.cli criar-dono ...`).

## 7. Decisões de produto ANTES de ir ao ar

- **Simulação é mock**: parcelas Pan/BV/Bradesco/Santander/Fontcred têm taxas **fictícias**
  (`motor-simulacao/app/motor/mock.py`). Decidir:
  - (a) ir ao ar deixando claro no prompt do bot que é **estimativa/simulação**, não cotação oficial; ou
  - (b) esperar o driver bancário real (hoje em hold).
- CPF já é mascarado ao armazenar; sem coleta de consentimento (decisão tomada).

## 8. Validação (usar um número de teste antes de soltar geral)

1. Contato **SALVO** na sua agenda manda mensagem → bot **NÃO** responde.
2. Contato **NÃO salvo** manda mensagem → bot responde.
3. Fluxo completo: consulta estoque real → cria lead → simulação retorna parcelas.
4. Handoff auto-pausa (E3, standalone — sem Portal): você responde **1 msg pelo celular**
   (WhatsApp app) na conversa → bot **para** naquela conversa (`bot_ativo=false`).
   Mensagem do **próprio bot** não deve pausar. Reativar: Portal "Devolver ao bot" ou
   `PATCH /v1/conversas/{tel}/estado` com `{ "bot_ativo": true }`.
5. No Portal: a conversa aparece em `/app/conversas`, a thread abre, o handoff reflete.

## 9. Go-live

- Ativar o workflow `wAiNaoSalvos0001` (toggle **Active** na UI do n8n — aplica ao vivo).
- Acompanhar as primeiras conversas.

## 10. Rollback imediato (se precisar parar)

- Desativar o workflow `wAiNaoSalvos0001` (toggle Active off na UI). O bot para de responder na hora.
