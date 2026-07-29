# Índice dos planos (canônico para agentes)

## Como usar (agentes)

1. `docs/contexto-compacto.md` — estado atual, **eixos de prioridade** e regras (**sempre primeiro**).
2. `docs/handoff-contexto.md` — só o **checkpoint do topo** (seções antigas = histórico).
3. **Somente planos desta pasta com Status ≠ SUPERSEDED/DONE checklist** (não `_archive/`).
4. `docs/go-live-chatbot.md` — eixo demo/WA (local ou lab Fly).

**Não** usar como fonte de verdade de implementação atual:

- `docs/plans/_archive/` (LEGADO / checklists DONE)
- `docs/design.md` e trechos antigos do `README.md` raiz (pesquisa/histórico; podem citar
  consentimento obrigatório, renda/prazo e RPA-only — **superados** por este índice + #1A/#2A/#4A)
- cópias espelhadas `docs/superpowers/` (removidas; plano canônico só aqui)

Cada plano `*A`/`*B` tem bloco **Status** no topo: leia antes de reimplementar.

## Ordem válida de implementação

| Ordem | Plano | Produto | Status resumido |
|---:|---|---|---|
| 0 | [Plano #0](2026-07-11-plano0-fundacao-core-dominio-seguranca.md) | Contratos e segurança | Fundação — decisões ainda válidas |
| 1 | [Plano #1A](2026-07-11-plano1a-motor-simulacao-independente.md) | Motor de Simulação | Santander + Fontecred + Bradesco/Pan portal; fan-out; **B+D teto 2 + warm session** |
| 2 | [Plano #4A](2026-07-11-plano4a-estoque-api-independente.md) | Estoque API/admin | Operacional; idempotência+mídia periódica+outbox testado; falta restore drill |
| 3 | [Plano #2A](2026-07-11-plano2a-chatbot-standalone-revendivel.md) | Chatbot + Estoque Lite | API+E3+E5+**menu estoque WA**+fotos+sim+n8n; **roteamento 3 casos**; residual = **E2E humano** |
| 4 | [Plano #5A](2026-07-11-plano5a-catalogo-publico-independente.md) | Catálogo Público | Vitrine+funil+**Pixel browser** (ViewContent); residual SEO/tema |
| 5 | [Plano #3A](2026-07-11-plano3a-portal-vendedor-independente.md) | Portal/CRM | Base + **Task 9A financeiras + Ajustes reais feitos**; falta Playwright E2E |
| 5.1 | [Plano #3A.1](2026-07-11-plano3a1-frontend-dashboard-mvp.md) | Frontend Dashboard MVP | MVP fechado; **Task 16 histórico FEITO**; falta Playwright E2E |
| 6 | [Plano #3B](2026-07-11-plano3b-dashboard-dono-vendas-metas.md) | Vendas/metas/dono | Vendas+metas+CSV+**Task 5 campanhas**; **Task 4 funil DONE** |
| 6.1 | [Tráfego pago CRM](2026-07-20-plano-trafego-pago-crm-campanhas-roi.md) | Campanhas + atribuição + ROI | **DONE MVP** (`8e7ec5f`) — E8 + #3B T5; CAPI/CSV fechados no plano 6.2 |
| 6.2 | [Conversões / funil / insights](2026-07-21-plano-conversao-atribuicao-insights.md) | CAPI, gastos, resultados dono, funil, bus, Google | **ATIVO rev.3** — A/B/E/D/H/C/F feitos; residual G |
| 6.2b | [CTWA atribuição + CAPI messaging](2026-07-22-plano-ctwa-atribuicao-capi-messaging.md) | Click-to-WhatsApp no CRM, match campanha, Purchase messaging | **MVP CÓDIGO** — lead CTWA + match + CAPI messaging; residual E2E lab Evolution |
| 6.2c | [Meta spend API (gasto automático)](2026-07-22-plano-meta-spend-api.md) | Puxar `spend` do Ads via Marketing API → `CampanhaGasto` | **MVP + job 24h** — botão + thread + `/internal/jobs/meta-spend-sync`; residual OAuth / App Review |
| 6.3 | [Multi-WhatsApp por vendedor](2026-07-22-plano-multi-whatsapp-vendedores-campanhas.md) | Canais por vendedor + campanhas + inbox central | **ATIVO / NÃO IMPLEMENTADO** — iniciar pela Task 0 (contrato Evolution/CTWA e capacidade; fixture pode ser a mesma do 6.2b) |
| 6.4 | [Revy Tráfego × Portal loja](2026-07-28-plano-revy-trafego-separacao.md) | App gestor multi-loja + slim resultados no portal | **FASE 3 pronta**: banco próprio, projeção de vendas e outbox; deploy/cutover registrado no handoff |
| 6+ | [Plano #6](2026-07-11-plano6-evolucoes-roadmap.md) | Roadmap add-ons | E1 áudio backend feito; E6 automático WhatsApp → Estoque → Catálogo MVP feito; E3/E5/E8/E10 feitos |
| ops | [Plano #7 deploy Fly](2026-07-13-plano7-deploy-fly-io-design.md) | Lab Fly.io | **DONE** (monólitos); superado na prática pela arquitetura 3-VM |
| ops | [Arquitetura 3 VMs](2026-07-21-plano-arquitetura-3-vms.md) | Consolidação Fly (custo) | **IMPLEMENTADO / OPERANDO** — `suite-pg` + `evolution2037` + `app2037` always-on; `motor2037` Playwright on-demand; n8n webhook + roteamento 3 casos; ops = `deploy/fly/3vm/` + `up-all.sh --3vm` |
| ops | [Menu estoque WA + fixes foto](2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md) | Cadastro/menu/fotos prod | **CÓDIGO DONE** — próximo: E2E menu/cadastro, depois cliente novo |

Planos #1A e #4A podem avançar em paralelo após #0. #2A depende da fatia Lite do #4A.
Numeração é histórica; não obriga Portal antes de Estoque/Catálogo.

### Sub-planos da #1A Task 12 (driver real de simulação)

Detalham a Task 12 do #1A (1º driver `real: true`). Ler junto com o #1A:

- [Design/spec Santander](2026-07-13-plano1a-task12-santander-design.md) — API-first, base reutilizável.
- [Lições Santander](2026-07-13-playwright-licoes-santander.md) — **obrigatório** antes do próximo Playwright.
- [Mapa dos bancos + **campos por provedor**](2026-07-13-plano1a-task12-bancos-reconhecimento.md) —
  decisões LIVE/plano/backlog; tabela de campos canônica (entrada, placa, celular…).
- [Lições Fontecred](2026-07-15-playwright-licoes-fontecred.md) — **obrigatório** (sessão fria/quente,
  modal, waits, smoke no worker).
- [Decisão B+D captcha/IP](2026-07-16-fly-rpa-captcha-opcoes.md) — máx. **2** browsers + sessão quente.
- [Warm session + batch 2](2026-07-17-plano1a-warm-session-batch2.md) — **fases 0–2 DONE**; residual keep-alive/object store.
- [Fan-out / workers sob demanda](2026-07-14-plano1a-workers-playwright-sob-demanda.md) — **DONE** no código; teto default **2**.
- [Drivers Playwright resilientes](2026-07-21-plano-drivers-resilientes.md) — **BACKLOG / NÃO IMPLEMENTADO**;
  trace, sessão endurecida, locators resilientes e canários opcionais de IA/browser.
- [Estabilidade Bradesco Playwright](2026-07-24-plano-estabilidade-bradesco-playwright.md) —
  **BACKLOG PRIORIZADO / NÃO IMPLEMENTADO**; diagnóstico específico de sessão, login,
  máquina de estados, retry pós-envio e concorrência por credencial.
- Bradesco / Pan portal: checklists em `_archive/` — código LIVE; lições [Pan portal](2026-07-15-playwright-licoes-pan-portal.md).

## Pacotes comerciais

- **Chatbot Atendimento:** #2A + Estoque Lite (+ E5 cadastro WA).
- **Chatbot Financiamento:** #2A + provider do #1A (+ por-placa/sim).
- **Motor / Estoque / Catálogo conectado:** cada um sozinho (#1A / #4A / #5A→Estoque).
- **Catálogo Standalone:** #5A + operação mínima #4A (± Pixel env).
- **Portal do Vendedor:** #3A + Estoque; Bot/Motor opcionais; 9A se Motor.
- **Gestão completa:** #3A + #3B + Estoque (± Bot/Motor/Catálogo/E10/E8).

## Arquivo (não executar)

Tudo em [`_archive/`](_archive/) é **histórico** — não define arquitetura nem ordem de implementação.

| Arquivado | Por quê / ler em vez disso |
|---|---|
| Planos monolíticos #1–#5 (2026-07-11) | Substituídos pelos `*A` / `*B` |
| `…-santander-implementacao.md` | Checklist DONE; usar **lições** + **design** Santander |
| `…-bradesco-implementacao.md` / `…-pan-playwright-implementacao.md` | Checklists DONE; usar mapa de bancos + código + lições |
| `…-plano7-deploy-fly-io-implementacao.md` | 1ª subida Fly já feita; ops = `deploy/fly/*.sh` + design #7 |
| `…-fontecred-deploy-handoff.md` | SUPERSEDED; usar **lições Fontecred** |
