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
| [Copiloto F5 — log e isolamento](2026-08-12-copiloto-fase5-log-de-perguntas-e-isolamento.md) | Loja / Control | Parte A: endpoint no Portal + tela no Control com as perguntas-lacuna. Parte B: RLS no Postgres. Independentes. |
| [Copiloto F6 — cadastro e funil](2026-08-12-copiloto-fase6-cadastro-e-funil.md) | Loja | Ferramentas `cadastro_incompleto` e `funil_resumo` no registro MCP. A regra de sinal `cadastro_incompleto` **já existe** (F1) — isto é consulta no chat. Simulação de financiamento foi **retirada**. |
| [Foto de veículo no Portal](2026-08-12-foto-veiculo-upload-portal.md) | Loja / Estoque | Upload por arquivo no form legado. Vale nos dois modos WA: no 1 é atalho; no 2 é o único jeito de publicar. Grupo do Modo 1 **não** some. |
| [Modo 2 / Card 1 — sino por pessoa](2026-08-13-wa-modo2-1-loja-sino-por-pessoa.md) | Loja | Coluna `destinatario_usuario_id` em `copiloto_sinal` + filtro na leitura + criar/transferir oferta. **Depende do B1.** Botão Peguei e fila de vendedores ficam para depois do card do chatbot. |
| [Central de notificação (B1)](2026-08-12-notificacao-central-simulacao-pronta.md) | Loja | Sino geral + elegibilidade **por tipo**. **Sem** blast `simulacao_pronta` e **sem** aposentar o grupo (spec dos dois modos). Elegibilidade **por pessoa** (destinatário) não entra aqui — precisa migration, fica no plano dos dois modos. |
| [Worker Playwright no PC](2026-08-12-worker-playwright-pc-local.md) | Motor | Design aprovado, sem código de orquestração PC×Fly. Gate: `scripts/probe_bradesco.py` no IP residencial. |
| [Estabilidade Bradesco](2026-07-24-plano-estabilidade-bradesco-playwright.md) | Motor | Backlog priorizado. Driver existe; falha recorrente é captcha/IP. |
| [Drivers resilientes](2026-07-21-plano-drivers-resilientes.md) | Motor | Backlog. |
| [Rebuild do site](2026-08-09-plano-site-rebuild-html-estatico.md) | Site | **Adiado.** Export do design tool + `apply-seo` seguem em uso. |

## Sem card (não inventar plano)

| Tema | Estado real |
|---|---|
| Copiloto F1–F4 | **No `main`.** Chat, 7 regras, FIPE, ações com confirmação/desfazer, sino do Copiloto. Flag `REVY_LOJA_COPILOTO_ENABLED` default OFF. Planos em `docs/referencia-viva/planos/`. |
| Alerta no grupo de estoque | **Código pronto** (outbox + retry + dead-letter). Residual = smoke e Active ON. **Fica** no Modo 1; não aposentar. |
| WhatsApp dois modos | Spec fechada em [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md). Plano de implementação ainda não escrito. Plano quebrado em 4 cards por produto. Card 1 (Loja/sino) escrito. Faltam: chatbot (fila + rodízio + bot), `n8n-cloud`, toggle no Control. |
| Multi-WhatsApp E2E / Google Ads | Residual de Control (secrets + lab), não é plano novo. |
| CTWA Task 4 | Configuração de anúncio (`Cód:` na mensagem), não código. |
| Seller AI (Loja F7) | Adiado. `SELLER_AI_ENABLED` não altera rotas. |

Agente: abra **um** card. Se o arquivo passar de ~200 linhas, leia só Global Constraints + a Task da vez.
