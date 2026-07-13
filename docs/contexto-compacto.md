# Contexto compacto para continuidade

Atualizado em **2026-07-13**. Leia isto primeiro; detalhes operacionais em `docs/handoff-contexto.md`.
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Sem reset/checkout destrutivo sem pedido explícito.
- Não ler/imprimir `.env`, tokens, chaves Gemini/Evolution/Motor ou senhas.
- Estoque = fonte de verdade. Integrações só por **HTTP** entre produtos.
- Ordem: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6`.
- Simulação com nomes de banco = **mock**. Não é cotação real. Caminho real planejado: **híbrido
  API + Playwright** (agregador opcional); senhas de portal rotacionam no **Dashboard** (~2 semanas)
  via Motor cifrado — ver Planos #1A e #3A Task 9A.
- Bot WhatsApp: **desativado de propósito** até `docs/go-live-chatbot.md`.

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock, **credenciais cifradas (Task 11)** | Task 10 revenda; Task 12 1º driver real |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, conversas, handoff, atrib. catálogo, sim HTTP, E2E outbox, **por-placa+sim multi-prazo**, **E3 auto-pausa**, **E5 cadastro WA** | go-live manual, LGPD exclusão, mojibake residual |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, público, RBAC, outbox, **placa + por-placa**, **placa no admin HTMX** | E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | leads/conversas/sim, **sim. vendedor**, vendas, metas loja, funil, **Task 9A financeiras**, **E10 Tráfego/CAPI** | #3B residual; Playwright E2E; worker retry CAPI |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA `CAT-*`, outbox, wiring funil, **Pixel Meta browser** | validar containers reais; SEO/tema; sync Pixel ID com Portal |

**Testes:** 305 (Motor 69 · Estoque 65 · Chatbot 62 · Portal 90 · Catálogo 19).  
**Estimativa:** ~**80%** MVP demonstrável · ~**65%** produção/revenda.

## Decisões de produto vigentes

- **Simulação = mock** até driver `real: true`. Caminho real: híbrido API + Playwright (+ agregador opcional).
- **Sem trava de consentimento** no chatbot (decisão do dono 2026-07). Schema/tabela de consentimento
  pode existir; o fluxo **não** bloqueia lead/nome. `design.md` / README raiz ainda citam consentimento
  antigo — **não reintroduzir** sem pedido.
- CPF mascarado no texto de mensagens.
- CRM WhatsApp: simular por **placa** + **telefone**; **sem** renda e **sem** prazo único na coleta
  (prazos padrão multi-opção). Valor do veículo só do Estoque. *(Estoque `por-placa` **feito**; falta
  o lookup+payload no Chatbot #2A.)*
- Vendedor **deve** poder simular manualmente, sem ver custo/lucro/tokens — **feito** (whitelist, Task 13).
- Senhas de portal bancário: rotação no **Dashboard** (#3A Task 9A) → Motor cifrado (#1A Task 11).
  **Nunca** colar login/senha de banco no chat com IA.
- Funil Catálogo→Chatbot→Portal com wiring de deploy (`CATALOGO_EVENTS_URL/TOKEN`, desligado por
  padrão) e E2E da entrega do outbox; falta validar em containers reais.

## Próxima sequência (sugerida)

1. Go-live WhatsApp sob demanda (`docs/go-live-chatbot.md`) — prompt/tools n8n **já atualizados** (import + publish).
2. Validar funil catálogo + Pixel em containers reais (`META_PIXEL_ID` alinhado à aba Tráfego).
3. #3B residual; #5A residual (SEO/tema); worker retry outbox CAPI.
4. Motor Task 10 (revenda) → 12 (1º driver real híbrido). Task 11 (credenciais) **feita**; UI Portal 9A **feita**.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q
git status --short
```
