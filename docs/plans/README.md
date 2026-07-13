# Índice dos planos (canônico para agentes)

## Como usar (agentes)

1. `docs/contexto-compacto.md` — estado atual e regras (**sempre primeiro**).
2. `docs/handoff-contexto.md` — checkpoint operacional.
3. **Somente os planos desta pasta** (não `_archive/`) — o plano do produto a implementar.
4. `docs/go-live-chatbot.md` — só ao ligar o bot.

**Não** usar como fonte de verdade de implementação atual:

- `docs/plans/_archive/` (LEGADO)
- `docs/design.md` e trechos antigos do `README.md` raiz (pesquisa/histórico; podem citar
  consentimento obrigatório, renda/prazo e RPA-only — **superados** por este índice + #1A/#2A/#4A)

Cada plano `*A`/`*B` tem bloco **Status 2026-07-12** no topo: leia antes de reimplementar.

## Ordem válida de implementação

| Ordem | Plano | Produto | Status resumido |
|---:|---|---|---|
| 0 | [Plano #0](2026-07-11-plano0-fundacao-core-dominio-seguranca.md) | Contratos e segurança | Fundação — decisões ainda válidas |
| 1 | [Plano #1A](2026-07-11-plano1a-motor-simulacao-independente.md) | Motor de Simulação | Demo mock; **Task 11 (credenciais) feita**; falta Task 10 e Task 12 (1º driver real — ver sub-planos abaixo) |
| 2 | [Plano #4A](2026-07-11-plano4a-estoque-api-independente.md) | Estoque API/admin | Operacional; **placa + por-placa feitos**; falta placa na admin HTMX, outbox E2E/restore |
| 3 | [Plano #2A](2026-07-11-plano2a-chatbot-standalone-revendivel.md) | Chatbot + Estoque Lite | Código pronto; bot off; go-live pendente |
| 4 | [Plano #5A](2026-07-11-plano5a-catalogo-publico-independente.md) | Catálogo Público | 1º incremento entregue; residual SEO/tema |
| 5 | [Plano #3A](2026-07-11-plano3a-portal-vendedor-independente.md) | Portal/CRM | Base entregue via #3A.1 |
| 5.1 | [Plano #3A.1](2026-07-11-plano3a1-frontend-dashboard-mvp.md) | Frontend Dashboard MVP | MVP quase fechado; **RBAC sim. vendedor feito**; falta Playwright E2E |
| 6 | [Plano #3B](2026-07-11-plano3b-dashboard-dono-vendas-metas.md) | Vendas/metas/dono | Parcial (vendas, financeiro, metas loja) |
| futuro | [Plano #6](2026-07-11-plano6-evolucoes-roadmap.md) | Roadmap add-ons | Não iniciado |

Planos #1A e #4A podem avançar em paralelo após #0. #2A depende da fatia Lite do #4A.
Numeração é histórica; não obriga Portal antes de Estoque/Catálogo.

### Sub-planos da #1A Task 12 (driver real de simulação)

Detalham a Task 12 do #1A (1º driver `real: true`). Ler junto com o #1A:

- [Design/spec](2026-07-13-plano1a-task12-santander-design.md) — arquitetura, princípio **API-first**,
  base reutilizável, riscos ToS/fragilidade. **Aprovado pelo dono 2026-07-13.**
- [Plano de implementação — Fase 1 (Motor)](2026-07-13-plano1a-task12-santander-implementacao.md) —
  11 tasks TDD; piloto Santander via Playwright. **Não iniciado** (aguarda verificação de APIs).
- [Mapa dos bancos (reconhecimento)](2026-07-13-plano1a-task12-bancos-reconhecimento.md) — API vs
  Playwright por banco; Pan/BV/Bradesco **provavelmente têm API** (a confirmar com os bancos).

## Pacotes comerciais

- **Chatbot Atendimento:** #2A + Estoque Lite.
- **Chatbot Financiamento:** #2A + provider do #1A.
- **Motor / Estoque / Catálogo conectado:** cada um sozinho (#1A / #4A / #5A→Estoque).
- **Catálogo Standalone:** #5A + operação mínima #4A.
- **Portal do Vendedor:** #3A + Estoque; Bot/Motor opcionais.
- **Gestão completa:** #3A + #3B + Estoque (± Bot/Motor/Catálogo).

## Arquivo (não executar)

Planos monolíticos antigos (#1–#5 sem sufixo) estão em [`_archive/`](_archive/) — ~3k linhas de
código passo a passo obsoleto. **Não definem arquitetura nem ordem de implementação.**
