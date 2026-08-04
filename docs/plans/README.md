# Índice dos planos (canônico para agentes)

> **Última revisão: 2026-08-04.** Situação atual: Revy Control (F0–F6) e Revy Loja
> (F0–F6/F8) implementados; bot WhatsApp com atendimento humano + gate n8n; **atribuição
> CTWA por `ad_id` Fase 1 deployada** (`app2037`). A fila real está em **Próximos passos**
> abaixo; os planos marcados **DONE documentam o código atual** (referência, não fila).

## Como usar (agentes)

1. `docs/contexto-compacto.md` — estado atual, **eixos de prioridade** e regras (**sempre primeiro**).
2. `docs/handoff-contexto.md` — checkpoint operacional atual e conciso.
3. Para evolução de produto, ler primeiro **Revy Control (6.5)** e **Revy Loja (6.6)**;
   planos DONE explicam o código atual, mas não redefinem as fronteiras futuras.
4. **Somente planos desta pasta com Status ≠ SUPERSEDED/DONE checklist** (não `_archive/`).
5. `docs/go-live-chatbot.md` — eixo demo/WA (local ou lab Fly).

**Não** usar como fonte de verdade de implementação atual:

- `docs/plans/_archive/` (LEGADO / checklists DONE)
- `docs/superpowers/plans/` como fila principal (são planos auxiliares/históricos);
  `docs/superpowers/specs/` continua válido quando o plano canônico o referencia

Cada plano `*A`/`*B` tem bloco **Status** no topo: leia antes de reimplementar.

## Próximos passos ativos (2026-08+)

Eixos com trabalho real pendente (um por mudança; não misturar). Fonte viva:
`docs/contexto-compacto.md` → "Prioridades independentes".

- **Atribuição CTWA — Fase 2:** resolver `ad_id→campaign_id` via Graph API (Tasks 5–8 do
  [plano 2026-08-04](../superpowers/plans/2026-08-04-atribuicao-ctwa-campanha.md)); **pende
  token `ads_read`**. Fase 1 já deployada. Antes de medir de fato: cadastrar `ad_id` nas
  campanhas + lançar gasto (README do plano).
- **Bot WhatsApp:** smoke virgem/CTWA/handoff/salvo no lab → workflow Active ON.
- **Multi-WhatsApp (Control Fase 5):** E2E dois canais + `canal_id` correto.
- **Google Ads (Control Fase 4):** secrets GCP + OAuth/métricas/conversões.
- **Motor/RPA:** smoke real por banco (resultado ao cliente ainda humano no Portal).
- **Revy Loja:** deep-links simulação/venda no workspace + telemetria; Seller AI (F7) adiado.

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
| 6.2 | [Conversões / funil / insights](2026-07-21-plano-conversao-atribuicao-insights.md) | CAPI, gastos, resultados dono, funil e bus | **DONE NO ESCOPO** — Google movido ao Revy Control |
| 6.2b | [CTWA atribuição + CAPI messaging](2026-07-22-plano-ctwa-atribuicao-capi-messaging.md) | Click-to-WhatsApp no CRM, match campanha, Purchase messaging | **PARCIAL/REVISTO** — CAPI messaging válido; o **match por campanha estava quebrado na prática** (diag. dia 1: 0 leads criados, `meta_campaign_id` sempre nulo). Corrigido/estendido pelo **6.2d**. |
| 6.2c | [Meta spend API (gasto automático)](2026-07-22-plano-meta-spend-api.md) | Puxar `spend` do Ads via Marketing API → `CampanhaGasto` | **MVP + job 24h** — botão + thread + `/internal/jobs/meta-spend-sync`; residual OAuth / App Review |
| 6.2d | [CTWA por ad_id + Graph](../superpowers/plans/2026-08-04-atribuicao-ctwa-campanha.md) | Lead na 2ª mensagem + match por `ad_id`; resolução `ad_id→campaign_id` via Graph | **FASE 1 DEPLOYADA** (`app2037`, 2026-08-04): tabela `campanha_anuncios`, matcher ad_id, UI, lead na 2ª msg. **Fase 2 (Graph) pende token `ads_read`.** Spec/README em `docs/superpowers/specs/2026-08-04-*`. |
| 6.4 | [Revy Tráfego × Portal loja](2026-07-28-plano-revy-trafego-separacao.md) | App gestor multi-loja + slim resultados no portal | **FASE 3 pronta**: banco próprio, projeção de vendas e outbox; arquitetura no as-built e operação em `deploy/fly/3vm/` |
| 6.5 | [Revy Control](2026-07-29-plano-revy-control.md) | Lojas, RBAC, módulos, Google Ads, integrações, auditoria e Multi-WhatsApp | **CÓDIGO PRODUTO COMPLETE** — workers outbox/métricas Google, reconcile status, HTTP adapters, UI/API aquisição, multi-WA n8n; residual = GCP humano + lab F7/E2E |
| 6.5b | [PR-4 identidade loja / memberships](2026-07-31-pr4-identidade-loja-fase-b-memberships.md) | Dono multi-loja por convite (identidade da loja, fase B) | **IMPLEMENTADO** (`cd9e4f0`) — memberships + convite de dono |
| 6.6 | [Revy Loja](2026-07-29-plano-revy-loja.md) | Portal → Vendas + Estoque; Atendimento, Chatbot, Multibanco e Seller AI | **CÓDIGO F0–F6+F8 COMPLETE (lean)** — shell, overviews, atendimento multi-canal, equipe, bancos, fixtures contratos; **F7 Seller AI deferred**; residual = lab ops only |
| 6+ | [Plano #6](2026-07-11-plano6-evolucoes-roadmap.md) | Roadmap histórico de ideias | Entregas antigas continuam válidas; itens ainda “ativos” exigem revalidação em Control/Loja |
| ops | [Arquitetura 3 VMs](2026-07-21-plano-arquitetura-3-vms.md) | Consolidação Fly (custo) | **IMPLEMENTADO / OPERANDO** — `suite-pg` + `evolution2037` + `app2037` always-on; `motor2037` Playwright on-demand; n8n webhook + roteamento 3 casos; ops = `deploy/fly/3vm/` + `up-all.sh --3vm` |
| ops | [Runbook rollout lab / provisionamento](2026-07-29-runbook-rollout-lab-provisionamento.md) | Subida do lab + provisionamento | Procedimento operacional; usar junto de `deploy/fly/3vm/README.md` |
| ops | [Menu estoque WA + fixes foto](2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md) | Cadastro/menu/fotos prod | **CÓDIGO DONE** — próximo: E2E menu/cadastro, depois cliente novo |

Planos #1A e #4A podem avançar em paralelo após #0. #2A depende da fatia Lite do #4A.
Numeração é histórica; não obriga Portal antes de Estoque/Catálogo.

## Execução ativa — Control × Loja

As fases dos dois planos são gates, não duas filas completas em sequência:

| Corte | Revy Control | Revy Loja | Resultado liberado |
|---|---|---|---|
| Fundação | 0–2 | 0 e preparação visual | loja, identidade, cargos e entitlements confiáveis |
| MVP comercial base | 3 | 1–5 | Vendas + Estoque, dashboard, Atendimento e Multibanco; Meta atual |
| Google Ads | 4 | resumo na Fase 3 | leitura, atribuição e conversões Google |
| Multi-WhatsApp | 5 | 6 | vários números equivalentes, conversa pelo canal correto |
| IA comercial | — | 7 | follow-ups, propostas e Seller AI sobre Atendimento estável |
| Consolidação | 6–7 | 8 | dashboards finais, rollout e limpeza |

Control 4 e 5 são independentes entre si. O primeiro MVP comercial não precisa esperar
Google ou Multi-WhatsApp se essas capacidades não fizerem parte do escopo piloto;
integração ausente deve aparecer como indisponível, nunca como resultado zero.

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

## Estrutura comercial futura

A estrutura canônica está em [`docs/README-COMERCIAL.md`](../README-COMERCIAL.md):

- **Revy Control:** superfície administrativa/técnica e de aquisição;
- **Revy Loja:** produto operacional único;
- **Vendas e Estoque:** únicos módulos principais contratáveis;
- Chatbot, Seller AI e Simulação Multibanco: capacidades embutidas em Vendas;
- Catálogo Público: saída do Estoque.

Os nomes de pacotes standalone dos planos antigos são históricos e não devem orientar
o novo menu ou a arquitetura comercial.

## Arquivo (não executar)

Tudo em [`_archive/`](_archive/) é **histórico** — não define arquitetura nem ordem de implementação.

| Arquivado | Por quê / ler em vez disso |
|---|---|
| Planos monolíticos #1–#5 (2026-07-11) | Substituídos pelos `*A` / `*B` |
| `…-santander-implementacao.md` | Checklist DONE; usar **lições** + **design** Santander |
| `…-bradesco-implementacao.md` / `…-pan-playwright-implementacao.md` | Checklists DONE; usar mapa de bancos + código + lições |
| `…-plano7-deploy-fly-io-implementacao.md` | 1ª subida Fly já feita; ops = `deploy/fly/3vm/` + arquitetura 3-VM |
| `…-fontecred-deploy-handoff.md` | SUPERSEDED; usar **lições Fontecred** |
| `…-multi-whatsapp-vendedores-campanhas.md` (2026-08-04) | SUPERSEDED pelo Revy Control (Fase 5 multi-WhatsApp) |
| `…-plano7-deploy-fly-io-design.md` (2026-08-04) | DONE; superado pela arquitetura 3-VM + `deploy/fly/3vm/` |
