# Plano #3A.1 — Frontend do Dashboard MVP

> Workstream executável do #3A. **Maior parte entregue** (2026-07-12). Use este doc para o que
> ainda falta, não para reimplementar do zero. Detalhe de produto #3A: `plano3a-*.md`.

**Goal:** Dashboard web (dono/gerente/vendedor) com login, estoque via API, leads, handoff e
simulação manual — tokens só no servidor.

**Stack:** FastAPI, Jinja2, HTMX, Tailwind local, SQLAlchemy/Alembic, PostgreSQL, httpx, pytest;
Playwright para E2E crítico.

## Arquitetura (fixa)

```text
Browser → sessão/cookie → Portal BFF
  ├── Estoque API (token servidor)
  ├── Chatbot API (token servidor)
  └── Motor (via Chatbot/simular; opcional)
```

- Fonte de verdade: veículos = Estoque; leads/conversas = Chatbot; usuários = Portal.
- Sem métricas financeiras mock no MVP; financeiro real é #3B (já iniciado).
- Nunca `Authorization: Bearer` no browser.

## Status das tasks

| Task | Tema | Status |
|---:|---|---|
| 1–5 | Scaffold, auth, clients HTTP, design system | **Feito** |
| 6–9 | Visão geral + estoque (lista/CRUD/publicar) | **Feito** |
| 10–12 | Leads, endpoints conversas no Chatbot, handoff UI | **Feito** |
| 13 | Simulação manual | **Feito** (2026-07-13) — `vendedor` libera via RBAC; whitelist `simulacao_sem_dados_sensiveis` esconde custo/lucro/tokens |
| 14 | Docker / compose portal | **Feito** (ajustar se faltar standalone empacotado) |
| 15 | Playwright E2E | **Aberto** |

## Aberto (implementar daqui)

### Task 13 — completar RBAC da simulação

- Papéis `dono`, `gerente` e **`vendedor`** podem `POST` simulação via BFF.
- Vendedor **não** vê custo do veículo, lucro, tokens Motor nem métricas financeiras.
- Aceite: testes de autorização + HTML sem campos sensíveis para vendedor.

### Task 15 — E2E Playwright

1. Login dono → CRUD/publicar veículo → refletir na API pública.
2. Lista/detalhe lead; conversa Assumir/Devolver.
3. Vendedor: sem custo/config; com simulação sem dados sensíveis.
4. Chatbot indisponível não derruba estoque.
5. Nenhum token em HTML/storage/network do browser.

## Fora deste plano (#3B / depois)

Vendas, lucro, metas, funil, campanhas, CSV, equipe/config — ver #3B e handoff.

## Definition of Done (MVP)

- [x] Login, sessão, RBAC/tenancy e estoque via API.
- [x] Leads e conversas/handoff reais.
- [x] Tokens não no navegador (padrão BFF).
- [x] Simulação autorizada ao vendedor sem dados sensíveis. (2026-07-13)
- [ ] Playwright E2E dos fluxos acima.
