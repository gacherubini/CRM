# Handoff técnico

Atualizado em **2026-08-03 (noite)**. Este arquivo registra somente o checkpoint atual.
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
- Seller AI permanece adiado e desligado.
- O Portal foi modularizado: simulações, metas, equipe e tráfego/campanhas ficam em
  `portal-gestao/app/web/`; `main.py` mantém bootstrap e rotas legadas restantes.
- O workflow `n8n/workflow-teste-numero-autorizado.json` é gerado do canônico (lab; 1 telefone).
- `n8n/workflow-ai-nao-salvos.json` é o **oficial no Git** (25 nós, jornada catálogo +
  simulação humana). Importado no `n8n2037` como `wAiNaoSalvos0001` — **Active fica a
  critério do owner**; **não religar** sem ler o diagnóstico e aplicar correções mínimas.
- **Diagnóstico bot (2026-08-03):** [`diagnostico-bot-whatsapp-2026-08-03.md`](diagnostico-bot-whatsapp-2026-08-03.md)
  — CTWA silenciado por `isSaved` fail-closed, handoff `bot_ativo` ignorado, saudação
  sem contexto; workflow desligado de propósito até fix.
- Stack local: `./local.sh up` — `deploy/local/README.md`; segredos em `.env.local`.

## Validação conhecida

- Suítes em 2026-07-31: portal-gestao **471**, revy-trafego **361** (+1 falha pré-existente),
  chatbot-api **246**, catalogo-publico **53**.
- A falha é `revy-trafego/tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`:
  teste estagnado desde `573348e`, que incluiu `"motor"` em `DEFAULT_PROVISIONING_TARGETS`.
  O hook passou a enfileirar uma linha `motor` e o `.one()` do teste estoura
  `MultipleResultsFound`. Não é regressão de produto; o fix é filtrar pelo `id` enfileirado.
- `git diff --check` e compilação dos módulos extraídos passaram no corte da refatoração.

## Estado operacional

**Noite 2026-08-03:** lab Fly **desligado** para economizar; **volumes e apps preservados**.
- `app2037`, `evolution2037`, `suite-pg`: `machine stop`.
- `n8n2037`: machine recriada no volume `n8n_data` (`801655f6637358`), depois
  `autostart=false` + stop (senão o `min_machines_running=1` religava sozinho).
  **Amanhã:** `fly machine start 801655f6637358 -a n8n2037` e, se quiser always-on de novo,
  `fly machine update … --autostart=true` ou redeploy `fly.n8n.toml`.
- Workflow oficial **importado** no volume n8n (`wAiNaoSalvos0001`); **Active na manhã**.

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

- **Ativar workflow oficial** na manhã (lab estava off; Active não garantido após restart).
- **Re-parear / confirmar QR** do canal da loja se Evolution ou status ainda “Aguardando QR”.
- **Números da equipe** em Grupo do estoque se lista vazia (senão não há aviso de simulação no WA).
- **Motor/RPA** ainda não é o caminho de resultado ao cliente — simulação humana no Portal.
- Cutover Loja: `REVY_LOJA_REDIRECT_LEGACY` ainda OFF (dual-path).
- Áudio no workflow Git = ignorado (ramo de 31 nós do live antigo pode ter sido
  sobrescrito pelo import de 25 nós — se precisar áudio, reexportar/fundir).
- E2E multi-WA; Google Ads GCP; smokes bancários; restore drill; Graphify se usar como índice.

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
