# Handoff técnico

Só o checkpoint. Narrativa de entrega fica no Git e em
[`../nao-plano/historico/`](../nao-plano/historico/).

O bloco **29/08** abaixo é o recente. O resto do checkpoint é de **2026-08-13** e
envelheceu em partes — onde ele contradiz o
[`contexto-compacto.md`](contexto-compacto.md), o contexto compacto vence.

Leia primeiro:

1. [`contexto-compacto.md`](contexto-compacto.md) — estado e prioridades
2. [`../fila/README.md`](../fila/README.md) — o que ainda é código
3. [`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) — as-built

## Checkpoint de 2026-08-29 — Embedded Signup

Tudo no `main` e **no ar** (`app2037` sha `ce4e2ab`). Suítes: chatbot **667**,
portal **1412**.

- **O onboarding assistido do Modo 2 não roda.** Tocar a WABA de um cliente exige
  Advanced Access, que só sai por App Review. **Submetido em 29/08, sem resposta.**
  Enquanto não sair, nenhuma loja nova conecta — é o gate de tudo.
- **A cadeia inteira existe no Chatbot:** `app/meta_onboarding.py` (os quatro elos),
  `app/onboarding_cloud.py` (ordem, retomada, teto), `app/segredo_canal.py` (Fernet,
  fail-closed), migration `0028`, a rota `POST /v1/whatsapp/canais/cloud/onboarding`
  e o `/webhook/cloud` entendendo o status do template.
- **A Loja tem as telas:** decisão (`/app/loja/whatsapp/conectar`), popup do SDK,
  rótulos `cloud_*` e o passo em que o onboarding parou.
- **O botão do popup está desabilitado e acende sozinho** quando
  `PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID` entrarem no `[env]`. Nenhum código
  muda no dia da liberação.
- **Duas armadilhas caras:** registrar número tem teto de 10 por número em 72 h
  móveis — estourar deixa o cliente três dias sem WhatsApp, e por isso o código para
  em 5 e não tem retry automático. E o template `chama_vendedor` foi reclassificado
  para `MARKETING` (≈10x o custo), com prazo de contestação até **22/10/2026**.
- **Sem prova:** o JS do popup nunca rodou em navegador.
- Não existem ainda: tela de templates (§10.4), visão no Control (§14.5) e o spike
  contra a Meta de verdade.

## Checkpoint de 2026-08-13 (o que o `main` tinha então)

- **Copiloto F1–F4** no Portal: `app/loja/copiloto/`, `app/web/loja_copiloto.py`,
  workers `copiloto_sinais_job` e `copiloto_purge_job`. 7 regras em `SINAL_REGRAS`.
  Migrations Portal `0021`–`0023`. Control provisiona o módulo (`0018_copiloto_modulo`).
  Flag `REVY_LOJA_COPILOTO_ENABLED` default OFF. F5 e F6 não começaram.
- **Marca unificada** nos quatro front-ends: `shared/brand/revy-tokens.css` é a fonte
  única; acento verde racing; `app.css` não reabre `:root`. Detalhe da entrega:
  [`planos/2026-08-08-identidade-visual-revy.md`](planos/2026-08-08-identidade-visual-revy.md).
- **CTWA/ROI:** Graph `ad_id→campaign_id`; venda herda campanha do lead na leitura.
  Nunca casar por telefone mascarado. Task 4 = config de anúncio.
  [`planos/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md`](planos/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md).
- **Alerta de simulação:** outbox `notificacoes_operacionais` + worker no lifespan
  do Chatbot. Residual é smoke, não código.
- **n8n:** canônico `n8n/workflow-ai-nao-salvos.json` (**32 nós** no Git). Live
  `wAiNaoSalvos0001` na última inspeção (2026-08-04) estava **inativo/draft**.
  Teste `workflow-teste-numero-autorizado.json` separado e OFF.
- **WhatsApp dois modos:** spec pronta, sem plano e sem código. Coexistência por
  vendedor removida de propósito.
- Seller AI adiado. Foto por arquivo e sino geral (fora do Copiloto) não existem.
- `venda_projetada.loja_id`: corrigido no código (`projetar_venda` + migration
  `0017_vendas_projetadas_backfill_loja_id`). No deploy, `alembic upgrade head`
  no Revy senão KPI de venda antiga fica zero.

## Estado operacional

Topologia (desde 2026-07-31):

| App | Papel | Região |
|---|---|---|
| `suite-pg` | Postgres | `iad` |
| `app2037` | bundle APIs/UI/site | `iad` |
| `evolution2037` | WhatsApp | `iad` |
| `n8n2037` | orquestração | `iad` |
| `motor2037` | Playwright sob demanda | `gru` (não mover) |

Piloto `app2037`: shell + entitlements + atendimento + WhatsApp Loja **ON**;
redirect legado **OFF**; Copiloto **OFF** até ops ligar secret + entitlement.

Não recriar apps monolíticos. Não destruir volume/snapshot sem pedido.
Não rodar `n8n list:workflow` via SSH no volume de prod (trava SQLite).

Detalhe de start/import: `deploy/fly/3vm/README.md`.

## Pendências reais

- **Copiloto:** F5 e F6 (ver fila). Ligar em prod é ops (flag + módulo + chave LLM).
- **Foto de veículo** e **sino geral + simulação pronta** — cards na fila.
- **Motor:** worker PC (gate = probe Bradesco); estabilidade Bradesco; smokes reais.
- **Bot:** smoke virgem/CTWA/handoff/salvo → Active ON só pelo dono.
- **Control:** Google Ads (secrets GCP); E2E dois canais WA; projeção de metas
  Portal→Control (diferida).
- **CTWA Task 4:** `Cód:` na mensagem pré-preenchida do anúncio.
- **Loja:** `REVY_LOJA_REDIRECT_LEGACY` ainda OFF (dual-path); espaçamento das
  telas novas em fila visual separada; card Simulações no Agente é placeholder.
- **n8n:** áudio no Git = ignorado; `findChats`/`@lid` ainda frágeis; enxugar nós adiado.
- Conferência visual consolidada dos dois temas (pós-varredura de marca) antes de
  tratar a marca como “fechada em prod”.

## Segurança

- Não ler, copiar ou versionar `.env`, `.secrets.local`, chaves Evolution, tokens
  ou `storage_state` do Motor.
- `*.ready.json` e screenshots de portal bancário são efêmeros.
- `REVY_LOJA_COPILOTO_LLM_KEY` nunca entra no `[env]` do `fly.toml` nem no git.

## Próximo handoff

Atualize só este checkpoint, `contexto-compacto.md` e `docs/fila/README.md`.
Se um card da fila entrou no `main`, **mova** o arquivo para
`docs/referencia-viva/planos/` no mesmo PR. Não acrescente novela de entrega aqui.
