# Índice dos planos (canônico para agentes)

> Última revisão: 2026-08-08. Planos marcados **DONE documentam o código atual** — são
> referência, não fila. A fila real está em "Próximos passos".

## Como usar

1. [`../contexto-compacto.md`](../contexto-compacto.md) — estado atual e prioridades
   (**sempre primeiro**).
2. [`../handoff-contexto.md`](../handoff-contexto.md) — checkpoint operacional.
3. Para evolução de produto: **Revy Control (6.5)** e **Revy Loja (6.6)** antes de tudo.
4. Cada plano `*A`/`*B` tem bloco **Status** no topo. Leia antes de reimplementar.

**Não** use como fonte de verdade da implementação atual: `_archive/` (histórico/DONE) e
`../superpowers/plans/` como fila principal (são auxiliares). `../superpowers/specs/`
continua válido quando um plano canônico o referencia.

## Próximos passos ativos (2026-08+)

Um eixo por mudança; não misture. Fonte viva: `../contexto-compacto.md` → "Prioridades
independentes".

- **Atribuição CTWA (Graph, sempre ON):** cache `meta_ad_campanha`, worker no lifespan,
  casador via mapa; proteções de max tentativas, cooldown 24h, teto 20 calls/ciclo, backoff
  429/5xx. Campanha Revy precisa de `meta_campaign_id` + token `ads_read`.
- **CTWA/ROI herança venda→lead:** código implementado 2026-08-08 (Tasks 1/2/3/5/6/8/9).
  Pendente só a **Task 4**, que é configuração dos anúncios, não código.
- **Bot WhatsApp:** smoke virgem/CTWA/handoff/salvo no lab → workflow Active ON; residual
  de outbox/retry do alerta de simulação (Fase 3).
- **Multi-WhatsApp (Control Fase 5):** E2E com dois canais + `canal_id` correto.
- **Google Ads (Control Fase 4):** secrets GCP + OAuth/métricas/conversões.
- **Motor/RPA:** smoke real por banco (o resultado ao cliente segue humano no Portal).
- **Revy Loja:** deep-links de simulação/venda no workspace + telemetria. Seller AI (F7)
  adiado.

## Ordem válida de implementação

| # | Plano | Produto | Status |
|---:|---|---|---|
| 0 | [#0 Fundação](2026-07-11-plano0-fundacao-core-dominio-seguranca.md) | Contratos e segurança | Decisões ainda válidas |
| 1 | [#1A Motor](2026-07-11-plano1a-motor-simulacao-independente.md) | Motor | 4 bancos LIVE; fan-out; teto 2 + warm session |
| 2 | [#4A Estoque](2026-07-11-plano4a-estoque-api-independente.md) | Estoque API/admin | Operacional; falta restore drill |
| 3 | [#2A Chatbot](2026-07-11-plano2a-chatbot-standalone-revendivel.md) | Chatbot + Estoque Lite | Completo; residual = E2E humano |
| 4 | [#5A Catálogo](2026-07-11-plano5a-catalogo-publico-independente.md) | Catálogo Público | Vitrine + funil + Pixel; residual SEO/tema |
| 5 | [#3A Portal](2026-07-11-plano3a-portal-vendedor-independente.md) | Portal/CRM | Base + financeiras + Ajustes; falta Playwright E2E |
| 5.1 | [#3A.1 Dashboard](2026-07-11-plano3a1-frontend-dashboard-mvp.md) | Frontend MVP | Fechado; falta Playwright E2E |
| 6 | [#3B Vendas/metas](2026-07-11-plano3b-dashboard-dono-vendas-metas.md) | Vendas, metas, funil | DONE |
| 6.1 | [Tráfego pago CRM](2026-07-20-plano-trafego-pago-crm-campanhas-roi.md) | Campanhas + ROI | DONE MVP |
| 6.2 | [Conversões / funil](2026-07-21-plano-conversao-atribuicao-insights.md) | CAPI, gastos, funil, bus | DONE no escopo; Google migrou ao Control |
| 6.2b | [CTWA + CAPI messaging](2026-07-22-plano-ctwa-atribuicao-capi-messaging.md) | CTWA no CRM, Purchase messaging | PARCIAL — match por campanha estava quebrado; corrigido pelo 6.2d |
| 6.2c | [Meta spend API](2026-07-22-plano-meta-spend-api.md) | `spend` do Ads → `CampanhaGasto` | MVP + job 24h; residual OAuth/App Review |
| 6.2d | [CTWA por ad_id + Graph](../superpowers/plans/2026-08-04-atribuicao-ctwa-campanha.md) | Lead na 2ª msg + `ad_id→campaign_id` | **Código atual.** Cadastro manual de `ad_ids` removido |
| 6.2e | [CTWA/ROI herança venda→lead](../superpowers/plans/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md) | Venda herda campanha do lead; origem honesta | IMPLEMENTADO 08/08; Task 4 é configuração, segue pendente |
| 6.4 | [Revy Tráfego × Portal](2026-07-28-plano-revy-trafego-separacao.md) | App multi-loja + slim no portal | Fase 3 pronta: banco próprio, projeção, outbox |
| 6.5 | [Revy Control](2026-07-29-plano-revy-control.md) | Lojas, RBAC, módulos, Google, auditoria, multi-WA | Produto completo; residual = GCP humano + lab E2E |
| 6.5b | [PR-4 memberships](2026-07-31-pr4-identidade-loja-fase-b-memberships.md) | Dono multi-loja por convite | IMPLEMENTADO (`cd9e4f0`) |
| 6.6 | [Revy Loja](2026-07-29-plano-revy-loja.md) | Vendas + Estoque, Atendimento, Multibanco | F0–F6+F8 completo; F7 Seller AI adiado |
| 6+ | [#6 Roadmap](2026-07-11-plano6-evolucoes-roadmap.md) | Ideias históricas | Itens "ativos" exigem revalidação em Control/Loja |
| ops | [Arquitetura 3 VMs](2026-07-21-plano-arquitetura-3-vms.md) | Consolidação Fly | OPERANDO — ops em `deploy/fly/3vm/` |
| ops | [Runbook rollout lab](2026-07-29-runbook-rollout-lab-provisionamento.md) | Subida do lab + provisionamento | Usar junto de `deploy/fly/3vm/README.md` |
| ops | [Menu estoque WA + fotos](2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md) | Cadastro/menu/fotos | Código DONE; falta E2E |
| ops | [Alerta simulação no grupo](2026-08-05-plano-alerta-grupo-estoque-simulacao.md) | Chatbot + n8n + Evolution | F0–F2 no código; residual outbox/retry + smoke |

#1A e #4A avançam em paralelo depois do #0; #2A depende da fatia Lite do #4A. A numeração é
histórica e **não** obriga Portal antes de Estoque/Catálogo.

### Gates Control × Loja

As fases dos dois planos são gates, não duas filas em sequência:

| Corte | Control | Loja | Libera |
|---|---|---|---|
| Fundação | 0–2 | 0 | loja, identidade, cargos e entitlements confiáveis |
| MVP comercial | 3 | 1–5 | Vendas + Estoque, dashboard, Atendimento, Multibanco |
| Google Ads | 4 | resumo na F3 | leitura, atribuição e conversões Google |
| Multi-WhatsApp | 5 | 6 | vários números, conversa pelo canal correto |
| IA comercial | — | 7 | follow-ups, propostas e Seller AI |
| Consolidação | 6–7 | 8 | dashboards finais, rollout e limpeza |

Control 4 e 5 são independentes. O MVP comercial não precisa esperar Google nem
Multi-WhatsApp; integração ausente deve aparecer como **indisponível**, nunca como
resultado zero.

## Sub-planos da #1A Task 12 (drivers reais)

- [Design/spec Santander](2026-07-13-plano1a-task12-santander-design.md) — base reutilizável.
- [Lições Santander](2026-07-13-playwright-licoes-santander.md) — **obrigatório** antes do
  próximo Playwright.
- [Mapa dos bancos + campos por provedor](2026-07-13-plano1a-task12-bancos-reconhecimento.md)
  — tabela de campos canônica.
- [Lições Fontecred](2026-07-15-playwright-licoes-fontecred.md) — **obrigatório** (sessão
  fria/quente, modal, waits, smoke no worker).
- [Lições Pan portal](2026-07-15-playwright-licoes-pan-portal.md).
- [Decisão B+D captcha/IP](2026-07-16-fly-rpa-captcha-opcoes.md) — máx. **2** browsers.
- [Warm session + batch 2](2026-07-17-plano1a-warm-session-batch2.md) — fases 0–2 DONE.
- [Workers sob demanda](2026-07-14-plano1a-workers-playwright-sob-demanda.md) — DONE.
- [Drivers resilientes](2026-07-21-plano-drivers-resilientes.md) — **BACKLOG**, não
  implementado.
- [Estabilidade Bradesco](2026-07-24-plano-estabilidade-bradesco-playwright.md) —
  **BACKLOG priorizado**, não implementado.

## Arquivo (não executar)

Tudo em [`_archive/`](_archive/) é histórico e não define arquitetura nem ordem.

| Arquivado | Ler em vez disso |
|---|---|
| Planos monolíticos #1–#5 (2026-07-11) | Os `*A` / `*B` |
| `…-santander-implementacao.md` | Lições + design Santander |
| `…-bradesco-implementacao.md` · `…-pan-playwright-implementacao.md` | Mapa de bancos + código + lições |
| `…-plano7-deploy-fly-io-*.md` | Arquitetura 3-VM + `deploy/fly/3vm/` |
| `…-fontecred-deploy-handoff.md` | Lições Fontecred |
| `…-multi-whatsapp-vendedores-campanhas.md` | Revy Control, Fase 5 |

Estrutura comercial (Control, Loja, módulos Vendas/Estoque, capacidades embutidas):
[`../README-COMERCIAL.md`](../README-COMERCIAL.md). Nomes de pacotes standalone dos planos
antigos são históricos e não orientam o menu nem a arquitetura comercial.
