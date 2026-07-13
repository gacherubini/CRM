# Handoff técnico — suíte automotiva

> Checkpoint: **2026-07-13**. Estado atual (não diário de sessão).
> Confirme containers/`.env`/n8n antes de editar. Testes unitários ≠ E2E WhatsApp.
> Leia primeiro: `docs/contexto-compacto.md`. Planos válidos: `docs/plans/README.md`.

## Estado em uma frase

Demo forte com Motor, Estoque, Chatbot, Portal e Catálogo integrados por HTTP (~**80%** MVP,
~**65%** produção/revenda). Simulação ainda **mock**. Bot WhatsApp **off de propósito**.
Funil Catálogo→Chatbot→Portal com wiring de deploy e E2E da entrega do outbox; falta validar em
ambiente com containers reais.

## Verificação

| Produto | Testes | Porta host típica |
|---|---:|---|
| Motor | 69 | `:8000` |
| Chatbot | 62 | `:8001` |
| Estoque | 65 | `:8100` |
| Catálogo | 19 | `:8200` |
| Portal | 90 | `:9000` |
| **Total** | **305** | Evolution `:8080`, n8n `:5678` |

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q
```

## Por produto (feito / falta)

### Motor (`motor-simulacao/`, `deploy/motor-standalone`)

- **Feito:** jobs async, worker/lease, auth+tenancy, cifra, CLI, mock de 5 bancos, compose,
  **Task 11** (credenciais cifradas por cliente+provedor, endpoints admin listar/upsert/testar-login,
  GET mascarado, auditoria, métrica de falha de auth, rotação sem restart — `testar-login` é
  placeholder até haver driver real).
- **Falta:** **Task 10** revenda; **Task 12** 1º driver real (híbrido API/Playwright — vai chamar
  `registrar_sucesso/falha_login` com desfecho real). UI de credenciais no Portal (#3A Task 9A) — agora
  desbloqueada pela API do Motor. Agregador opcional depois.

### Chatbot (`chatbot-api/`, `deploy/chatbot-standalone`)

- **Feito:** tenancy, leads, conversas/mensagens, handoff, CPF mascarado no texto, webhook auth
  opt-in + dedupe `provider_message_id`, `HttpSimulationProvider`, atribuição catálogo
  `POST /v1/integracoes/catalogo/interesses` + migration `0004`, sem trava de consentimento (decisão),
  E2E de entrega do outbox catálogo→chatbot (`tests/test_e2e_outbox_delivery.py`: headers
  Bearer/Idempotency-Key/X-Event-Type + retry/idempotência).
- **Falta:** go-live (`docs/go-live-chatbot.md`); prompt n8n ainda fala de consentimento; mojibake na
  ingestão; webhooks de domínio; readiness real; LGPD completa (exclusão).

### Estoque (`estoque-api/`)

- **Feito:** CRUD, tenancy/RBAC, API pública, outbox HMAC, admin parcial, CSV/fotos, **placa**
  normalizada (Mercosul/antigo) + unicidade `(loja_id, placa)` + `GET /v1/veiculos/por-placa/{placa}`
  privado + filtro `placa` + coluna no CSV (migration `0005`).
- **Falta:** campo **placa** na tela admin HTMX (só na API hoje); E2E outbox+receptor; restore/revenda;
  fechar admin. *(Wart: migrations `0002/0003` não rodam em SQLite — `ALTER`/unique constraint; prod é
  Postgres, testes usam `create_all`.)*

### Portal (`portal-gestao/`)

- **Feito:** auth/RBAC, estoque via API, leads, conversas+handoff, simulação manual (BFF),
  **simulação liberada ao `vendedor`** sem custo/lucro/tokens (whitelist `simulacao_sem_dados_sensiveis`,
  Task 13), vendas/financeiro (#3B), metas de loja CRUD, `/app/vendedor`, funil em `/app/financeiro`,
  atribuições de atendimento (migration `0004`).
- **Falta:** Task **9A** UI de credenciais das financeiras (Motor Task 11 já entrega a API); metas
  individuais UI; campanhas; equipe/config; CSV reconciliação; Playwright E2E.

### Catálogo (`catalogo-publico/`, `deploy/catalogo-conectado`)

- **Feito:** vitrine/detalhe, CTA `wa.me` + ref `CAT-*`, eventos/UTM SQLite, outbox Bearer com
  retry/idempotência, Docker não-root, **wiring do funil no deploy** (`CATALOGO_EVENTS_URL/TOKEN` no
  `deploy/catalogo-conectado` + `.env.example`/README, desligado por padrão) + E2E de entrega.
- **Falta:** validar o funil em ambiente com containers reais (token de serviço + slug batendo);
  SEO/cache/tema/standalone (resto do #5A).

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Integrações **só HTTP**. Estoque = fonte de verdade dos veículos. Tokens só no servidor.
- **Nunca** ler/versionar `.env`, tokens Motor/Chatbot, Evolution, Gemini, `MOTOR_ENCRYPTION_KEY`.
- n8n versionado: placeholders (`__INSTANCE__`, `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`).
  Runtime no volume Docker pode ter segredos — não exportar cego para o git.
- Ordem dos planos: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6`.
  Ignore `docs/plans/_archive/` (LEGADO).
- Parcelas com nomes de banco = **sempre mock** até existir driver `real: true`.

## Próximos passos (ordem)

1. Validar o funil do catálogo em containers reais (token de serviço + slug) — wiring/E2E já prontos.
2. Chatbot: lookup **por placa** (`HttpInventoryProvider`) + payload de simulação WhatsApp
   (telefone, sem renda/prazo único) — #2A, agora que o Estoque expõe `por-placa`.
3. Portal: **Task 9A** UI de credenciais das financeiras — desbloqueada pela API do Motor (Task 11).
   #3B residual (metas individuais, campanhas, equipe/config); Playwright E2E.
4. #5A residual (tema, SEO, rate limit, standalone).
5. Prompt n8n + mojibake; go-live do bot quando o dono decidir (`docs/go-live-chatbot.md`).
6. Motor **Task 10** (revenda) → **Task 12** (1º driver real híbrido API + Playwright; 1 banco piloto;
   liga em `registrar_sucesso/falha_login`). Agregador opcional. Não reintroduzir mock como “banco real”.
7. Estoque: campo **placa** na tela admin HTMX (hoje só na API).

## Avisos operacionais

1. E2E “sumiu”? Checar Evolution `open`, n8n **Published**, placeholders não voltaram,
   `SIMULATION_PROVIDER=http`, token Motor válido.
2. Não usar `printenv` em containers com tokens.
3. Scripts PowerShell que editam Code nodes do n8n: preservar `$('NomeDoNo')`.
4. Import n8n desativa workflow → precisa `publish:workflow` + restart.
5. Senha dev conhecida no handoff antigo: não documentar senhas aqui; usar seed/local.
6. `chatbot-api/` tem dirs órfãos `test-tmp-run*` (permissão negada) que quebram `pytest -q` na
   coleção — rode `pytest tests/ -q` ou remova os dirs (`Remove-Item -Recurse -Force`).
