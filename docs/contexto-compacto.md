# Contexto compacto para continuidade

Atualizado em **2026-07-13** (Santander **entrada retornada** + fix skeleton; **Task 16 histórico** live).  
Leia isto primeiro; detalhes em `docs/handoff-contexto.md`.  
**Playwright / próximos bancos:** `docs/plans/2026-07-13-playwright-licoes-santander.md`.  
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Sem reset/checkout destrutivo sem pedido explícito.
- Não ler/imprimir `.env`, tokens, chaves Gemini/Evolution/Motor/Portal/CAPI ou senhas.
- Estoque = fonte de verdade. Integrações só por **HTTP** entre produtos.
- Ordem: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6`.
- Simulação: **mock** até driver `real: true`. **Santander = real** (piloto live). No Santander a
  **entrada é calculada pelo banco** e devolvida (campo `entrada` no resultado) — não é input.
  Demais: híbrido **API-first** + Playwright só se não houver API.
- Senhas de portal: Dashboard **9A** → Motor cifrado (Task 11).
- Bot WhatsApp: **off** até `docs/go-live-chatbot.md` (n8n importado; falta Publish + `ESTOQUE_API_*`).

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock, T11, **T12 Santander live** (headed+Xvfb, **entrada retornada**, fix skeleton), **listagem `GET /v1/simulacoes` + `solicitado_por`** (T16), migrations head 0009 | outros bancos; 1 PW/banco paralelo; T10; **2 falhas pré-existentes** (mock Santander) |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, handoff, por-placa, E3, E5, n8n tools | go-live manual; LGPD |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, placa, por-placa | E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | CRM, **progresso sim + resultado multi-prazo (coluna Entrada)**, **histórico de sims por usuário (T16)**, 9A, E10 | #3B; E2E |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA, Pixel browser | containers reais; SEO |

**Estimativa:** ~**93%** MVP demonstrável (cotação real Santander + histórico) · ~**76%** produção/revenda multi-banco.

## Decisões vigentes

- Santander: Playwright headed + Xvfb (headless_shell = Akamai).
- 1 browser por banco (isolamento); multi-banco paralelo ainda a implementar.
- Credenciais só no Motor (Portal só BFF).
- `testar-login` ainda placeholder — simulação real é a prova de credencial.

## Próxima sequência (sugerida)

1. **Corrigir 2 falhas pré-existentes** do Motor (mock `Santander` sombreado pelo driver real homônimo).
2. **Próximo banco** — ler lições Santander (inclui skeleton); API-first (Pan/BV/Bradesco); Fontecred se Playwright.
3. Go-live WhatsApp se operação priorizar (`docs/go-live-chatbot.md`).
4. Multi-banco paralelo; `testar-login` real; Task 10 revenda.

> **Histórico de simulações por usuário (Task 16): FEITO** — não reimplementar.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/test_santander_driver.py tests/test_listar_simulacoes.py -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_simulacoes.py tests/test_simulacoes_historico.py -q
cd ..\deploy\motor-standalone
docker compose exec -T motor-worker sh -c "pgrep -a Xvfb"
docker compose exec -T motor-api sh -c "cd /srv && alembic current"   # deve ser 0009 (head)
git status --short
```
