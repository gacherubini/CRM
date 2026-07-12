# Contexto compacto para continuidade

Atualizado em **2026-07-12**. Leia isto primeiro; detalhes operacionais em `docs/handoff-contexto.md`.
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
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock | Task 10–12; credenciais; 1º driver real |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, conversas, handoff, atrib. catálogo, sim HTTP | go-live, prompt, mojibake, LGPD; sim por placa |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, público, RBAC, outbox | **placa + por-placa**; E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | leads/conversas/sim, vendas, metas loja, vendedor, funil | sim. p/ vendedor; Task 9A acessos bancos; #3B residual; Playwright E2E |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA `CAT-*`, outbox | E2E events URL; SEO/tema/standalone |

**Testes:** 267 (Motor 58 · Estoque 45 · Chatbot 59 · Portal 86 · Catálogo 19).  
**Estimativa:** ~**78%** MVP demonstrável · ~**62%** produção/revenda.

## Decisões de produto vigentes

- **Simulação = mock** até driver `real: true`. Caminho real: híbrido API + Playwright (+ agregador opcional).
- **Sem trava de consentimento** no chatbot (decisão do dono 2026-07). Schema/tabela de consentimento
  pode existir; o fluxo **não** bloqueia lead/nome. `design.md` / README raiz ainda citam consentimento
  antigo — **não reintroduzir** sem pedido.
- CPF mascarado no texto de mensagens.
- CRM WhatsApp: simular por **placa** + **telefone**; **sem** renda e **sem** prazo único na coleta
  (prazos padrão multi-opção). Valor do veículo só do Estoque. *(Planejado nos #4A/#2A/#1A; código ainda no contrato antigo.)*
- Vendedor **deve** poder simular manualmente, sem ver custo/lucro/tokens (RBAC pendente).
- Senhas de portal bancário: rotação no **Dashboard** (#3A Task 9A) → Motor cifrado (#1A Task 11).
  **Nunca** colar login/senha de banco no chat com IA.
- Funil Catálogo→Chatbot→Portal em código; outbox do catálogo ainda precisa env de deploy.

## Próxima sequência (sugerida)

1. `CATALOGO_EVENTS_URL`/`TOKEN` + E2E clique → Portal.
2. Estoque **placa** + Chatbot lookup + payload sim (telefone, sem renda/prazo único).
3. Portal: RBAC sim. vendedor + Task 9A (quando Motor tiver API de credenciais).
4. #3B residual; #5A residual; prompt n8n; go-live sob demanda.
5. Motor Task 10 → 11 (credenciais) → 12 (1º driver real híbrido).

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\catalogo-publico; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q
git status --short
```
