# Handoff técnico

Atualizado em **2026-08-03**. Este arquivo registra somente o checkpoint atual.
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
- O workflow `n8n/workflow-teste-numero-autorizado.json` é usado para testes e não deve
  ser removido.
- `n8n/workflow-ai-nao-salvos.json` **não é mais fiel ao que roda**: o live tem 31 nós e o
  arquivo tem 25 (ver Pendências). Tratar como referência, não como fonte de verdade.
- Stack local completa com um comando: `./local.sh up` (compose + bootstrap de loja,
  usuário e credenciais). Guia em `deploy/local/README.md`; segredos ficam em `.env.local`,
  que é ignorado pelo Git.

## Validação conhecida

- Suítes em 2026-07-31: portal-gestao **471**, revy-trafego **361** (+1 falha pré-existente),
  chatbot-api **246**, catalogo-publico **53**.
- A falha é `revy-trafego/tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`:
  teste estagnado desde `573348e`, que incluiu `"motor"` em `DEFAULT_PROVISIONING_TARGETS`.
  O hook passou a enfileirar uma linha `motor` e o `.one()` do teste estoura
  `MultipleResultsFound`. Não é regressão de produto; o fix é filtrar pelo `id` enfileirado.
- `git diff --check` e compilação dos módulos extraídos passaram no corte da refatoração.

## Estado operacional

O repositório não é fonte confiável para afirmar que uma Machine Fly está ligada neste
instante. Antes de qualquer ação:

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

## Pendências reais

- **Re-parear os números de WhatsApp por QR** (Ajustes na Revy Loja): o volume da Evolution
  nasceu vazio na migração para `iad` em 2026-07-31.
- **Portal, Tráfego e Catálogo começaram com banco vazio** na mesma migração (decisão do
  owner: só o n8n precisava sobreviver). Foi recriada uma conta `dono` no Portal para a loja
  `moto-center`; o gestor do Control é recriado sozinho por `bootstrap_gestor_se_vazio` a
  partir dos secrets `REVY_TRAFEGO_BOOTSTRAP_*`. Fotos do estoque se perderam.
  **Atualização 2026-08-02:** a `moto-center` estava só no Portal (login), não no Control —
  com `REVY_LOJA_ENTITLEMENTS_ENABLED=1` isso dava "módulo indisponível" + menu do shell
  vazio. O owner (re)criou a loja no Control (ativa + Vendas + Estoque) e ela foi projetada
  ao Portal; enforcement volta a funcionar. Mecanismo, estado das flags em prod e runbook de
  inspeção dos bancos em [`2026-08-02-provisionamento-loja-entitlements.md`](2026-08-02-provisionamento-loja-entitlements.md).
  **Atualização 2026-08-03:** cutover **parcial** no `app2037` (secrets revalidados): shell +
  entitlements + atendimento + `REVY_LOJA_WHATSAPP_ENABLED` **ON**; `REVY_LOJA_REDIRECT_LEGACY`
  **ainda OFF** (dual-path: URLs legadas `/app/leads`, `/app/conversas` etc. não redirecionam
  sozinhas). Seller AI permanece off. Defaults de código no repo continuam OFF.
- **Escala horizontal está bloqueada por dois motivos independentes** — plano em
  `docs/superpowers/plans/2026-07-31-escala-horizontal-app2037.md`: (1) Portal, Tráfego e
  Catálogo rodam em SQLite dentro do volume `app_data`, que é single-attach, então
  `fly scale count 2` produziria bancos divergentes em silêncio; (2) os workers de outbox e
  jobs sobem no `lifespan` do processo web, então N machines rodariam N cópias de cada loop.
  Sessão é cookie assinado e **não** é bloqueador.
- **`n8n/workflow-ai-nao-salvos.json` está defasado**: o workflow live tem 31 nós, o arquivo
  do repo tem 25. Faltam no repo transcrição de áudio (`Transcrever audio1`, `E audio1`,
  `Aplicar transcricao1`), `consultar_por_placa1`, `registrar_consentimento1` e
  `registrar_lead1`. O `CLAUDE.md` chama o arquivo de canônico — não é. Sincronizar exige
  re-placeholderizar os segredos antes de commitar.
- Residual cutover Loja (opcional): ligar `REVY_LOJA_REDIRECT_LEGACY=1` quando bookmarks/menus
  antigos devem cair no shell; até lá dual-path permanece. UX/deep-links de Atendimento.
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
