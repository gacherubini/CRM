# Contexto compacto para continuidade

Atualizado em **2026-08-03**. Este é o ponto de entrada para estado e prioridades.
O desenho implementado está em
[`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md),
os termos do domínio em [`../CONTEXT.md`](../CONTEXT.md) e os planos válidos em
[`plans/README.md`](plans/README.md).

## Estado atual

- **Revy Control:** código lean F0–F6 implementado em `revy-trafego`. Inclui lojas,
  pessoas/cargos, acessos, contrato/módulos, prontidão, auditoria, provisioning,
  Google Ads e canais WhatsApp. **Defaults de código** das flags continuam OFF (dev/lab).
- **Revy Loja:** código lean F0–F6 e F8 implementado em `portal-gestao`. Inclui shell,
  entitlements, visões de Vendas/Estoque, Atendimento multi-canal, equipe e bancos.
  Seller AI (F7) permanece explicitamente adiado (off em prod).
- **Prod `app2037` (piloto, secrets 2026-08-03):** cutover **parcial** — shell +
  entitlements + atendimento + WhatsApp Loja **ON**; `REVY_LOJA_REDIRECT_LEGACY` **OFF**
  (dual-path: `/app/leads`, `/app/conversas` etc. ainda respondem sem 303). Detalhe e
  runbook em [`2026-08-02-provisionamento-loja-entitlements.md`](2026-08-02-provisionamento-loja-entitlements.md).
- **Portal legado:** continua disponível (redirect legado off). `app/main.py` foi reduzido e
  os domínios grandes estão em `app/web/{simulacoes,metas,equipe,trafego}.py`.
- **WhatsApp:** Chatbot é dono de canais, leads, conversas e mensagens; Control apenas
  administra os canais por contrato HTTP. n8n continua a orquestração do webhook.
- **Motor:** Santander, Fontecred, Bradesco e Pan portal usam workers Playwright sob
  demanda. Warm sessions e concorrência máxima devem ser validadas no ambiente real.
- **Fly:** a arquitetura canônica é 3-VM. Nunca assuma que o lab está ligado ou saudável;
  confira `deploy/fly/3vm/README.md` e o estado atual antes de operar.

## Fontes da verdade

| Tema | Fonte |
|---|---|
| Arquitetura implementada Control/Loja | `docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md` |
| Próxima implementação / status de planos | `docs/plans/README.md` e o bloco Status do plano |
| Operação recente | `docs/handoff-contexto.md` |
| Provisionamento loja / entitlements / inspeção de prod | `docs/2026-08-02-provisionamento-loja-entitlements.md` |
| Deploy Fly | `deploy/fly/3vm/README.md` |
| Go-live WhatsApp | `docs/go-live-chatbot.md` |
| RPA bancário | `docs/plans/*playwright*` e mapa de bancos |
| Vocabulário e ownership | `CONTEXT.md` |

`docs/plans/_archive/` é somente histórico. `docs/superpowers/plans/` não é fila
principal; specs continuam válidas quando referenciadas pelo plano canônico.

## Prioridades independentes

Escolha um eixo por mudança; não misture rollout, RPA e produto na mesma entrega.

| Eixo | Próximo resultado verificável |
|---|---|
| Rollout Control/Loja | Piloto parcial já ON em prod (shell/entitlements/atendimento/whatsapp). Residual: redirect legado opcional + validar dual-path/UX; não “ligar shell de novo” |
| Multi-WhatsApp | E2E Evolution + n8n com dois canais e resposta pelo `canal_id` correto |
| Google Ads | Configurar projeto GCP/secrets e fechar OAuth, métricas e conversões no lab |
| Motor | Smoke real por banco, sessão quente e teto de dois browsers |
| Loja | Fechar deep-links de simulação/venda no Atendimento; telemetria; redirect legado se desejado |
| Operação | Restore drill de banco/volume e revisão dos runbooks |

## Fronteiras permanentes

- Produtos se integram somente por HTTP/eventos versionados; não importe `app` de outro serviço.
- Estoque API é a fonte de verdade de veículos.
- Chatbot é a fonte de verdade de canais, leads, conversas e mensagens.
- Portal/Revy Loja é dono de vendas e metas; projeta eventos ao Revy Control.
- Motor é dono das credenciais e da execução bancária.
- Control é dono de lojas, acessos globais, pessoas/cargos, módulos e integrações técnicas.
- Credenciais, tokens, cookies e workflows preparados nunca entram no Git ou em logs.
- Suspensão operacional é gate de backend, não simples visibilidade de menu.
- Flags de rollout ficam OFF por padrão no **código** (dev/lab); em prod o piloto liga
  secrets por ops. Entitlements só ligam após projeção confiável (fail-closed).

## Mapa rápido

| Produto | Entrada / área principal |
|---|---|
| Chatbot | `chatbot-api/app/main.py`, domínio em `app/servico.py` |
| Motor | `motor-simulacao/app/main.py`, drivers em `app/motor/` |
| Estoque | `estoque-api/app/main.py` |
| Revy Loja | `portal-gestao/app/main.py`, `app/loja/`, `app/web/` |
| Revy Control | `revy-trafego/app/main.py`, `app/control/`, `app/web/control*.py` |
| Catálogo | `catalogo-publico/app/main.py` |
| Orquestração | `n8n/workflow-ai-nao-salvos.json` |

## Verificação mínima

```powershell
cd portal-gestao
.\.venv\Scripts\python.exe -m pytest -q

cd ..\chatbot-api
.\.venv\Scripts\python.exe -m pytest -q

cd ..\motor-simulacao
.\.venv\Scripts\python.exe -m pytest -q

cd ..\estoque-api
.\.venv\Scripts\python.exe -m pytest -q
```

O workflow de teste `n8n/workflow-teste-numero-autorizado.json` é usado ativamente e
deve ser preservado. Valide ambos os workflows com os scripts em `n8n/`.

## Regras de operação

- Não recrie apps Fly monolíticos antigos.
- Não destrua apps, volumes, snapshots ou bancos sem pedido explícito.
- Não trate contagens antigas de testes ou releases registrados em documentos como estado atual.
- Não use `git clean -fdX`: ele apagaria venvs, segredos, Graphify e sessões do Motor.
- Antes de concluir: testes relevantes, `git diff --check` e `git status --short`.
