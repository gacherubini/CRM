# Contexto compacto para continuidade

Atualizado em **2026-07-13** (pós placa/E3/E5/n8n/9A/E10). Leia isto primeiro; detalhes em
`docs/handoff-contexto.md`. Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Sem reset/checkout destrutivo sem pedido explícito.
- Não ler/imprimir `.env`, tokens, chaves Gemini/Evolution/Motor/Portal/CAPI ou senhas.
- Estoque = fonte de verdade. Integrações só por **HTTP** entre produtos.
- Ordem: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6`.
- Simulação com nomes de banco = **mock**. Caminho real: **híbrido API + Playwright** (agregador
  opcional). Senhas de portal: Dashboard **Task 9A** → Motor cifrado (Task 11).
- Bot WhatsApp: **desativado de propósito** até `docs/go-live-chatbot.md` (tools/prompt já atualizados).

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock, **credenciais (T11)** | T10 revenda; **T12 driver real** (design ok, código não) |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, handoff, funil, **por-placa+sim multi-prazo**, **E3**, **E5**, n8n tools | go-live manual; LGPD exclusão |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, público, placa+por-placa, **placa admin HTMX** | E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | CRM, sim vendedor, vendas/metas/funil, **9A financeiras**, **E10 Tráfego/CAPI** | #3B residual; Playwright E2E; retry CAPI |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA, outbox, **Pixel browser** | containers reais; SEO/tema; sync Pixel ID |

**Testes:** ~**358** (Motor 69 · Chatbot 88 · Estoque 65 · Portal 113 · Catálogo 23).  
**Estimativa:** ~**90%** MVP demonstrável · ~**75%** produção/revenda.

## Decisões de produto vigentes

- **Simulação = mock** até driver `real: true`.
- **Sem trava de consentimento** no fluxo WhatsApp.
- CPF mascarado em mensagens.
- CRM: simular por **placa + telefone**; sem renda; multi-prazo padrão; valor do **Estoque**.
  *(Chatbot lookup+sim por placa **feito**; n8n tools **feitos**.)*
- Vendedor simula sem custo/lucro/tokens — **feito**.
- Credenciais bancos: UI Portal **9A** → Motor — **feito** (API+UI).
- Pixel: Lead no CTA catálogo + Purchase na venda confirmada (CAPI) — **MVP feito**.
- Funil Catálogo→Chatbot wiring feito; validar em containers reais.

## Próxima sequência (sugerida)

1. Go-live WhatsApp (`docs/go-live-chatbot.md`) — import + publish + env.
2. Validar funil + Pixel em containers reais.
3. Motor Task 12 (driver real) + Task 10; #3B/#5A residual.
4. E1 áudio / E6 fotos / E8 ROI quando fizer sentido.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest tests/ -q
git status --short
```
