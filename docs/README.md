# Docs

Três pastas. O agente não varre `docs/` — escolhe **uma**.

| Pasta | O que é | Quando abrir |
|---|---|---|
| [`fila/`](fila/README.md) | Trabalho que ainda produz código ou config | Implementar um card |
| [`referencia-viva/`](referencia-viva/) | Verdade atual (estado, as-built, specs, planos DONE) | Entender o que já existe |
| [`nao-plano/`](nao-plano/) | Marca, história, tutoriais, planos substituídos | Só se o humano pedir |

Regras do agente: [`../AGENTS.md`](../AGENTS.md). Brief de subagente: [`referencia-viva/agents/task-brief.md`](referencia-viva/agents/task-brief.md).

Plano novo → `fila/`. Spec ainda válida → `referencia-viva/specs/`. Plano feito que descreve o código → `referencia-viva/planos/`. Plano velho/substituído → `nao-plano/arquivados/`.

Quando um card entra no `main`, no mesmo PR: mover o arquivo, atualizar
`fila/README.md` e `referencia-viva/contexto-compacto.md`. Código vence o
bloco Status do plano.

## Arquitetura viva — o que foi construído (2026-08-30 a 31)

A arquitetura deixou de ser diagrama que alguém redesenha e virou **artefato
gerado**, do mesmo jeito que `mapa/*.md` já era:
`.claude/skills/revy-research/arquitetura.html`, por `gerar_arquitetura.py`.

Duas cenas navegáveis por zoom. **Arquitetura**: produto, componente e as
arestas entre eles — os seis produtos têm de 7 a 16 unidades de
responsabilidade, cada uma com `arquivo:linha` provando que existe.
**Schema**: mapa conceitual de banco — uma caixa por tabela, os atributos
dentro, e uma seta por chave estrangeira rotulada com a cardinalidade lida do
próprio SQLAlchemy.

A intenção mora em `arquitetura.py`, escrita à mão; o inventário vem do
`_frescor.json`. `rota` (407) e `template` (90) são **dispensadas** de
propósito, e `flag` (102) vira contagem: parede de ficha responde *quais
arquivos existem*, que não é a pergunta desta página.

Spec canônica, com o porquê de cada decisão e o que ficou aberto:
[`referencia-viva/specs/2026-08-30-arquitetura-viva-design.md`](referencia-viva/specs/2026-08-30-arquitetura-viva-design.md)
— a **§14** é o as-built e vence o resto do documento onde os dois divergirem.

**Conferir no navegador não é opcional**: sete defeitos desta página só
apareceram abrindo ela, e dois não deixavam rastro no console. Ver §14.8.

## Embedded Signup — o que foi construído (2026-08-29)

Spec canônica: [`referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`](referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md).

O onboarding assistido que a spec do Modo 2 descrevia **não roda**: tocar a WABA de um
cliente exige Advanced Access, que só sai por App Review. Descoberto em 29/08 tentando pôr
uma loja real no ar. O caminho passou a ser o lojista conectar sozinho, com a Revy como
Tech Provider.

| Card | Produto | O que entrou no código |
|---|---|---|
| 2 · canal, estado e segredos | Chatbot | Migration `0028`: `business_id`, `onboarding_elo`, `onboarding_erro`, `token_cifrado`, `pin_cifrado`, `registro_tentativas`. `app/segredo_canal.py` (Fernet, **fail-closed**). Projetar `whatsapp_modo=2` no Control passou a ativar o canal `cloud_pendente`. |
| 3 · a cadeia | Chatbot | `app/meta_onboarding.py` (os quatro elos que falam com a Graph, sem banco), `app/onboarding_cloud.py` (ordem, retomada, teto de 5 no registro), `POST /v1/whatsapp/canais/cloud/onboarding`, e o `/webhook/cloud` entendendo `message_template_status_update` — **sem rota nova**. |
| 4 · a tela | Loja / Chatbot | Tela de decisão (`/app/loja/whatsapp/conectar`), popup do SDK, rótulos dos estados `cloud_*`, o passo em que o onboarding parou, e o erro de elo chegando como elo em vez de "chatbot indisponível". |

Planos em [`referencia-viva/planos/`](referencia-viva/planos/). O card 1 (spike contra a
Meta de verdade) continua em [`fila/`](fila/README.md).

**Nada disto conecta loja nenhuma ainda.** O App Review foi submetido em 29/08 e não teve
resposta; sem ele não há `config_id`, sem `config_id` o popup não abre. O botão está
desabilitado e **acende sozinho** quando `PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID`
entrarem no `[env]` — nenhum código muda. Faltam também a tela de templates (§10.4) e a
visão no Control (§14.5), que não viraram card.

**O JS do popup nunca rodou em navegador.** A lista do que precisa ser clicado está no fim
do card 4.

## Agente por loja — o que foi construído (2026-08-25)

Spec canônica: [`referencia-viva/specs/2026-08-24-agente-por-loja-design.md`](referencia-viva/specs/2026-08-24-agente-por-loja-design.md).
Antes disto existia **um** agente, com `vitor motos` e `limeira-sp` escritos à mão dentro
do `systemMessage` do n8n — a segunda loja se apresentaria como a primeira.

| Card | Produto | O que entrou no código |
|---|---|---|
| 1 · dado e texto | Chatbot | `agente_config` + `agente_config_versao` (0027), gerador de prompt por campo, núcleo Revy em código, rascunho/publicar/restaurar/histórico, liga-desliga por loja dentro do `pode_responder`. Plano em [`referencia-viva/planos/`](referencia-viva/planos/2026-08-25-agente-por-loja-1-dado-e-texto.md). |
| 2 · n8n | n8n / Chatbot | `systemMessage` virou expressão: operação literal no JSON, prompt da loja num slot no fim, terminando no núcleo. Nós `Buscar config do agente1` + `Gate config do agente1` (200 → loja · 423 → para · falha → padrão). Higienização da saída passou a obedecer a loja. Assertivas de prompt migradas para snapshots. |
| 3 · tela | Loja | `/app/loja/agente/configuracao`: formulário consciente do modo, autosave, aviso de conflito, publicar, histórico. |
| 4 · preview | n8n / Chatbot | `workflow-preview.json` gerado, nó-ponte `Extrair1`, telefone sintético e ferramentas em modo seco. `POST /v1/agente/preview`. |

**O cliente não sente nada disto ainda, e é decisão do dono** (25/08): ele quer
acompanhar o passo que muda o que o bot fala. Só o card 1 está deployado — as rotas
existem no `app2037` e ninguém as chama; o `n8n2037` roda o workflow anterior. A ordem do
rollout, com o efeito de cada passo, está em
[`../chatbot-api/README.md`](../chatbot-api/README.md), seção "O que falta" — e na skill
`revy-deploy`.

O que ficou **deliberadamente de fora** (modelo por loja, teto de tokens por loja,
cadência de follow-up, "só lead de anúncio", persona pronta) está em
`.claude/skills/revy-research/decisoes/2026-08-25-agente-por-loja-o-que-ficou-de-fora.md`.
Não re-propor.

## WhatsApp Modo 2 — o que foi construído (2026-08-12 a 14)

Spec canônica: [`referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md).
Sete planos executados, todos em [`referencia-viva/planos/`](referencia-viva/planos/):

| Plano | Produto | O que entrou no código |
|---|---|---|
| `2026-08-12-foto-veiculo-upload-portal` | Loja | Upload de foto por arquivo no form de estoque. O caminho pelo grupo continua. |
| `2026-08-12-notificacao-central-simulacao-pronta` | Loja | Sino geral: `regras_elegiveis` por tipo, worker independente da flag do Copiloto. |
| `2026-08-13-wa-modo2-1-loja-sino-por-pessoa` | Loja | `copiloto_sinal.destinatario_usuario_id` (0024): sinal endereçado a uma pessoa só. |
| `2026-08-13-wa-modo2-2-chatbot-fila-e-rodizio` | Chatbot | `fila_vendedor`, `oferta_lead`, ponteiro rotativo (0020/0021), trava idempotente, worker de 10 min, HTTP da fila. |
| `2026-08-13-wa-modo2-2b-chatbot-bot-e-mensagens` | Chatbot | Adapters Cloud (mídia pelo Graph, outbound com dois envelopes), três gatilhos, clique→trava, re-notificação, `FollowupWorker` (0022). |
| `2026-08-13-wa-modo2-3-n8n-cloud-e-webhook` | Chatbot / n8n | HMAC sobre corpo cru, parse do inbound Cloud, `/webhook/cloud`, `workflow-cloud.json` e validador. |
| `2026-08-13-wa-modo2-4-control-toggle` | Control / Chatbot | `lojas.whatsapp_modo` (0019), aggregate no snapshot, escolha na ficha, e a terceira cláusula do gate. |

**Todas as flags estão OFF.**

A **metade do dono da loja** — sino 1:1 com botão Peguei, faixa "N sem vendedor", filtro
Aguardando e card de 7 dias — **entrou no `main`**. O `chatbot-api` expõe `GET /v1/ofertas` e
`POST /v1/ofertas/{id}/assumir`, e `criar_sinal_direcionado` passou a ter chamador no
`copiloto_sinais_job`. Lead que ninguém pega **não some mais**. Plano em
[`referencia-viva/planos/2026-08-14-wa-modo2-5-loja-visao-do-dono.md`](referencia-viva/planos/2026-08-14-wa-modo2-5-loja-visao-do-dono.md).

O que falta fora de código (Meta, n8n, transcrição) está em
[`fila/2026-08-14-wa-modo2-fechamento-piloto.md`](fila/2026-08-14-wa-modo2-fechamento-piloto.md).

