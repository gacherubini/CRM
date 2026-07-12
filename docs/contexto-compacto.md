# Contexto compacto para continuidade

Atualizado em 2026-07-12 após entrega do primeiro incremento do CRM financeiro #3B e do
Catálogo Público #5A. Leia este arquivo primeiro e depois `docs/handoff-contexto.md`.

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

- `portal-gestao/`: dashboard, estoque, leads, conversas/handoff e simulação manual reais.
- #3B: vendas e dashboard financeiro; metas de loja agora têm CRUD (quantidade, faturamento e
  lucro), RBAC/tenancy, validação de período/alvo/sobreposição e migration `0003_adiciona_meta_ativa`.
- Venda sem custo não gera mais lucro fictício: dashboard sinaliza dados incompletos e suspende o
  atingimento da meta de lucro. Suíte do Portal: **72 testes**.
- Equipe/config ainda placeholder. Precisa `CHATBOT_API_TOKEN` no `.env` local do portal.

### Catálogo Público #5A

- Primeiro incremento vertical entregue em `catalogo-publico/` (FastAPI + Jinja + CSS local).
- Vitrine pública, filtros/paginação, detalhe/galeria, estados 404/422/503 e CTA seguro para WhatsApp.
- Consome somente a API pública HTTP do Estoque; não compartilha banco/models.
- Eventos de interesse + UTMs em SQLite próprio; redirect limitado a `https://wa.me`.
- Deploy conectado em `deploy/catalogo-conectado`, Docker não-root, healthcheck e volume persistente.
- **15 testes**; validado ao vivo em `http://localhost:8200/l/demo` contra o Estoque real.

## Próxima sequência recomendada

1. Funil comercial ponta a ponta: `catalog.interest_clicked` → lead/origem/UTM → atribuição → venda.
2. #3B: dashboard do vendedor, funil/conversão e campanhas.
3. #5A: outbox/webhook de interesse, exportação, tema por loja, SEO/cache e standalone.
4. Ajustar prompt n8n (remover consentimento antigo) e corrigir mojibake na entrada.
5. Fechar E2E Motor Task 10, Estoque outbox/restore e Playwright do Portal.
6. Drivers bancários reais (ainda em hold) quando sair do mock.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q
git status --short
```

Estado estimado: suíte ~72% para MVP demonstrável e ~58% para produção/revenda.
Simulação = mock até plugar driver real.
