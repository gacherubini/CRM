# Plano #3A.1 — Frontend do Dashboard MVP

> Workstream executável do #3A. **MVP entregue** (2026-07-13) exceto Playwright E2E.
> Task 13 (sim vendedor) **feita**. Task 9A (financeiras) e E10 (Tráfego) vivem no Portal mas
> fora deste checklist original. Use este doc só para o residual, não para reimplementar.
>
> **2026-07-13:** progresso de simulação HTMX (`progresso.html` + rota job) + resultado multi-prazo
> com códigos de erro do Motor (**Santander live**, coluna **Entrada** necessária). **Task 16 histórico
> de simulações por usuário: FEITO** (rota `/app/simulacoes/historico` + `GET /v1/simulacoes` no Motor).
> Ainda aberto: Playwright E2E (Task 15).

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
| 16 | Histórico de simulações por usuário | **Feito** (2026-07-13) |

## Aberto (implementar daqui)

### Task 15 — Playwright E2E

- Fluxos críticos login → estoque → leads → handoff → simulação (smoke).

### Task 16 — Histórico de simulações por usuário — **FEITO (2026-07-13)**

Entregue: cada usuário vê o histórico das simulações que **ele** disparou.

- [x] Tela **Histórico de simulações** em `/app/simulacoes/historico` (template `historico.html`, link
      no form de Simular).
- [x] Escopo: **do usuário logado** (filtra `solicitado_por`=email); dono/gerente têm toggle
      **`?escopo=loja`** ("toda a loja"); vendedor forçado a "minhas".
- [x] Colunas: data/hora, status, placa/referência, prazos, bancos, solicitante (no escopo loja),
      atalho para `/app/simulacoes/job/{id}`; paginação.
- [x] Estados finais incluídos (`concluida`/`parcial`/`falhou`/`aguardando_intervencao`) + em andamento.
- [x] Tenancy: `GET /v1/simulacoes` escopado por `cliente_id`; nunca outro tenant.
- [x] Persistência: **`solicitado_por`** em `simulacoes` (migration 0009), gravado do header `X-Ator`;
      `GET /v1/simulacoes` com filtros (`status`/`solicitado_por`/`desde`/`ate`) + paginação
      (`limite`/`offset`); Portal BFF `MotorClient.listar_simulacoes` + rota + UI.

> **Nota:** sims **anteriores** ao deploy têm `solicitado_por` nulo → não aparecem em "minhas sims";
> dono vê no escopo "toda a loja". Novas sims populam normalmente.

#### Ao vivo (complemento — parcial/aberto)

- A lista inclui `recebida`/`processando`; **auto-refresh dedicado** da lista e **status por provedor**
  na listagem ainda não implementados (o job individual já tem progresso). Multi-banco RPA = **um
  Playwright por banco** (ver #1A Task 12) — ainda a implementar.

### Task 13 — RBAC da simulação (**feito 2026-07-13**)

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
- [x] Histórico de simulações por usuário (Task 16). (2026-07-13)
- [ ] Playwright E2E dos fluxos acima.
