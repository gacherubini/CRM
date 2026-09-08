# Handoff técnico

Só o checkpoint. Narrativa de entrega fica no Git e em
[`../nao-plano/historico/`](../nao-plano/historico/).

O bloco **07/09** abaixo é o recente. O resto do checkpoint é de **2026-08-13** e
envelheceu em partes — onde ele contradiz o
[`contexto-compacto.md`](contexto-compacto.md), o contexto compacto vence.

Leia primeiro:

1. [`contexto-compacto.md`](contexto-compacto.md) — estado e prioridades
2. [`../fila/README.md`](../fila/README.md) — o que ainda é código
3. [`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) — as-built

## Checkpoint de 2026-09-08 — o popup abriu de verdade, e o corte do chip tem plano

`main` em **`0360f14`**. `app2037` segue no ar em `a24ad91` (o commit de hoje e script +
docs, nada que exija deploy). Suite do chatbot: **677** (eram 667).

### O popup do embedded signup ABRIU

Faltava um **terceiro** campo de OAuth, na mesma tela dos dois de ontem
(`/apps/1370395535203964/business-login/settings/`): **"URIs de redirecionamento do OAuth
validos"**, que estava **vazio** com **"Usar modo estrito" ligado** — e modo estrito com
lista vazia nao deixa nenhum redirect passar. Preenchido com `https://app2037.fly.dev/`, o
validador da Meta ficou verde e a janela abriu em *"Conecte sua conta facilmente a Revy"*.

**Armadilha que custou duas tentativas:** no campo de URIs, o Enter cria o chip e dispara
um toast verde *"As alteracoes foram salvas"* que **mente**. Quem salva e o botao
**"Salvar alteracoes"** no rodape, abaixo da dobra, encoberto pelo proprio toast. Confira
sempre com o validador do topo da pagina **depois de um reload**.

Detalhe em `.claude/skills/revy-research/learnings/2026-09-07-o-config-id-nao-basta-para-o-popup-abrir.md`
(reescrito hoje: eram tres campos, nao dois).

### Descartado no caminho, para ninguem reabrir

- **`v21.0` do `FB.init` nao e problema.** O app esta em v26.0 nas duas caixas de
  "Atualizar a versao da API", mas v21.0 so sai do ar em **21/01/2027**.
- **`public_profile` em "Pronto para teste" e pista falsa.** O Login for Business e regido
  pelo `config_id`, que substitui o `scope`. Nao submeter para analise por causa disto.
- **O JS da Loja esta certo.** `whatsapp_decidir.html:201-219` manda `config_id`,
  `response_type: "code"`, `override_default_response_type` e `sessionInfoVersion: "3"`.
  O `response_type=code` visto na URL do popup prova que as opcoes chegaram ao SDK.
- O app **nao tem caso de uso de autenticacao** (so os dois de Ads e o de WhatsApp). Nao
  impediu o popup de abrir. Fica anotado, nao vira acao.

### Ainda por olhar

O alerta de App Review de 07/09 diz *"Further action may be required before your app can go
live… address any outstanding questions"*. A pagina de submissoes nao foi aberta. Como o
popup abriu, isto **nao e bloqueio** — mas continua sem leitura.

### O chip: um so, e ha plano escrito

O dono decidiu em 07/09 usar **um unico chip Vivo** para as duas fases: entra pelo popup na
loja `teste`, e depois vira para a loja real trocando `whatsapp_canais.loja_id`. WABA no
portfolio **do amigo**; a loja de destino **ja existe e ja opera Modo 1**; os dados do teste
sao **apagados** no corte.

- Spec + runbook das 5 fases: `docs/referencia-viva/specs/2026-09-07-um-chip-teste-depois-loja-real-design.md`
- Card: `docs/fila/2026-09-07-mover-canal-de-loja.md`
- Ferramenta pronta e testada: `chatbot-api/scripts/mover_canal_de_loja.py` (10 testes)

**A consequencia que nao e de codigo:** projetar `whatsapp_modo=2` na loja do amigo manda
**todo** o outbound dela pela Cloud, inclusive a resposta a quem escrever no numero
Evolution antigo. Marcar aquele canal como inativo nao segura
(`resolve_canal_for_instance` ignora `ativo`) — o numero velho tem de sair da Evolution no
corte.

## Checkpoint de 2026-09-07 — o App Review saiu e o popup abriu

`main` limpo, `app2037` no ar em **`a24ad91`**. `motor2037` continua em `ce4e2ab`
(os drivers Playwright novos subiram na API, nao no worker).

**O gate de 29/08 caiu.** App Review **aprovado em 07/09 11:18 GMT-3**, as duas
permissoes: `whatsapp_business_messaging` e `whatsapp_business_management`.

O que foi feito hoje, em ordem:

1. Criada a configuracao v4 do Login for Business pelo modelo *"cadastro incorporado
   do WhatsApp com token de expiracao em 60 dias"* → **`config_id 1092096256576691`**.
   (App ID `1370395535203964`, business_id `4040462592922875`.)
2. `PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID` no `[env]` do `fly.app.toml`
   (`a24ad91`), deployado e conferido: o botao da Loja **acendeu**.
3. O `FB.login` reprovou com *"A opcao JSSDK nao esta ativada"*. Faltavam dois campos
   que o §15 do spec nao previa, na tela de OAuth do app
   (`/apps/<id>/business-login/settings/`): **Entrar com o SDK do JavaScript = Sim** e
   **Dominios permitidos para o SDK do JavaScript = `https://app2037.fly.dev/`**.
   Ligados, salvos — e **a janela da Meta passou**.

Detalhe em `.claude/skills/revy-research/learnings/2026-09-07-o-config-id-nao-basta-para-o-popup-abrir.md`.

### Duas horas que nao se repetem

- **"Pronto para publicar" NAO e gate.** E o rotulo das permissoes aprovadas no caso
  de uso. Nao existe botao de publicar permissao: a pagina `Publicar`
  (`/apps/<id>/go_live/`) so oferece "Tirar do ar" (o app ja esta no ar desde 23/08) e
  o menu Acoes da permissao so oferece "Reduzir o acesso" — que so existe para quem ja
  esta no nivel de cima. Procurar esse botao custou boa parte da noite.
- **O "60 dias" do modelo nao morde.** O token do popup fica em `token_cifrado` e so os
  elos de `onboarding_cloud.py` o usam; o envio do dia a dia usa `CHATBOT_GRAPH_TOKEN`.
  Expirar so significa que uma retomada muito atrasada pede popup de novo.
- **"Recurso indisponivel — o Login do Facebook esta indisponivel para ele no momento"**
  apareceu ~2 h depois, com a janela ja tendo passado. Nao ha acao pendente
  (`Ações necessárias`: a unica, Verificacao de Uso de Dados, esta **Concluida em
  07/09**) e nada nos 5 alertas indica restricao. Leitura: propagacao da propria
  mudanca de OAuth. **Tentar de novo mais tarde antes de mexer em qualquer coisa.**

### O que continua sem prova

- **Os quatro elos nunca falaram com a Graph de verdade.** Inscrever app na WABA,
  registrar numero, criar template: so mock. E o risco concentrado.
- Os **tres caminhos de desistencia** do popup nao foram exercitados.
- Teto do elo 3: paramos em 5 tentativas; a Meta trava o numero por **3 dias**.
  **A primeira conexao tem de ser num chip descartavel, nunca no do cliente.**

### Depois que uma loja conectar (nada disto e codigo)

Canal nasce `pendente`. Liberar no Control (projetar `whatsapp_modo=2`), cadastrar a
fila de vendedores, esperar a Meta aprovar o template na WABA dela.

### Estado da loja `teste` (conferido em prod, 07/09)

Projecao: `('teste','loja','ativa')` e `('teste','whatsapp_modo','2')`. As tres
condicoes de `rodizio.loja_opera_modo2` passam; a tela do Agente renderiza o
interruptor de follow-up (so existe no Modo 2) e a de Numeros mostra o card de nuvem.
**A Loja nunca escreve "Modo 2"** — mostra o efeito, nao o nome. Divida viva: o
cabecalho da tela de Numeros ainda fala de QR mesmo em loja Cloud.


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
