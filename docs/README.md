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

