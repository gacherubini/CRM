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
| [Componentes dos quatro produtos](2026-08-30-componentes-dos-quatro-produtos.md) | Arquitetura (skill `revy-research`) | Chatbot e Estoque já têm a camada de componente — caixa com `arquivo:linha` provando que existe, mais as arestas internas. **Catálogo, Motor, Control e Loja ainda mostram árvore de arquivo**: as caixas que têm são pasta (`app/web/`, `app/clients/`) e nenhum dos quatro tem uma única aresta interna. O card traz a receita que funcionou duas vezes, o ponto de partida já levantado por produto e as armadilhas — inclusive a que apaga a prova em silêncio. Na branch `arquitetura-viva`. |
| [Embedded Signup 1 — spike dos endpoints](2026-08-29-embedded-signup-1-spike-endpoints.md) | Meta / pesquisa | **Bloqueado pelo App Review.** A cadeia dos quatro elos foi escrita a partir da doc e **nunca rodou contra a Meta de verdade** — o spike confirma a sequência e os formatos de corpo. Cuidado: o elo que registra o número tem custo irreversível de 72 h, então o card limita as tentativas. Não é card de código. |
| [Postgres 2 — o corte](2026-08-16-postgres-2-corte.md) | Loja / Control / Deploy | Portal e Control ainda rodam **SQLite em arquivo** no volume do `app2037`. O card leva os dois para o banco `revy` no `suite-pg`, com schema e role por produto. Traz ferramenta com teste (pré-voo, carga, validação) e o runbook do corte com caminho de aborto. **Ler o spec junto.** |
| [Postgres 1 — concorrência](2026-08-16-postgres-1-concorrencia.md) | Loja | Três "lê-depois-escreve" viram transições atômicas. Só o rate-limit de ações vaza hoje; o resto é **pré-requisito do segundo processo**, não do corte. Independente do card acima — qualquer ordem. |
| [Mensagem de tool vaza para o cliente](2026-08-26-mensagem-de-tool-vaza-para-o-cliente.md) | n8n / Chatbot | A tool `simular1` usa a mesma chave `mensagem` para treze ramos, e só dois são texto de cliente — o modelo copia instrução interna para o WhatsApp. O núcleo Revy repete a ambiguidade, então o conserto é nos dois produtos. **Medido: 22 vezes em 20 dias, 19 clientes seguiram a conversa mesmo assim** — não é urgente, mas cai logo depois do CPF. Tem tasks prontas para agente (§7). |
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
| Embedded Signup — cadeia, telas e segredos (Cards 2, 3 e 4) | **No `main` e no ar** (`app2037` sha `ce4e2ab`, 29/08). Chatbot: os quatro elos, a retomada, o teto do registro, os segredos cifrados, a rota `POST /v1/whatsapp/canais/cloud/onboarding` e o webhook do status do template. Loja: tela de decisão, popup do SDK, rótulos Cloud e o passo em que o onboarding parou. **O botão do popup está desabilitado** até `PORTAL_META_CONFIG_ID` existir — e ele acende sozinho, sem mudar código. Falta **clicar o popup no navegador**: o JS nunca rodou. Cards em [`../referencia-viva/planos/`](../referencia-viva/planos/), spec em [`../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`](../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md). |
| Embedded Signup — tela de templates e visão no Control | **Não existem.** São os itens 4 e 5 da ordem de execução do spec (§14) e ainda não viraram card: os dois esperam o App Review, que é o gate de tudo. |
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
