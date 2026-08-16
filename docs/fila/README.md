# Fila

Só o que ainda produz trabalho. Um eixo por mudança. Código e testes vencem o
Status escrito no card.

Fonte de estado: [`../referencia-viva/contexto-compacto.md`](../referencia-viva/contexto-compacto.md).

Como classificar: se o símbolo já existe no `main` (módulo, rota, migration), o
card vai para `docs/referencia-viva/planos/` — mesmo que falte smoke ou merge de
deploy. Ops sem código novo não ganha card.

## Cards de código

| Card | Produto | O que falta no `main` |
|---|---|---|
| [Modo 2 / Card 5 — a metade do dono](2026-08-14-wa-modo2-5-loja-visao-do-dono.md) | Chatbot / Loja | A ponte que ficou no vão entre os planos por produto: rotas de oferta no chatbot, sino 1:1 com botão Peguei, faixa "N sem vendedor" e card de 7 dias. Sem isto, **lead que ninguém pega some**. |
| [Piloto Modo 2 — fechamento](2026-08-14-wa-modo2-fechamento-piloto.md) | Chatbot / n8n / Motor | Débitos técnicos (migration 0017 no SQLite, teste de outbox duplicado) + o roteiro operacional da Meta e do n8n que o código não faz sozinho. |
| [Copiloto F5 — log e isolamento](2026-08-12-copiloto-fase5-log-de-perguntas-e-isolamento.md) | Loja / Control | Parte A: endpoint no Portal + tela no Control com as perguntas-lacuna. Parte B: RLS no Postgres. Independentes. |
| [Copiloto F6 — cadastro e funil](2026-08-12-copiloto-fase6-cadastro-e-funil.md) | Loja | Ferramentas `cadastro_incompleto` e `funil_resumo` no registro MCP. A regra de sinal `cadastro_incompleto` **já existe** (F1) — isto é consulta no chat. Simulação de financiamento foi **retirada**. |
| [Worker Playwright no PC](2026-08-12-worker-playwright-pc-local.md) | Motor | Design aprovado, sem código de orquestração PC×Fly. Gate: `scripts/probe_bradesco.py` no IP residencial. |
| [Estabilidade Bradesco](2026-07-24-plano-estabilidade-bradesco-playwright.md) | Motor | Backlog priorizado. Driver existe; falha recorrente é captcha/IP. |
| [Drivers resilientes](2026-07-21-plano-drivers-resilientes.md) | Motor | Backlog. |
| [Rebuild do site](2026-08-09-plano-site-rebuild-html-estatico.md) | Site | **Adiado.** Export do design tool + `apply-seo` seguem em uso. |

## Sem card (não inventar plano)

| Tema | Estado real |
|---|---|
| Copiloto F1–F4 | **No `main`.** Chat, 7 regras, FIPE, ações com confirmação/desfazer, sino do Copiloto. Flag `REVY_LOJA_COPILOTO_ENABLED` default OFF. Planos em `docs/referencia-viva/planos/`. |
| Alerta no grupo de estoque | **Código pronto** (outbox + retry + dead-letter). Residual = smoke e Active ON. **Fica** no Modo 1; não aposentar. |
| Foto de veículo / sino geral / sino 1:1 | **No código.** Upload por arquivo no form de estoque, `regras_elegiveis` por tipo, e `destinatario_usuario_id` em `copiloto_sinal`. Planos em `../referencia-viva/planos/`. |
| WhatsApp dois modos | **Código da Fase 1 inteiro no `main` da branch**, com flags OFF. Spec em [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md); os 7 cards executados em [`../referencia-viva/planos/`](../referencia-viva/planos/). Resta o card de fechamento (Meta + n8n + débitos). |
| Multi-WhatsApp E2E / Google Ads | Residual de Control (secrets + lab), não é plano novo. |
| CTWA Task 4 | Configuração de anúncio (`Cód:` na mensagem), não código. |
| Seller AI (Loja F7) | Adiado. `SELLER_AI_ENABLED` não altera rotas. |

Agente: abra **um** card. Se o arquivo passar de ~200 linhas, leia só Global Constraints + a Task da vez.
