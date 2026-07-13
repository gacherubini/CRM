# Handoff técnico — suíte automotiva

> Checkpoint: **2026-07-13 (pós Fases 1–3 + n8n + 9A + E10)**. Estado atual (não diário de sessão).
> Confirme containers/`.env`/n8n antes de editar. Testes unitários ≠ E2E WhatsApp.
> Leia primeiro: `docs/contexto-compacto.md`. Planos válidos: `docs/plans/README.md`.

## Estado em uma frase

Suíte **demo forte / quase pronta para operação** (~**90%** MVP demonstrável, ~**75%** produção/revenda).
Motor/Estoque/Chatbot/Portal/Catálogo integrados por HTTP. Simulação ainda **mock**. Bot WhatsApp
**off de propósito** (workflow + tools **atualizados**, falta import/publish/go-live). Entregues nesta
onda: **placa CRM**, **E3 auto-pausa**, **E5 cadastro WA**, **prompt/tools n8n**, **Task 9A financeiras**,
**E10 Pixel Meta**.

## Verificação

| Produto | Testes (aprox.) | Porta host típica |
|---|---:|---|
| Motor | 69 | `:8000` |
| Chatbot | 88 | `:8001` |
| Estoque | 65 | `:8100` |
| Catálogo | 23 | `:8200` |
| Portal | 113 | `:9000` |
| **Total** | **~358** | Evolution `:8080`, n8n `:5678` |

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest tests/ -q
```

## Por produto (feito / falta)

### Motor (`motor-simulacao/`, `deploy/motor-standalone`)

- **Feito:** jobs async, worker/lease, auth+tenancy, cifra, CLI, mock de 5 bancos, compose,
  **Task 11** (credenciais cifradas por cliente+provedor, listar/upsert/testar-login, GET mascarado,
  auditoria — `testar-login` placeholder até driver real).
- **Falta:** **Task 10** revenda; **Task 12** 1º driver real (design Santander aprovado; implementação
  **não iniciada**). UI Portal 9A **feita** (consome esta API).

### Chatbot (`chatbot-api/`, `deploy/chatbot-standalone`)

- **Feito:** tenancy, leads, conversas/mensagens, handoff, CPF mascarado, webhook auth opt-in +
  dedupe, sim HTTP/mock, atribuição catálogo + E2E outbox, **sem trava consentimento**,
  **GET /v1/estoque/por-placa**, **POST /v1/simular** (placa → valor do Estoque; multi-prazo padrão
  24/36/48/60; sem renda obrigatória), **E3 auto-pausa** (`from_me` sem `origem_bot` → pausa;
  ack/status/vazio ignorados), **E5** números autorizados + `POST /v1/operacao/veiculos` → Estoque
  privado, env `ESTOQUE_API_URL`/`TOKEN`, migration `0005_numeros_autorizados`.
- **n8n versionado:** prompt/tools atualizados (placa, por-placa, sim, cadastrar_veiculo); workflow
  **ainda `active: false`**.
- **Falta:** go-live manual (`docs/go-live-chatbot.md`); LGPD exclusão; readiness real; mojibake residual
  se ainda aparecer; worker/foto E6 no cadastro.

### Estoque (`estoque-api/`)

- **Feito:** CRUD, tenancy/RBAC, API pública, outbox HMAC, admin parcial, CSV/fotos, **placa**
  normalizada + unicidade + `por-placa` + **campo placa no admin HTMX** (form/painel recriados) e
  Portal form/lista.
- **Falta:** E2E outbox+receptor em containers; restore/revenda; admin 100% fechado.
  *(Wart: migrations `0002/0003` não rodam em SQLite; prod Postgres.)*

### Portal (`portal-gestao/`)

- **Feito:** auth/RBAC, estoque, leads, conversas+handoff, simulação (vendedor sem lucro/tokens),
  vendas/financeiro/metas loja/funil, **Task 9A** `/app/financeiras` (BFF Motor), **E10** `/app/trafego`
  (Pixel + CAPI token cifrado, Purchase ao confirmar venda, outbox best-effort).
- **Env:** `MOTOR_URL`/`MOTOR_TOKEN`, `PORTAL_ENCRYPTION_KEY`.
- **Falta:** #3B residual (metas por vendedor UI, campanhas, equipe/config real, CSV reconciliação);
  Playwright E2E; worker de retry do outbox CAPI; phone hash no Purchase se houver telefone na venda.

### Catálogo (`catalogo-publico/`, `deploy/catalogo-conectado`)

- **Feito:** vitrine/detalhe, CTA `wa.me`+`CAT-*`, UTM/eventos, outbox, wiring funil deploy + E2E
  entrega, **Pixel browser** (`META_PIXEL_ID`: PageView + Lead com `event_id`).
- **Falta:** validar funil+pixel em containers reais; SEO/cache/tema/standalone; sync automático
  Pixel ID com Portal (hoje operador alinha manualmente).

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Integrações **só HTTP**. Estoque = fonte de verdade dos veículos. Tokens só no servidor.
- **Nunca** ler/versionar `.env`, tokens Motor/Chatbot, Evolution, Gemini, `MOTOR_ENCRYPTION_KEY`,
  `PORTAL_ENCRYPTION_KEY`, token CAPI.
- n8n versionado: placeholders (`__INSTANCE__`, `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`).
- Ordem dos planos: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6`.
  Ignore `docs/plans/_archive/` (LEGADO).
- Parcelas com nomes de banco = **sempre mock** até driver `real: true`.

## Próximos passos (ordem)

1. **Go-live WhatsApp** sob demanda — import workflow, placeholders, `ESTOQUE_API_*`,
   `autorizar-numero`, publish (`docs/go-live-chatbot.md`).
2. Validar funil catálogo + Pixel em **containers reais** (token/slug + `META_PIXEL_ID` = aba Tráfego).
3. Motor **Task 12** (1º driver real) + **Task 10** revenda; #3B residual; #5A residual.
4. CAPI retry worker; E1 áudio / E6 fotos quando operação pedir.

## Avisos operacionais

1. E2E “sumiu”? Evolution `open`, n8n **Published**, placeholders, `SIMULATION_PROVIDER=http`, token Motor.
2. Não usar `printenv` em containers com tokens.
3. Scripts PowerShell em Code nodes n8n: preservar `$('NomeDoNo')`.
4. Import n8n desativa workflow → `publish:workflow` + restart.
5. E3: Evolution deve entregar `fromMe` com texto; bot outbound com `origem_bot: true` + `provider_message_id`.
6. `chatbot-api/`: use `pytest tests/ -q` (evitar dirs `test-tmp-run*`).
7. Portal produção: definir `PORTAL_ENCRYPTION_KEY` (`python -m app.cli gerar-chave-cifragem`).
