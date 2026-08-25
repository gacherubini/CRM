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
| [Catálogo do bot por loja](2026-08-25-catalogo-por-loja.md) | Estoque / Chatbot / n8n | `GET /v1/config/catalogo-bot` é cega para loja: com duas lojas no Modo 2, o cliente de uma recebe o link da vitrine da outra — sem erro e sem log. **Não é pesquisa, é decisão do dono**: o card compara as três saídas com o custo de cada uma e recomenda uma. Só morde com a segunda loja Modo 2. |
| [Postgres 2 — o corte](2026-08-16-postgres-2-corte.md) | Loja / Control / Deploy | Portal e Control ainda rodam **SQLite em arquivo** no volume do `app2037`. O card leva os dois para o banco `revy` no `suite-pg`, com schema e role por produto. Traz ferramenta com teste (pré-voo, carga, validação) e o runbook do corte com caminho de aborto. **Ler o spec junto.** |
| [Postgres 1 — concorrência](2026-08-16-postgres-1-concorrencia.md) | Loja | Três "lê-depois-escreve" viram transições atômicas. Só o rate-limit de ações vaza hoje; o resto é **pré-requisito do segundo processo**, não do corte. Independente do card acima — qualquer ordem. |
| [Modo 2 — humanização da entrega](2026-08-24-modo2-humanizacao-da-entrega.md) | n8n | **Encolheu em 24/08.** A Task 1 saiu: o "digitando…" da Cloud API está no `chatbot-api` e não precisou do `delay` do Modo 1 — na API oficial não há anti-ban a imitar. Restam o filtro que minuscula URL e `Cód:` (Task 2) e o tom, que é decisão do dono (Task 3). |
| [Piloto Modo 2 — fechamento](2026-08-14-wa-modo2-fechamento-piloto.md) | Chatbot / n8n / Motor | Sobrou **um** débito técnico: a migration `0017` não aplica em SQLite, então a chain nunca rodou de zero (produção é Postgres e nunca reclamou). O teste de outbox duplicado **já foi corrigido**. O resto é roteiro operacional da Meta e do n8n que o código não faz sozinho. |
| [Copiloto F5 — log e isolamento](2026-08-12-copiloto-fase5-log-de-perguntas-e-isolamento.md) | Loja / Control | Parte A: endpoint no Portal + tela no Control com as perguntas-lacuna. Parte B: RLS no Postgres — **bloqueada**, o Portal roda SQLite e SQLite não tem RLS; destrava com o card do corte. Independentes. |
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
| Modo 2 — metade do dono (Card 5) | **No `main`.** `GET /v1/ofertas` e `POST /v1/ofertas/{id}/assumir` (`chatbot-api/app/main.py`), produtor do sinal no `copiloto_sinais_job`, botão Peguei no sino, faixa "N sem vendedor" e card de 7 dias (`portal-gestao/app/loja/routes.py`). Lead que ninguém pega **não some mais**. Plano em `../referencia-viva/planos/`. |
| Modo 2 — multi-loja por credencial de integração | **No `main`** (`654f5d4`, migration `0026_credencial_integracao`). Falta a central Cloud da segunda loja, que é ops. Plano em `../referencia-viva/planos/`. |
| Foto de veículo / sino geral / sino 1:1 | **No código.** Upload por arquivo no form de estoque, `regras_elegiveis` por tipo, e `destinatario_usuario_id` em `copiloto_sinal`. Planos em `../referencia-viva/planos/`. |
| WhatsApp dois modos | **Código da Fase 1 inteiro no `main` da branch**, com flags OFF. Spec em [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md); os 7 cards executados em [`../referencia-viva/planos/`](../referencia-viva/planos/). Resta o card de fechamento (Meta + n8n + débitos). |
| Multi-WhatsApp E2E / Google Ads | Residual de Control (secrets + lab), não é plano novo. |
| CTWA Task 4 | Configuração de anúncio (`Cód:` na mensagem), não código. |
| Seller AI (Loja F7) | Adiado. `SELLER_AI_ENABLED` não altera rotas. |

Agente: abra **um** card. Se o arquivo passar de ~200 linhas, leia só Global Constraints + a Task da vez.
