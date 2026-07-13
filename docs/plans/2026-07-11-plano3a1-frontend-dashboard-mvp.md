# Plano #3A.1 — Frontend do Dashboard MVP

> Workstream executável do #3A. **MVP entregue** (2026-07-13) exceto Playwright E2E.
> Task 13 (sim vendedor) **feita**. Task 9A (financeiras) e E10 (Tráfego) vivem no Portal mas
> fora deste checklist original. Use este doc só para o residual, não para reimplementar.
>
> **2026-07-13:** progresso de simulação HTMX (`progresso.html` + rota job) + resultado multi-prazo
> com códigos de erro do Motor (**Santander live**). Ainda aberto: **histórico de simulações do
> usuário** + lista ao vivo (Task 16).

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

### Task 15 — Playwright E2E

- Fluxos críticos login → estoque → leads → handoff → simulação (smoke).

### Task 16 — Histórico + simulações ao vivo no Portal (pedido dono 2026-07-13)

> Parcial: já existe `/app/simulacoes/job/{id}` com progresso auto-refresh e resultado multi-prazo
> (Santander live). **Não** há ainda lista/histórico — cada simulação some depois de abrir o resultado.

#### Histórico por usuário (requisito de produto — dono 2026-07-13)

Cada **usuário do Portal** (vendedor/gerente/dono da loja) precisa ver o **histórico das simulações
que ele disparou** (não só “jobs em andamento” da loja inteira):

- [ ] Tela **Histórico de simulações** (ex.: `/app/simulacoes/historico` ou aba em Simular).
- [ ] Escopo: **do usuário logado** (ator/email ou `user_id` do Portal). Dono/gerente podem ter
      filtro “só eu / toda a loja” (opcional na v1; v1 mínima = pelo menos “minhas sims”).
- [ ] Colunas mínimas: data/hora, status, placa/CPF mascarado, prazos, bancos, atalho para o
      resultado/job (reabrir tela de parcelas ou progresso se ainda rodando).
- [ ] Incluir estados finais: `concluida`, `parcial`, `falhou`, `aguardando_intervencao` — não
      só `processando`.
- [ ] Tenancy: só sims do **cliente Motor da loja**; nunca de outro tenant.
- [ ] Persistência: Motor já guarda `simulacoes`/`simulacao_resultados` por `cliente_id`. Falta:
      - Motor: `GET /v1/simulacoes` com filtros (status, `desde`/`ate`, paginação) e, se possível,
        correlacionar **ator** (quem pediu) — hoje o job pode não guardar `usuario_portal`;
        gravar `referencia_externa` ou campo `solicitado_por` no create (Portal envia email do
        usuário logado).
      - Portal BFF: lista filtrada + UI.

#### Ao vivo (complemento)

- [ ] Lista “em andamento” (`recebida`/`processando`) com auto-refresh e link para o job.
- [ ] Multi-banco: status por provedor na lista e no detalhe.
- [ ] Alinhado ao Motor: multi-banco RPA = **um Playwright por banco** (ver #1A Task 12).

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
- [ ] Playwright E2E dos fluxos acima.
