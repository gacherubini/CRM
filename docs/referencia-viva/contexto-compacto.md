# Contexto compacto para continuidade

Atualizado em **2026-08-24**. Ponto de entrada de estado e prioridades.
Quadro: [`../README.md`](../README.md). Fila: [`../fila/README.md`](../fila/README.md).
Vocabulário: [`../../CONTEXT.md`](../../CONTEXT.md). As-built Control/Loja:
[`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md).

## Estado atual

- **Copiloto de Vendas (Loja):** F1–F4 no `main`. Seção própria no shell (dono/gerente),
  chat com LLM (DeepSeek, turno assíncrono), 7 regras de sinal (`estoque_parado`,
  `lead_sem_resposta`, `meta_em_risco`, `margem_incompleta`, `cadastro_incompleto`,
  `atribuicao_baixa`, `preco_fora_da_faixa`), FIPE, ações com confirmação e desfazer,
  sino do Copiloto. Kill-switch `REVY_LOJA_COPILOTO_ENABLED` (default **OFF**) **e**
  entitlement `Module.COPILOTO` (Control provisiona o módulo). F5 (log de lacunas no
  Control + RLS) e F6 (ferramentas de cadastro/funil no chat) **não** estão no código.
  Simulação de financiamento no Copiloto foi **retirada** (PII no prompt).
- **Revy Control:** F0–F6 no código. Copiloto é módulo contratável
  (`revy-trafego` migration `0018_copiloto_modulo`). Visão geral com filtro de período;
  Prontidão na ficha da loja; Integrações espelham a Loja. Google Ads e Multi-WhatsApp
  existem atrás de flag; falta secrets GCP e E2E de dois canais.
- **Revy Loja:** F0–F6/F8 + Atendimento (chat + poll), Perfil, Grupo do estoque, números
  WA, Vitrine unificada, funil clicável, página do Agente, bloco de aquisição por
  `ctwa_source_type`. Seller AI adiado. **Foto de veículo agora tem upload por arquivo**
  no form de estoque (o caminho pelo grupo continua). **Sino geral existe**
  (`regras_elegiveis` por tipo, independente do Copiloto) e aceita **destinatário por
  pessoa** (`copiloto_sinal.destinatario_usuario_id`, migration 0024).
  **Troca de loja consertada em 24/08:** o seletor era montado com as memberships do Control
  (3 lojas para o dono) e o `POST /app/loja/selecionar` autorizava só por `usuario.loja_slug`,
  então **2 das 3 opções do próprio seletor sempre caíam** em `/app?erro=loja-nao-autorizada`.
  Fonte única agora (`control_memberships_for`), com o cargo filtrado por `ROLES_OPERACIONAIS`
  para `admin_plataforma` não virar acesso de loja pela porta dos fundos. O `?erro=` também
  **não era renderizado em lugar nenhum** — agora a tela explica, sem detalhe interno.

- **WhatsApp Modo 2 (central Cloud API):** no `main`, **deployado e rodando em produção**.
  Placar do que existe e do que falta:
  [`design/2026-08-16-whatsapp-modo2-asbuilt.md`](design/2026-08-16-whatsapp-modo2-asbuilt.md).
  **Em 16/08 o `n8n-cloud` era um transporte de 4 nós — havia rodízio e handoff e nenhum bot
  respondendo o cliente.** Corrigido: o workflow virou fork gerado do Modo 1 (20 nós, com
  agente, ferramentas e debounce), `solicitar_handoff` passou a abrir o rodízio, e o retry
  da §6.1 saiu do `logger.exception` para uma tabela com worker.
  **Piloto de 23/08 (número de teste da Meta), o que PROVOU:** loja `teste` no Postgres do
  chatbot com as projeções `loja=ativa` e `whatsapp_modo=2` semeadas à mão (`version=1`, baixa
  de propósito para o Control sobrescrever sem ficar `stale`), um vendedor na fila,
  `loja_opera_modo2()` = `True`, as **três** flags do Modo 2 em `1`
  (`REVY_CONTROL_WHATSAPP_MODO2_ENABLED` + `CHATBOT_WHATSAPP_MODO2_ENABLED` +
  `MULTI_WHATSAPP_ENABLED`) e o `wCloudMeta0001` ativo no `n8n2037`. Cadeia com carimbo de log:
  `/webhook/cloud` 200 (loja resolvida pelo `phone_number_id`) → `pode-responder` 200 →
  `/v1/operacao/responder` **200 às 23:49:17 de 23/08**. O bot respondeu ao cliente de verdade.
  **A volta completa veio na madrugada de 24/08:** cliente pediu humano → rodízio ofereceu →
  vendedor tocou em "Peguei" → oferta `5034a589` em `estado=travada`, conversa do cliente com
  `bot_ativo=False` / `status=handoff`. Primeira vez desde o merge de 16/08 que um vendedor foi
  chamado, e saiu de graça (janela do vendedor aberta → `interactive`, sem tocar no template).
  **Segue sem prova:** fila com 2+ vendedores (ponteiro, 10 min, a volta que para), dois cliques
  concorrentes, re-notificação, follow-up, o caminho pago com janela fechada, e áudio.
  O piloto **não** está concluído.
  Três achados: (1) bug corrigido em prod (`922a365`) — `_wamid_ja_visto` chamava `.add()` de
  `set` num `OrderedDict`, alcançável só em reentrega pós-restart, e o 500 virava laço porque a
  Meta reentrega sem 200; suíte do `chatbot-api` verde. (2) template `chama_vendedor`
  reclassificado pela Meta de `UTILITY` para `MARKETING` e ainda `PENDING` — ~R$0,32 contra
  ~R$0,03–0,04, ~10× por oferta; contorno é mandar a oferta como `interactive` na janela de 24 h
  do vendedor. (3) allow-list do número de teste casa a string enviada e o `wa_id` brasileiro vem
  **sem o nono dígito** — cadastrar o número sem o 9; em número real não há allow-list.
  **Multi-loja: consertado e no ar em 24/08** (`654f5d4`). O workflow servia N lojas com
  o token de UMA, então o chatbot procurava a conversa na loja errada e o agente parava
  sem erro. Agora há credencial de `papel="integracao"` (sem loja) e toda rota do bot
  resolve a loja pela `instance` do pedido; sem ela é `400`, nunca um fallback. Card com
  o as-built e o que sobrou:
  [`../fila/2026-08-23-modo2-multiloja-credencial-de-integracao.md`](../fila/2026-08-23-modo2-multiloja-credencial-de-integracao.md). **Ainda não provado com duas lojas** — falta a central Cloud da segunda.
  Dívida conhecida, em ordem de risco: **VAD do áudio** (§5.10 — o Whisper alucina em ruído e o
  bot age em cima), **recusa não cutuca** (§5.9 r.5) e `classificar_etapa` presa em `so_oi`.
  **Noite de 24/08, ao preparar o teste com 2 vendedores, dois furos apareceram e foram
  corrigidos** (no ar, `app2037` v158): (a) a **reoferta do rodízio nunca era enviada** — o worker
  trocava o dono da oferta no banco e ninguém avisava o vendedor 2, e o teste só conferia a linha
  do banco; junto, a volta esgotada passou a avisar o cliente. O mesmo defeito de outbound
  quebrava o **follow-up do Modo 2**, que consertou de carona. (b) o **handoff falava duas vezes**
  (backend + agente) — a rota agora cala o backend, e a §5.3 mudou de dono: quem avisa o cliente
  é o agente, sem rede se o turno dele morrer.
  **Áudio ganhou gate de confiança (24/08), e o "digitando…" existe.** Até aqui o Whisper
  alucinava frase plausível em trecho mudo e o bot **agia** em cima; não havia checagem nenhuma
  de que houve fala. Agora o provider pede `response_format=verbose_json` e a transcrição é
  reprovada por `no_speech_prob > 0.6`, `avg_logprob < -1.0`, `compression_ratio > 2.4` (loop),
  frase de legenda conhecida, ou duração acima do teto — esta **depois** da transcrição, porque
  a Meta não manda duração no inbound (conferido no webhook e no `GET /{media_id}`). Reprovou,
  cai no fallback "manda por texto" que já existia. **Falha-abre de propósito:** provider sem os
  sinais volta a aprovar o texto — bot surdo em silêncio numa troca de fornecedor seria pior.
  Não é VAD sobre o sinal, e é deliberado: um VAD de energia aprovaria "moto passando", que é o
  exemplo da própria spec; e o gate pós é necessário de qualquer jeito. Groq configurado
  (`whisper-large-v3`, `temperature=0`); o `model` tem **default no código** porque esquecê-lo
  daria 400 em todo áudio, calado.
  **O "digitando…" do Modo 2** é `CloudWhatsAppOutbound.marcar_lido_e_digitando`, disparado do
  `pode-responder` — o instante em que o agente começa a pensar, para a latência real virar a
  janela do indicador. Não precisou do `delay` do Modo 1: na API oficial não há anti-ban a
  imitar, e o indicador da Cloud é chamada à parte que exige o `wamid` do cliente (que a rota
  já recebia como `provider_message_id`). Acende o **tique azul** junto, e não há como separar.
  Acender no `/webhook/cloud` não serviria: o debounce é de 40 s e o indicador morre em 25 s.
  **O bot fala igual ao do Baileys mas não soa igual:** o `systemMessage` é byte a byte o mesmo;
  o que divergiu é a entrega — o `Atraso anti-ban1` calcula o "digitando…" e o Modo 2 **descarta**
  o delay. Card: [`../fila/2026-08-24-modo2-humanizacao-da-entrega.md`](../fila/2026-08-24-modo2-humanizacao-da-entrega.md).

- **Meta e domínio próprio (16/08):** portões 1 e 2 da Meta caíram no mesmo dia — app `Revy`
  criado, produto WhatsApp adicionado, número de teste enviando e webhook voltando. Domínio
  **`revyapp.com.br`** registrado no **CNPJ** (o `revy.com.br` é de terceiro), DNS migrado
  para a Cloudflare, e o **site saiu do bundle do Fly** para o Cloudflare Pages — publicar
  landing não é mais deploy. Em 23/08 o webhook foi ligado no `n8n2037` e o workflow ativado;
  falta **trocar o número de teste pelo real**. Estado verificado, armadilhas (DNSSEC do `.br`,
  janela de 2h do registro.br) e cronograma:
  [`design/2026-08-16-onboarding-meta-dominio-asbuilt.md`](design/2026-08-16-onboarding-meta-dominio-asbuilt.md).
  **O CNPJ verificado não bloqueia o piloto:** o teto de 250/24h conta só conversa iniciada
  pela empresa, e o funil é CTWA (inbound). Ele vira obrigatório na **terceira loja**.
  A verificação foi submetida em 23/08 e saiu **Verificada em 24/08** — portão 3 fechado.
  Fechá-lo **não destravou nenhum passo do piloto**: o que ele compra (nome de exibição,
  terceiro número, disparo para a base) só serve com número real, que segue sendo a
  pendência de hardware (chip/eSIM com voz-SMS, num número que nunca teve WhatsApp).
  Spec canônica:
  [`specs/2026-08-12-whatsapp-dois-modos-design.md`](specs/2026-08-12-whatsapp-dois-modos-design.md).
  Sete cards executados, planos em [`planos/`](planos/):
  - `chatbot-api`: `fila_vendedor`, `oferta_lead`, `rodizio_ponteiro` (migrations 0020/0021),
    `conversas.followup_toques` (0022). Ponteiro rotativo, trava idempotente do primeiro
    clique, worker de 10 min, adapters Cloud (`GraphMediaDownloader`,
    `CloudWhatsAppOutbound`), três gatilhos de handoff, re-notificação com throttle,
    `FollowupWorker`, e o webhook `/webhook/cloud` com HMAC sobre corpo cru e dedup por
    `wamid`. Flag `CHATBOT_WHATSAPP_MODO2_ENABLED`.
  - `revy-trafego`: `lojas.whatsapp_modo` (1 XOR 2, migration 0019), emitido como aggregate
    no snapshot de provisionamento, escolhido na ficha da loja. Flag
    `REVY_CONTROL_WHATSAPP_MODO2_ENABLED`.
  - `n8n`: `workflow-cloud.json` como transporte fino (GET verify + POST `rawBody`), com
    `validate_workflow_cloud.py`. `workflow-ai-nao-salvos.json` (Baileys) **intacto**.
  - **Gate único:** `rodizio.loja_opera_modo2` = flag + `allows_processing` +
    projeção `whatsapp_modo == "2"`. Loja Modo 1 não entra no rodízio.
  - **A metade do dono da loja entrou** (Card 5, agora em `planos/`): `GET /v1/ofertas` e
    `POST /v1/ofertas/{id}/assumir` no chatbot, produtor do sinal no `copiloto_sinais_job`,
    botão Peguei no sino, faixa "N sem vendedor" e card de 7 dias em `loja/routes.py`.
    **Lead que ninguém pega não some mais.**
  - **Falta fora de código:** o **número real** (chip/eSIM com voz-SMS, número que nunca teve
    WhatsApp) e o meio de pagamento na WABA. Conta na Meta, publicação/ativação do `n8n-cloud`
    e o provider de transcrição **saíram da lista**. Card de fechamento em `../fila/`.
- **Triagem UX 2026-08-07:** 32 itens feitos e **13 recusados** — não re-propor:
  [`2026-08-07-triagem-revisao-ux-loja-control.md`](2026-08-07-triagem-revisao-ux-loja-control.md).
- **Marca:** `shared/brand/revy-tokens.css` é a fonte única; acento verde racing;
  `app.css` não reabre `:root`. Conferência visual e alguns deploys de marca ainda
  pendentes no handoff da época — o código está no `main`.
- **CTWA/ROI:** match por `ad_id` + Graph; venda herda campanha do lead na leitura
  (`herdar_campanhas_de_leads`). Nunca casar por telefone mascarado. Task 4 é
  configuração de anúncio (`Cód:`), não código.
- **Bot WhatsApp:** replay >5 min bloqueado; debounce 40s (só a última mensagem);
  `origem=meta_ctwa` só com identificador de anúncio ou `ctwa_source_type` da família.
  Workflow Git `n8n/workflow-ai-nao-salvos.json` tem **32 nós**. Última inspeção do
  live (`n8n2037`, 2026-08-04): importado como `wAiNaoSalvos0001`, **inativo/draft**.
  Teste separado permanece OFF. Active ON só com smoke autorizado pelo dono.
- **Alerta de simulação no grupo:** persistência + outbox + retry + dead-letter no
  Chatbot. Residual = smoke, não código. **Fica** no Modo 1.
- **WhatsApp dois modos** (Baileys+grupo **ou** Central Cloud API): spec fechada
  (revisão 2026-08-13). Plano ainda não escrito. Coexistência por vendedor foi
  descartada. Escolha no Control; Loja muda a tela. Fallback do dono é Atendimento
  (faixa + filtro), não WhatsApp 19h.
- **Motor:** 4 bancos LIVE; teto 2 browsers; Playwright sob demanda em `motor2037`
  (`gru`). Resultado ao cliente continua **humano** no Portal. Worker em IP
  residencial: design aprovado, sem código; gate é o probe no PC.
- **Prod `app2037` (piloto):** secrets de shell, entitlements, atendimento e WhatsApp
  Loja **ON**; redirect legado **OFF**; Copiloto **OFF** no código até ops ligar.
- **Skill `revy-research` (23/08):** existe em `.claude/skills/revy-research/`. Dá ao agente
  `arquivo:linha` de rota, modelo, worker, migration, flag e template dos 6 produtos sem abrir
  `main.py` inteiro, mais `learnings/` e `decisoes/` (o que o dono já recusou). O `mapa/` é
  **gerado e commitado junto com o código** — nunca editado à mão. Mexeu em rota, modelo,
  worker, migration ou flag? regere e commite no mesmo commit (`AGENTS.md` §6):
  `cd .claude/skills/revy-research && python gerar_mapa.py` (Windows) ou `python3 gerar_mapa.py`
  (macOS), ~8s; `--verificar` reabre cada `arquivo:linha` e sai 1 se o mapa mentir.

## Fontes da verdade

| Tema | Abrir |
|---|---|
| Fila de código | `docs/fila/README.md` |
| Onde mora um símbolo (rota, modelo, worker, flag) | `.claude/skills/revy-research/mapa/<produto>.md` |
| As-built Control/Loja | `docs/referencia-viva/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md` |
| Ops recente | `docs/referencia-viva/handoff-contexto.md` |
| UX aceita e recusada | `docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md` |
| Copiloto (env, validação) | `portal-gestao/docs/copiloto-env.md` |
| Deploy Fly | `deploy/fly/3vm/README.md` |
| RPA / lições | README do Motor + **uma** lição em `docs/referencia-viva/planos/` |
| Vocabulário | `CONTEXT.md` |

## Prioridades independentes

Um eixo por mudança. Não misture Copiloto, RPA, rollout e n8n na mesma entrega.

| Eixo | Próximo resultado verificável |
|---|---|
| Copiloto | F5 (lacunas no Control e/ou RLS) **ou** F6 (ferramentas cadastro/funil) |
| Loja — foto | Upload por arquivo no form de estoque (os dois modos; no 2 é o único caminho) |
| Loja — sino | B1: central geral por tipo. Sem blast `simulacao_pronta`. Oferta 1:1 = plano dos dois modos |
| Motor | Probe Bradesco no PC (gate do worker residencial) **ou** estabilidade Bradesco |
| Bot / n8n | Smoke virgem/CTWA/handoff/salvo no lab → Active ON pelo dono |
| Modo 2 (piloto) | Fila com 2+ vendedores, agora contra o código corrigido (a reoferta não saía; conserto no ar em 24/08). Falta o manual: allow-list **sem o nono dígito**, o vendedor 2 abrindo a janela de 24 h, e `POST /v1/fila-vendedores` com `ordem=2` |
| Control | Secrets GCP (Google Ads) **ou** E2E dois canais WA |
| CTWA | Task 4: `Cód:` na mensagem do anúncio (config, não PR) |
| Site | Adiado — não pegar sem o dono pedir |

## Fronteiras permanentes

- Produtos se integram só por HTTP/evento versionado. Sem import `app` cruzado.
- Estoque = veículos. Chatbot = conversa. Loja = venda. Motor = banco. Control = estrutura.
- Flags de rollout default OFF no código. Suspensão é gate de backend.
- Copiloto: sem PII no prompt; cifra só vem de ferramenta tipada; `indisponivel`, nunca zero inventado.
- Sem secret, token, cookie ou `workflow-fly.ready.json` no git ou no log.
- 13 itens de UX recusados não voltam como proposta.

## Mapa rápido

| Produto | Onde o domínio mora |
|---|---|
| Chatbot | `chatbot-api/app/servico.py` (não abrir `main.py` inteiro) |
| Motor | `motor-simulacao/app/motor/` |
| Estoque | `estoque-api/app/` |
| Revy Loja | `portal-gestao/app/loja/` + `app/web/loja_*.py` + `app/loja/copiloto/` |
| Revy Control | `revy-trafego/app/control/` + `app/web/control*.py` |
| Catálogo | `catalogo-publico/app/` |
| n8n | `n8n/workflow-ai-nao-salvos.json` (32 nós no Git) |

## Verificação mínima

Sempre a partir da pasta do produto:

```bash
cd portal-gestao && python -m pytest -q
cd ../chatbot-api && python -m pytest -q
cd ../motor-simulacao && python -m pytest -q
cd ../estoque-api && python -m pytest -q
cd ../revy-trafego && python -m pytest -q
```

n8n: `python n8n/validate_workflow.py` na raiz. Preserve
`n8n/workflow-teste-numero-autorizado.json`.

Não anote contagem de testes neste arquivo — ela envelhece na hora.

## Regras de operação

- Não recrie apps Fly monolíticos. Não destrua volume/snapshot sem pedido.
- Não use `git clean -fdX`.
- Ao fechar um card da fila, **mova** o arquivo para `docs/referencia-viva/planos/`
  e atualize este arquivo + `docs/fila/README.md` no mesmo PR.
- Antes de concluir: testes do produto, `git diff --check`, `git status --short`.
