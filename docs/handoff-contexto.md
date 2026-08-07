# Handoff técnico

Atualizado em **2026-08-07**. Este arquivo registra somente o checkpoint atual.
Histórico detalhado permanece no Git; não acumular “checkpoints anteriores” aqui.

Leia primeiro:

1. [`contexto-compacto.md`](contexto-compacto.md) — estado, prioridades e regras.
2. [`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) — arquitetura implementada.
3. [`plans/README.md`](plans/README.md) — índice e status dos planos.

## Checkpoint de código

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

- **BUG — `venda_projetada.loja_id` nunca é preenchido (bloqueia os KPIs do Control):**
  `revy-trafego/app/vendas_projection.py` (`projetar_venda`) grava `loja_slug` e deixa
  `loja_id` NULL; o único lugar que preenche é `app/control/backfill.py`, chamado **só**
  dentro da migration `0002`. Toda venda que chega pelo contrato HTTP depois da migration
  fica órfã. O dashboard filtra por `loja_id`
  (`revy-trafego/app/control/dashboard.py`), então "Vendas confirmadas", ticket médio, Δ%
  e a tabela por loja mostram **zero** em produção, mesmo com vendas chegando. O ROI da
  Loja não sofre porque `financeiro_calc` filtra por `loja_slug`.
  **Correção:** resolver `Loja.slug → id` dentro de `projetar_venda` (padrão já existe em
  `api_v1.py:389-396`) + backfill único das órfãs. Ao testar, exercitar o caminho
  `projetar_venda` — `tests/test_dashboard_network_overview.py` passa `loja_id=` na mão e
  por isso valida a query, não o contrato.
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
