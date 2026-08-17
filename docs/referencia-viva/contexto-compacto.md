# Contexto compacto para continuidade

Atualizado em **2026-08-14**. Ponto de entrada de estado e prioridades.
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

- **WhatsApp Modo 2 (central Cloud API):** no `main` e **deployado**; flag
  `CHATBOT_WHATSAPP_MODO2_ENABLED=1` no `app2037` desde 16/08, mas **nenhuma loja tem a
  projeção `whatsapp_modo=2`** — o gate é fail-closed em três condições, então nada roda.
  Placar do que existe e do que falta:
  [`design/2026-08-16-whatsapp-modo2-asbuilt.md`](design/2026-08-16-whatsapp-modo2-asbuilt.md).
  **Em 16/08 o `n8n-cloud` era um transporte de 4 nós — havia rodízio e handoff e nenhum bot
  respondendo o cliente.** Corrigido: o workflow virou fork gerado do Modo 1 (20 nós, com
  agente, ferramentas e debounce), `solicitar_handoff` passou a abrir o rodízio, e o retry
  da §6.1 saiu do `logger.exception` para uma tabela com worker. Dívida conhecida, em ordem
  de risco: **VAD do áudio** (§5.10 — o Whisper alucina em ruído e o bot age em cima),
  **recusa não cutuca** (§5.9 r.5) e `classificar_etapa` presa em `so_oi`.

- **Meta e domínio próprio (16/08):** portões 1 e 2 da Meta caíram no mesmo dia — app `Revy`
  criado, produto WhatsApp adicionado, número de teste enviando e webhook voltando. Domínio
  **`revyapp.com.br`** registrado no **CNPJ** (o `revy.com.br` é de terceiro), DNS migrado
  para a Cloudflare, e o **site saiu do bundle do Fly** para o Cloudflare Pages — publicar
  landing não é mais deploy. Falta ligar o webhook no `n8n2037` e trocar o número de teste
  pelo real. Estado verificado, armadilhas (DNSSEC do `.br`, janela de 2h do registro.br) e
  cronograma:
  [`design/2026-08-16-onboarding-meta-dominio-asbuilt.md`](design/2026-08-16-onboarding-meta-dominio-asbuilt.md).
  **O CNPJ verificado não bloqueia o piloto:** o teto de 250/24h conta só conversa iniciada
  pela empresa, e o funil é CTWA (inbound). Ele vira obrigatório na **terceira loja**.
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
  - **Falta em código:** a metade do dono da loja — sino 1:1 com Peguei, faixa "N sem vendedor",
    filtro Aguardando, card de 7 dias. O chatbot não expõe rota de oferta e
    `criar_sinal_direcionado` não tem chamador, então **lead que ninguém pega some**. Card 5 em
    `../fila/`.
  - **Falta fora de código:** conta do Revy na Meta, publicar/ativar o `n8n-cloud`, provider de
    transcrição. Card de fechamento em `../fila/`.
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

## Fontes da verdade

| Tema | Abrir |
|---|---|
| Fila de código | `docs/fila/README.md` |
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
