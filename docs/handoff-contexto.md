# Handoff técnico

Atualizado em **2026-08-08**. Este arquivo registra somente o checkpoint atual.
Histórico detalhado permanece no Git; não acumular “checkpoints anteriores” aqui.

Leia primeiro:

1. [`contexto-compacto.md`](contexto-compacto.md) — estado, prioridades e regras.
2. [`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) — arquitetura implementada.
3. [`plans/README.md`](plans/README.md) — índice e status dos planos.

## Checkpoint de código

- **Entregas 2026-08-08 — Identidade visual unificada nos quatro front-ends (branch
  `design/identidade-visual-revy`, ainda NÃO deployado). Sem migration.** Spec em
  [`superpowers/specs/2026-08-08-identidade-visual-revy-design.md`](superpowers/specs/2026-08-08-identidade-visual-revy-design.md),
  plano em [`superpowers/plans/2026-08-08-identidade-visual-revy.md`](superpowers/plans/2026-08-08-identidade-visual-revy.md),
  kit para pessoas de fora em [`brand/revy-brand-kit.md`](brand/revy-brand-kit.md) v2.0.
  **As 10 tarefas do plano foram executadas.**
  - **`shared/brand/revy-tokens.css` é a fonte única** de cor, forma e tipografia.
    `sync_tokens.py` copia para os quatro produtos; `shared/brand/tests` falha se uma
    cópia divergir do canônico ou se um par de contraste cair abaixo de 4,5:1. Copiar em
    vez de importar por HTTP é decisão: cada produto é um deploy independente, e uma
    folha buscada de outro serviço faria o Control fora do ar despintar o catálogo.
  - **Acento passa a ser o verde racing.** `#1f4d3a` no claro, `#7fbfa3` no escuro — o 700
    sobre `#0a0a0a` dá 1,6:1. Um teste falha se o azul antigo (`#1f6feb`, `#5a95ff`,
    `#1a5fd0`, `#82afff`) voltar ao CSS da Loja ou do Control.
  - **Marca virou vetor.** O logo anterior era `<text font-family="Inter">`: sem contorno,
    dependia da fonte instalada e não servia para impresso nem criativo. `build_marca.py`
    gera símbolo por geometria e wordmark por `fontTools`. **A logo é preta sempre**; a
    versão reversa leva fio `rgba(255,255,255,.16)` para não sumir sobre `#161616`.
  - **Estado virou ponto + palavra**, nunca cor sozinha. Terminais (`cancelada`, `falhou`,
    `suspensa`, `encerrada`) não levam ponto. No Control existem **duas** formas de estado:
    `.status` e a hifenizada `.status-pill.status-ativa` (`app/rotulos.py`), de
    especificidade maior — as duas foram migradas.
  - **Catálogo e site são sempre claros.** Declaram `color-scheme: light`, e
    `shared/brand/tests/test_publicas.py` varre HTML e CSS escritos à mão para impedir que
    alguém ligue `data-theme` numa vitrine.
  - **Pendente:** deploy; PNG de favicon 32/180 (precisa de rasterizador, nenhum venv tem);
    `docs/brand/preview.html` e `index.html` ainda mostram a paleta v1.0; medição de LCP do
    catálogo; conferência visual humana dos dois temas. **Fora de escopo por decisão:** as
    ~57 páginas com o cabeçalho triplo (eyebrow + h1 + parágrafo) e a copy de marketing em
    `loja/vendas_visao.html` seguem como estão — o plano trocou marca, cor, forma e tipo,
    não redesenhou telas.

- **Entregas 2026-08-08 — Varredura de marca em todas as telas (branch
  `marca/varredura-telas`, ainda NÃO deployado/mesclado). Sem migration.** Plano em
  [`superpowers/plans/2026-08-08-varredura-marca-todas-as-telas.md`](superpowers/plans/2026-08-08-varredura-marca-todas-as-telas.md),
  spec em [`superpowers/specs/2026-08-08-varredura-marca-todas-as-telas-design.md`](superpowers/specs/2026-08-08-varredura-marca-todas-as-telas-design.md).
  Continuação da entrega de identidade visual acima: leva a marca decidida às 76 telas do
  Revy Loja e do Revy Control. **As 14 tarefas do plano foram executadas.**
  - `app.css` de cada painel **não redeclara mais nenhum token canônico**, e a antiga
    "Camada Revy 2026" (sobrescritas soltas no fim do arquivo) foi dissolvida numa seção
    por peça (Botão, Campo e formulário, Estado, Painel e card, Tabela e lista, Número e
    gráfico, Navegação e shell, Alerta/faixa/vazio, Autenticação) — idêntica nos dois
    painéis.
  - **Os cinco apelidos genéricos saíram do canônico (Tarefa 14):** `--green`, `--amber`,
    `--red`, `--online` e `--radius` existiam só para o `app.css` antigo continuar
    funcionando; hoje todo consumo usa o nome semântico (`--ok`/`--warn`/`--danger`/
    `--whatsapp`, `--radius-ctl`/`--radius-nav`/`--radius-srf`). `catalogo-publico` e
    `site` também consumiam apelidos fora do alcance das guardas dos dois painéis
    (`.whatsapp`/`.notice`/`.filters` etc. em `catalog.css`, `--green: var(--online)` no
    `site/index.html`) e foram migrados na mesma tarefa.
  - **Os antigos tetos decrescentes viraram asserções absolutas** em
    `shared/brand/tests/test_app_css.py`: `test_nenhum_raio_fora_do_sistema` (zero raio
    literal fora de `--radius-ctl`/`-nav`/`-srf`, 50%, `inherit`, `0`) e
    `test_apelido_generico_nao_volta` (zero uso de qualquer apelido aposentado), nos dois
    painéis. Substituem `TETO_RAIOS`/`TETO_APELIDOS`, que só podiam descer.
  - **Hotfix crítico (`add7828`), pré-requisito da Tarefa 14:** o comentário de cabeçalho
    de `shared/brand/revy-tokens.css` tinha um `*/` literal no texto, fechando o comentário
    cedo e derrubando o `:root` do tema claro no parser real do navegador — as guardas em
    Python (regex) não pegavam isso. Corrigido, com guarda de regressão
    `test_root_do_tema_claro_sobrevive_ao_parser_do_navegador`.
  - **Pendente:** merge/deploy da branch. **Conferência visual consolidada dos dois temas**
    (telas-testemunha dos dois painéis + vitrine + site) foi deferida de propósito para
    depois da Tarefa 14 e é o próximo passo antes do merge. Espaçamento/"gaps" nas telas
    novas segue em fila separada, por decisão do dono (ver "Pendências reais").

- **Entregas 2026-08-08 — CTWA/ROI: a venda herda a campanha do lead (branch
  `feat/ctwa-heranca-roi`, ainda NÃO deployado). Sem migration.** Plano em
  [`superpowers/plans/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md`](superpowers/plans/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md).
  - **`revy-trafego/app/roi_calc.py` — `herdar_campanhas_de_leads`**: `venda_casa_campanha`
    só olhava `campanha_id`/`utm` gravados na própria venda, enquanto a contagem de leads
    já casava por `ad_id`. O conserto é **na leitura**, então vale retroativamente para
    toda venda já projetada — sem backfill, sem `UPDATE`, sem reenviar evento. Atribuição
    explícita vence herança, e a ordem do laço (nome em `casefold`) garante que uma venda
    nunca conte em duas campanhas. O detalhe da campanha (`main.py`) usa a mesma herança.
  - **`vendas_projection.py`**: `campanha_id_first/last` vindo do outbox do Portal só é
    gravado se existir em `campanhas` da mesma loja. O Portal manda UUID do cadastro dele;
    aceitar isso desligaria o casamento por UTM **e** a herança, e a venda sumiria do ROI.
  - **`chatbot-api/app/servico.py`**: `origem = meta_ctwa` passou a exigir identificador de
    anúncio **ou** `ctwa_source_type` de família de anúncio (`fb_ads`/`ctwa_ad`/`ad`, em
    `casefold` — o valor real é `FB_Ads`). Link direto e busca dentro do WhatsApp não são
    mais contados como anúncio. **Sem backfill**: os 10 leads antigos ficam errados de
    propósito. O sinal cru continua sempre gravado, e `canal=whatsapp` saiu do guard.
  - **`_vincular_tracking_pendente_ao_lead`**: varre **todas** as conversas do telefone com
    pendente em `ORDER BY criada_em ASC` (ASC é obrigatório: `_first` só é gravado enquanto
    nulo). O ramo idempotente do webhook passou a consumir o pendente.
  - **`portal-gestao/app/loja/sales_overview.py` + `templates/loja/vendas_visao.html`**:
    bloco "Por onde as pessoas chegam" na seção de aquisição, agrupando por
    `ctwa_source_type` (não por `origem`, que está errada e não será corrigida). **Guard
    próprio**: a fonte é o lead do Chatbot, não o gasto da Meta.
  - **`meta_ad_resolver_job.py` + `control/integrations.py`**: salvar a config de Ads
    destrava os ads que estouraram `max_tentativas` (WHERE por `loja_slug`, **não** por
    `store.id`), e a auditoria CTWA mostra quantos anúncios seguem sem campanha.
  - ⚠️ **Pendente e não é código — Task 4:** pôr `Cód: <CÓDIGO>` na mensagem pré-preenchida
    de cada anúncio e corrigir `codigo_ctwa` das campanhas (2 das 3 têm a frase-convite
    inteira colada no campo). É a **única** rota que alcança os 3,6% de leads que a Meta
    entrega sem identificador.
  - ⚠️ **Nunca casar lead↔`ctwa_auditoria` por telefone mascarado.** Testado contra o dado
    real: casou o lead de uma venda com o anúncio de outro cliente (só os 4 dígitos finais
    batiam). Está documentado em "O que foi descartado" no plano.
- **Entregas 2026-08-07 — triagem de UX (main `e06d9e5`, LIVE app2037 v115):** 32 itens de
  uma revisão de produto, triados um a um pelo dono. **Sem migration.** Detalhe completo,
  com o que foi aceito e o que foi **recusado**, em
  [`2026-08-07-triagem-revisao-ux-loja-control.md`](2026-08-07-triagem-revisao-ux-loja-control.md).
  Resumo do que mudou de contrato ou de estrutura:
  - **Control › Visão geral** encolheu: saíram "Destaques", "Contagens por status", a tabela
    "Lojas", a coluna "Falhas", o painel Google e "Alterações recentes". `network_overview`
    ganhou `desde`/`ate` (datas inclusivas) e devolve `periodo_inicio`/`periodo_fim`; a
    janela padrão virou `[1º do mês, hoje]` e o Δ% compara a janela anterior de mesmo
    tamanho. A rota aceita `?inicio=&fim=`.
  - **`revy-trafego/app/rotulos.py`** (novo): mapa único de rótulos dos enums, registrado
    nos **dois** ambientes Jinja (`app.main` e `app.web.control_ui` têm instâncias
    separadas — global posto em um não aparece no outro).
  - **`/app` do Control deixou de ser tela**: encaminha para Visão geral (ou Lojas sem a
    flag de dashboard). `home.html` sobrou como estado vazio para Control desligado e sem
    loja — `exigir_loja` devolve todo mundo para `/app`, então redirecionar dali fecharia
    um laço.
  - **Ajustes › Integrações no Control** (`/app/control/integracoes`), espelhando a página
    que a Loja já tinha.
  - **Painel de Prontidão na ficha da loja**: `build_readiness_report` sai da mensagem de
    erro de ativação e vira UI (OK / Bloqueio / Alerta). Aba "Auditoria" da ficha removida.
  - **Loja**: fila de atendimento com coluna "Aguardando há" (`tempo_relativo()` em
    `portal-gestao/app/main.py`); badge de canal saiu do `<style>` inline escrito para o
    tema escuro; config da vitrine mudou de Ajustes › Números de WhatsApp para
    **Estoque › Vitrine** (o POST `/app/loja/whatsapp/catalogo` agora redireciona para
    `/app/loja/estoque/vitrine`); menu renomeado ("Resultado", "Situação do estoque",
    "Vitrine"); funil clicável; rodapé "Atalhos" para telas legadas removido.
  - **Página do Agente redesenhada** + ícone no menu; **conversa do lead no Control** com
    bolhas e separador de dia.
- **Entregas 2026-08-07 (main `a2a11f5`, LIVE app2037 v114):** 3 features no bundle —
  1. **Revy Control — Visão Geral de negócio** (`/trafego/app/control/dashboard`): cards
     Lojas ativas / Vendas no mês (Δ%) / Ticket médio / Leads na rede + tabela "Desempenho
     por loja" (só ativas) + "Destaques". Read model `network_overview`
     (`revy-trafego/app/control/dashboard.py`): vendas/ticket de `vendas_projetadas`
     (filtro `status=="confirmada"`); leads via `_ChatbotLeadsPort` HTTP (retries=0/timeout=3s,
     em `control_ui.py`). **Sem coluna/painel de Meta nesta fase** (Portal→Control não projeta
     metas ainda).
  2. **Filtro lojas ativas**: seletor lateral do Control mostra só `StoreStatus.ACTIVE`
     (`_selector_stores`); a gestão "Lojas" continua listando todas.
  3. **Revy Loja — Desempenho do agente** (`/app/loja/agente`): métricas do BOT (atendimentos,
     transferidos+%, gráfico CSS por dia) + card Simulações **placeholder "em construção"**.
     Consome endpoint NOVO do Chatbot `GET /v1/atendimento/resumo` (SQL sobre `conversas`).
  - Sem migration nova (lê tabelas existentes). Flags já ON no app2037 (são **secrets**, e o
    secret vence o `[env]="0"` do toml). Spec/plano em
    `docs/superpowers/{specs,plans}/2026-08-07-control-overview-loja-agente*`.
- Revy Control lean F0–F6 está implementado em `revy-trafego`.
- Revy Loja lean F0–F6/F8 está implementado em `portal-gestao`.
- **Entregas 2026-08-03 (main):** Atendimento com chat humano + poll `after_id`; Perfil
  (senha fora de Ajustes); status WA persiste `conectado` no DB; Grupo do estoque de volta
  no menu Ajustes + redesign da tela; workflow oficial com jornada de catálogo e
  `simular1` (lead qualificado + aviso equipe no WA + pausa bot; cliente só confirmação).
- **Bot WhatsApp (main `8effb99`):** fail-open no gate + prompt com histórico CRM.
  - Backend: `is_saved is True` cala por agenda; `None` (Evolution cega) **atende**.
  - Registrar expõe `tem_saida` + `historico_recente`.
  - Gate n8n `atendeLeadVirgem()` (handoff, agenda, `chatFound`, conversa em andamento).
  - IA: system prompt com prioridade da `mensagem_atual` + histórico no user prompt.
  - Detalhe: [`diagnostico-bot-whatsapp-2026-08-03.md`](diagnostico-bot-whatsapp-2026-08-03.md);
    guia: [`../n8n/GUIA-WORKFLOW.md`](../n8n/GUIA-WORKFLOW.md).
- Seller AI permanece adiado e desligado.
- O Portal foi modularizado: simulações, metas, equipe e tráfego/campanhas ficam em
  `portal-gestao/app/web/`; `main.py` mantém bootstrap e rotas legadas restantes.
- O workflow `n8n/workflow-teste-numero-autorizado.json` é gerado do canônico (lab; 1 telefone).
- `n8n/workflow-ai-nao-salvos.json` é o **oficial no Git** (30 nós: bloqueio de
  replay, Wait 40s + juiz da última mensagem e fallback temporário de estoque).
  Importado no `n8n2037` como `wAiNaoSalvos0001`; permanece inativo até smoke.
- Stack local: `./local.sh up` — `deploy/local/README.md`; segredos em `.env.local`.

## Validação conhecida

- Suítes (2026-08-08, branch `marca/varredura-telas`, fim da Tarefa 14): `shared/brand`
  **181** guardas de marca (raio, apelido aposentado, contraste AA, cópia sincronizada,
  `:root` sobrevive ao parser); portal-gestao **597**; revy-trafego **497** (+1 falha
  pré-existente `test_control_provisioning_outbox`, mesma de sempre — ver abaixo).
- Suítes (2026-08-07, em `e06d9e5`): revy-trafego **472** (+1 falha pré-existente outbox
  motor), portal-gestao **558** (`.venv` local). chatbot-api não foi tocado nesta entrega;
  última contagem conhecida **297** em `a2a11f5`.
- Suítes anteriores (merge `a2a11f5`): revy-trafego 461, chatbot-api 297, portal-gestao 551.
- A falha é `revy-trafego/tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`:
  teste estagnado desde `573348e` (`"motor"` em `DEFAULT_PROVISIONING_TARGETS`);
  **confirmado que falha no `main` também** (não é regressão da entrega de 07/08).
- chatbot-api: rodar ignorando dirs temporários travados de runs paralelos
  (`--ignore=test-tmp-run4 --ignore=test-tmp-run5`) — são scratch gitignored, não código.

## Estado operacional

**2026-08-04:** backend publicado no `app2037` e rota `/pode-responder` confirmada;
workflow oficial atualizado no `n8n2037` com backup `workflow.before-20260804140055739.json`.
A verificação pós-atualização retornou 30 nós, `active=false` e versão `draft`. O workflow
deve permanecer **inativo** até smoke autorizado pelo owner.
- Não rodar `n8n list:workflow` / CLI n8n via SSH no volume de prod (trava SQLite).
- Import: `prepare-workflow.ps1` + `upload-and-import-workflow.ps1`; **Active OFF** na UI.

Antes de qualquer ação:

1. consulte `deploy/fly/3vm/README.md`;
2. verifique `fly status` dos apps envolvidos;
3. confira migrations/readiness e logs sem imprimir segredos;
4. use deploy com contexto na raiz do repositório.

Arquitetura esperada do lab (**topologia dividida desde 2026-07-31**):

- `suite-pg`: banco — **`iad`**;
- `evolution2037`: canal WhatsApp, 512MB — **`iad`**;
- `app2037`: bundle de APIs/UI/site — **`iad`**;
- `n8n2037`: orquestração — **`iad`**;
- `motor2037`: workers Playwright sob demanda — **`gru`** (IP brasileiro para o RPA bancário;
  não mover — `deploy/fly/3vm/README.md`, "Por que a stack está dividida").

Não recriar apps monolíticos legados e não destruir volumes/snapshots sem pedido explícito.

## Ligar amanhã (checklist curto)

```text
1) Subir stack:
   fly machine start 48ee5d4ad12768 -a suite-pg
   fly machine start 867637ae203298 -a evolution2037
   fly machine start 48e1e6ea557558 -a app2037
   fly machine start 801655f6637358 -a n8n2037
   (opcional n8n always-on de novo: fly machine update 801655f6637358 -a n8n2037 --yes --autostart=true)
2) fly status → started + checks passing; healthz app e n8n
3) n8n UI https://n8n2037.fly.dev
   - confirmar "WhatsApp IA - Somente Nao Salvos" (wAiNaoSalvos0001) ainda OFF
   - fazer Active ON somente quando o owner autorizar o smoke
   - TESTE permanece OFF
4) Evolution: canal conectado; webhook → https://n8n2037.fly.dev/webhook/whatsapp-ai
5) Loja https://app2037.fly.dev
   - Ajustes → Números de WhatsApp: Conectado
   - Ajustes → Grupo do estoque: grupo + números da equipe
6) Smoke: não-salvo → bot; simular completo → frase curta; aviso WA equipe;
   Portal "Aguardando simulação"; bot pausado
```

Prepare de novo se precisar reimportar JSON com secrets:

```powershell
powershell -File deploy\fly\3vm\prepare-workflow.ps1 -Mode production
powershell -File deploy\fly\3vm\upload-and-import-workflow.ps1 -Mode production
# depois Active ON na UI (owner)
```

## Pendências reais

- **~~BUG — `venda_projetada.loja_id` nunca é preenchido~~ — CORRIGIDO (07/08, ainda não
  deployado):** `projetar_venda` passou a resolver `Loja.slug → id` (só quando está nulo,
  o que também cura venda órfã na próxima atualização) e a migration
  `0017_vendas_projetadas_backfill_loja_id` religa o passivo via
  `app/control/backfill.py::religar_vendas_orfas`. Cobertura pelo caminho real em
  `tests/test_vendas_projection.py`. **Ao deployar, rodar `alembic upgrade head` no
  revy-trafego** — sem a migration os KPIs continuam zerados para as vendas antigas.
- **Visão Geral do Control — as 2 decisões de produto de 07/08 foram resolvidas:**
  1. *Conversão mistura janelas* — o dono **recusou** mexer (item `C17` da triagem). A
     coluna segue como está.
  2. *Âncora do mês* — resolvida por declaração na tela ("vendas contadas pela data de
     confirmação"), sem uniformizar o backend. `network_overview` continua em
     `confirmada_em` e `financeiro_calc` em `criada_em`.
- **Espaçamento ("gaps") nas telas novas:** o dono viu problemas de espaçamento nas prévias
  e ainda não localizou onde. Fila separada.
- **Fase 2 do Control (diferida):** projeção de **metas** Portal→Control (habilita coluna
  Meta + painel "Meta da rede" + atingimento); endpoint bulk de leads por rede (hoje é loop
  por loja no escopo). Card **Simulações** no agente da Loja segue placeholder até a simulação
  estabilizar.
- Smoke bot e só então Active ON definitivo: virgem/CTWA atende; salvo/`chatFound` cala;
  handoff cala; rajada gera uma resposta; replay antigo não responde; estoque vazio oferece
  simulação sem fotos.
- **Re-parear / confirmar QR** do canal da loja se Evolution ou status ainda “Aguardando QR”.
- **Números da equipe** em Grupo do estoque se lista vazia (senão não há aviso de simulação no WA).
- **Motor/RPA** ainda não é o caminho de resultado ao cliente — simulação humana no Portal.
- Cutover Loja: `REVY_LOJA_REDIRECT_LEGACY` ainda OFF (dual-path).
- Áudio no workflow Git = ignorado; estabilizar `findChats`/`@lid` (sinal de agenda ainda frágil).
- Enxugar nós n8n (fundir gates) adiado de propósito.
- E2E multi-WA; Google Ads GCP; smokes bancários; restore drill.

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
