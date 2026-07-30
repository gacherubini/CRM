# Handoff técnico

Atualizado em **2026-07-30**. Este arquivo registra somente o checkpoint atual.
Histórico detalhado permanece no Git; não acumular “checkpoints anteriores” aqui.

Leia primeiro:

1. [`contexto-compacto.md`](contexto-compacto.md) — estado, prioridades e regras.
2. [`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) — arquitetura implementada.
3. [`plans/README.md`](plans/README.md) — índice e status dos planos.

## Checkpoint de código

- Revy Control lean F0–F6 está implementado em `revy-trafego`.
- Revy Loja lean F0–F6/F8 está implementado em `portal-gestao`.
- Seller AI permanece adiado e desligado.
- O Portal foi modularizado: simulações, metas, equipe e tráfego/campanhas ficam em
  `portal-gestao/app/web/`; `main.py` mantém bootstrap e rotas legadas restantes.
- O workflow canônico continua `n8n/workflow-ai-nao-salvos.json`.
- O workflow `n8n/workflow-teste-numero-autorizado.json` é usado para testes e não deve
  ser removido.

## Validação conhecida

- Refatoração do Portal: **439 testes passando**.
- `git diff --check` e compilação dos módulos extraídos passaram no corte da refatoração.
- Contagens antigas de outros produtos foram removidas deste handoff; rode a suíte atual
  do produto modificado antes de publicar.

## Estado operacional

O repositório não é fonte confiável para afirmar que uma Machine Fly está ligada neste
instante. Antes de qualquer ação:

1. consulte `deploy/fly/3vm/README.md`;
2. verifique `fly status` dos apps envolvidos;
3. confira migrations/readiness e logs sem imprimir segredos;
4. use deploy com contexto na raiz do repositório.

Arquitetura esperada do lab:

- `suite-pg`: banco;
- `evolution2037`: canal WhatsApp;
- `app2037`: bundle de APIs/UI/site;
- `n8n2037`: orquestração;
- `motor2037`: workers Playwright sob demanda.

Não recriar apps monolíticos legados e não destruir volumes/snapshots sem pedido explícito.

## Pendências reais

- Rollout das flags Control/Loja em uma loja piloto com projeção e gates observados.
- E2E Multi-WhatsApp com dois canais Evolution e resposta pelo canal correto.
- Configuração humana do Google Ads/GCP e smoke OAuth/métricas/conversões.
- Smoke real dos quatro bancos, incluindo sessão quente e limite de concorrência.
- Restore drill dos bancos/volumes.
- Fechar deep-links de simulação e venda dentro do workspace de Atendimento.
- Atualizar o Graphify após mudanças estruturais antes de usá-lo como índice.

## Segurança

- Não ler, copiar ou versionar `.env`, `.secrets.local`, chaves Evolution, tokens ou
  `storage_state` do Motor.
- Workflows `*.ready.json` são gerados localmente e podem conter tokens reais.
- Screenshots de portais bancários podem conter dados operacionais; trate como efêmeros.
- Integrações entre produtos são HTTP/eventos, nunca imports Python cruzados.

## Próximo handoff

Atualize somente as seções “Checkpoint de código”, “Validação conhecida” e “Pendências
reais”. Se precisar preservar narrativa histórica, use commit/PR ou um plano explicitamente
arquivado; não aumente este arquivo indefinidamente.
