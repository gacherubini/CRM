# Fila

Só o que ainda produz trabalho. Um eixo por mudança. Código e testes vencem o
Status escrito no card.

Fonte de estado: [`../referencia-viva/contexto-compacto.md`](../referencia-viva/contexto-compacto.md).
Não misture rollout, RPA e produto na mesma entrega.

## Cards

| Card | Produto | Nota |
|---|---|---|
| [Copiloto F3 — FIPE e ações](2026-08-11-copiloto-fase3-fipe-e-acoes.md) | Loja | Não iniciado. Depende da F2 mergeada. |
| [Copiloto F4 — notificações](2026-08-12-copiloto-fase4-notificacoes.md) | Loja | Não iniciado. Tasks 1–3 e 5 não dependem da F3. |
| [Copiloto F5 — log e isolamento](2026-08-12-copiloto-fase5-log-de-perguntas-e-isolamento.md) | Loja / Control | Não iniciado. Partes A e B são independentes. |
| [Copiloto F6 — cadastro e funil](2026-08-12-copiloto-fase6-cadastro-e-funil.md) | Loja | Não iniciado. |
| [Foto de veículo no Portal](2026-08-12-foto-veiculo-upload-portal.md) | Loja / Estoque | Upload por arquivo no form que já existe. |
| [Central de notificação + simulação pronta](2026-08-12-notificacao-central-simulacao-pronta.md) | Loja / Chatbot | Sino geral; não depende da flag do Copiloto. |
| [Alerta no grupo de estoque](2026-08-05-plano-alerta-grupo-estoque-simulacao.md) | Chatbot / n8n | F0–F2 no código; residual outbox/retry + smoke. |
| [Worker Playwright no PC](2026-08-12-worker-playwright-pc-local.md) | Motor | Design aprovado, sem código. Fase 0 (probe) é gate. |
| [Estabilidade Bradesco](2026-07-24-plano-estabilidade-bradesco-playwright.md) | Motor | Backlog priorizado. |
| [Drivers resilientes](2026-07-21-plano-drivers-resilientes.md) | Motor | Backlog. |
| [Rebuild do site](2026-08-09-plano-site-rebuild-html-estatico.md) | Site | Adiado. Export do design tool segue em uso. |

## Sem card (não inventar plano)

- Copiloto F2: implementado, **não mergeado em `main`**. Não é fila de escrever código.
- WhatsApp dois modos: spec em [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md); plano ainda não escrito.
- Multi-WhatsApp E2E e Google Ads: residual de Control, não é plano novo.
- CTWA Task 4: configuração de anúncio, não código.

Agente: abra **um** card. Se o arquivo passar de ~200 linhas, leia só Global Constraints + a Task da vez.
