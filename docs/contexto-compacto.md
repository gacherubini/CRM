# Contexto compacto para continuidade

Atualizado em 2026-07-12 após E2E WhatsApp real (estoque + lead + simulação mock via Motor HTTP)
e estabilização do workflow n8n. Leia este arquivo primeiro e depois `docs/handoff-contexto.md`.

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Preserve arquivos rastreados e novos; não use reset/checkout destrutivo.
- Não leia/imprima `.env`, tokens, chaves Gemini/Evolution/Motor ou senhas.
- Estoque é a fonte de verdade. Integrações só por HTTP entre produtos.
- Ordem válida: #0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6. Ignore `LEGADO`.
- Simulação com nomes de banco ainda é **mock** (taxas fictícias no Motor). Não é cotação real.

## Checkpoint verificado (2026-07-12)

### Motor #1A

- API async, auth/tenancy, lease/worker, cifra de payload, métricas.
- Migrations até `0005_job_lease`.
- Drivers atuais: **mock** (Pan/BV/Bradesco/Santander/Fontcred com taxas FICTÍCIAS).
- Deploy: `deploy/motor-standalone` porta host `8000`.

### Chatbot #2A + n8n + Evolution

- `SIMULATION_PROVIDER=http` no compose com `MOTOR_URL` / `MOTOR_TOKEN` (só no `.env` ignorado).
- `HttpSimulationProvider`: Bearer, 202 + polling, fallback seguro.
- E2E WhatsApp **validado em runtime**:
  - Evolution `loja1` open
  - Workflow n8n `WhatsApp IA - Somente Nao Salvos` (ID `wAiNaoSalvos0001`) ativo
  - estoque real (Onix) → lead → simulação mock → resposta no WhatsApp
- Workflow versionado: `n8n/workflow-ai-nao-salvos.json` (placeholders; **sem** tokens reais).
- Runtime n8n pode ter tokens injetados no SQLite do volume — não exportar isso para o git.
- Gate “somente não salvos” no runtime pode estar em modo TEMP (atende todos) — reverter para
  `isSaved === false` antes de produção.
- Tools no runtime: **Code Tool** (`helpers.httpRequest`), não `toolHttpRequest` (bug supplyData/execute no n8n 2.29).
- Modelo recomendado: `gemini-3.1-flash-lite` (3.5-flash deu 503 sob carga).

### Estoque #4A

- Tenancy/RBAC, CRUD, fotos, CSV, API pública, outbox HMAC, admin parcial.
- No compose do chatbot: porta `8100`.

### Portal

- `portal-gestao/`: shell Motora dark-tech, dashboard + estoque reais; leads + conversas/handoff
  agora reais (Plano #3A.1 Tasks 10,11,12; branch `feat/dashboard-leads-conversas`, verificado ao vivo).
  Simulações/equipe/config ainda placeholder. Precisa `CHATBOT_API_TOKEN` no `.env` do portal.

## Próxima sequência recomendada

1. Reverter gate n8n para só `isSaved === false` quando Evolution estiver confiável.
2. Endurecer webhook Evolution (auth, dedupe DB, corrida `origem_bot`).
3. LGPD: sanitizar/cifrar CPF em mensagens; exclusão de dados.
4. Fechar E2E Motor Task 10 (kill worker, restore) e outbox Estoque contra receptor real.
5. Portal: leads + conversas + handoff (#3A.1).
6. Drivers bancários reais (ainda em hold) quando sair do mock.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
git status --short
```

Estado estimado: backend ~80% para demo; produção/revenda ainda não.
Simulação = mock até plugar driver real.
