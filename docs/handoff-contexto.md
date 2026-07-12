# Handoff técnico — suíte automotiva

> Checkpoint: **2026-07-12**. Estado atual (não diário de sessão).
> Confirme containers/`.env`/n8n antes de editar. Testes unitários ≠ E2E WhatsApp.
> Leia primeiro: `docs/contexto-compacto.md`. Planos válidos: `docs/plans/README.md`.

## Estado em uma frase

Demo forte com Motor, Estoque, Chatbot, Portal e Catálogo integrados por HTTP (~**78%** MVP,
~**62%** produção/revenda). Simulação ainda **mock**. Bot WhatsApp **off de propósito**.
Funil Catálogo→Chatbot→Portal existe em código; E2E operacional do outbox do catálogo pendente.

## Verificação

| Produto | Testes | Porta host típica |
|---|---:|---|
| Motor | 58 | `:8000` |
| Chatbot | 59 | `:8001` |
| Estoque | 45 | `:8100` |
| Catálogo | 19 | `:8200` |
| Portal | 86 | `:9000` |
| **Total** | **267** | Evolution `:8080`, n8n `:5678` |

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q
```

## Por produto (feito / falta)

### Motor (`motor-simulacao/`, `deploy/motor-standalone`)

- **Feito:** jobs async, worker/lease, auth+tenancy, cifra, CLI, mock de 5 bancos, compose.
- **Falta:** Task 10 revenda; **Tasks 11–12** credenciais por provedor + 1º driver real (híbrido
  API/Playwright). UI de troca de senha no Portal (#3A Task 9A). Agregador opcional depois.

### Chatbot (`chatbot-api/`, `deploy/chatbot-standalone`)

- **Feito:** tenancy, leads, conversas/mensagens, handoff, CPF mascarado no texto, webhook auth
  opt-in + dedupe `provider_message_id`, `HttpSimulationProvider`, atribuição catálogo
  `POST /v1/integracoes/catalogo/interesses` + migration `0004`, sem trava de consentimento (decisão).
- **Falta:** go-live (`docs/go-live-chatbot.md`); prompt n8n ainda fala de consentimento; mojibake na
  ingestão; webhooks de domínio; readiness real; LGPD completa (exclusão).

### Estoque (`estoque-api/`)

- **Feito:** CRUD, tenancy/RBAC, API pública, outbox HMAC, admin parcial, CSV/fotos.
- **Falta:** campo/API **placa** + `GET .../por-placa` (decisão #4A CRM WhatsApp — ainda não no
  código); E2E outbox+receptor; restore/revenda; fechar admin.

### Portal (`portal-gestao/`)

- **Feito:** auth/RBAC, estoque via API, leads, conversas+handoff, simulação manual (BFF),
  vendas/financeiro (#3B), metas de loja CRUD, `/app/vendedor`, funil em `/app/financeiro`,
  atribuições de atendimento (migration `0004`).
- **Falta:** simulação manual liberada de fato para `vendedor` (RBAC+testes; decisão já tomada);
  Task **9A** acessos das financeiras (depende Motor Task 11); metas individuais UI; campanhas;
  equipe/config; CSV reconciliação; Playwright E2E.

### Catálogo (`catalogo-publico/`, `deploy/catalogo-conectado`)

- **Feito:** vitrine/detalhe, CTA `wa.me` + ref `CAT-*`, eventos/UTM SQLite, outbox Bearer com
  retry/idempotência, Docker não-root.
- **Falta:** configurar `CATALOGO_EVENTS_URL`/`TOKEN` e E2E clique→Portal; SEO/cache/tema/standalone
  (resto do #5A).

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

1. Outbox do catálogo no deploy + E2E Catálogo → Chatbot → Portal.
2. Estoque **placa** + simulação WhatsApp (telefone, sem renda/prazo único) — #4A/#2A.
3. Portal: RBAC simulação vendedor; #3B residual; depois Task 9A (com Motor Task 11).
4. #5A residual (tema, SEO, rate limit, standalone).
5. Prompt n8n + mojibake; go-live do bot quando o dono decidir (`docs/go-live-chatbot.md`).
6. Motor Task 10 → 11 (credenciais) → 12 (**híbrido** API + Playwright; 1 banco piloto).
   Agregador opcional. Não reintroduzir mock como “banco real”.

## Avisos operacionais

1. E2E “sumiu”? Checar Evolution `open`, n8n **Published**, placeholders não voltaram,
   `SIMULATION_PROVIDER=http`, token Motor válido.
2. Não usar `printenv` em containers com tokens.
3. Scripts PowerShell que editam Code nodes do n8n: preservar `$('NomeDoNo')`.
4. Import n8n desativa workflow → precisa `publish:workflow` + restart.
5. Senha dev conhecida no handoff antigo: não documentar senhas aqui; usar seed/local.
