# Handoff técnico

Atualizado em **2026-08-03 (tarde/noite)**. Este arquivo registra somente o checkpoint atual.
Histórico detalhado permanece no Git; não acumular “checkpoints anteriores” aqui.

Leia primeiro:

1. [`contexto-compacto.md`](contexto-compacto.md) — estado, prioridades e regras.
2. [`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md) — arquitetura implementada.
3. [`plans/README.md`](plans/README.md) — índice e status dos planos.

## Checkpoint de código

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
- `n8n/workflow-ai-nao-salvos.json` é o **oficial no Git** (27 nós, Wait 40s no
  caminho IA→WhatsApp). Importado no `n8n2037` como `wAiNaoSalvos0001`.
- Stack local: `./local.sh up` — `deploy/local/README.md`; segredos em `.env.local`.

## Validação conhecida

- chatbot-api (corte A+B 2026-08-03): **265** passed; gate n8n **11** cenários;
  `python n8n/validate_workflow.py` ok.
- Suítes anteriores (2026-07-31): portal-gestao **471**, revy-trafego **361**
  (+1 falha pré-existente outbox motor), catalogo-publico **53**.
- A falha é `revy-trafego/tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`:
  teste estagnado desde `573348e` (`"motor"` em `DEFAULT_PROVISIONING_TARGETS`).

## Estado operacional

**2026-08-03 (sessão bot):** lab **ligado** (app/n8n/evolution/suite-pg started em momentos
da sessão). Código A+B no Git (`8effb99`); **deploy app2037 + reimport n8n ainda a fazer**
se não rodados nesta sessão. Workflow deve permanecer **inativo** até smoke.
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
   - "WhatsApp IA - Somente Nao Salvos" (wAiNaoSalvos0001) → Active ON
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

- **Deploy `app2037`** com commit A+B se ainda não subiu; **reimport workflow** no n8n
  (**Active OFF**); smoke e só então Active ON.
- Smoke bot: virgem/CTWA atende; salvo/`chatFound` cala; handoff cala; pedido específico
  não usa só o template “quer ver as motos?”.
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
