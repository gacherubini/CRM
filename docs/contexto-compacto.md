# Contexto compacto para continuidade

Atualizado em **2026-08-03 (noite)**. Este é o ponto de entrada para estado e prioridades.
O desenho implementado está em
[`design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md),
os termos do domínio em [`../CONTEXT.md`](../CONTEXT.md) e os planos válidos em
[`plans/README.md`](plans/README.md).

## Estado atual

- **Revy Control:** código lean F0–F6 em `revy-trafego`. Defaults de flags no **código** OFF.
- **Revy Loja:** F0–F6/F8 + entregas 2026-08-03: chat no Atendimento (envio + poll),
  Perfil, status WA persistido, Grupo do estoque no menu, redesign da tela de números.
  Seller AI adiado.
- **Prod `app2037` (piloto):** secrets shell + entitlements + atendimento + WhatsApp Loja
  **ON**; redirect legado **OFF**. Detalhe:
  [`2026-08-02-provisionamento-loja-entitlements.md`](2026-08-02-provisionamento-loja-entitlements.md).
- **n8n:** workflow oficial `WhatsApp IA - Somente Nao Salvos` (`wAiNaoSalvos0001`) importado
  (catálogo + `simular` com aviso humano e pausa do bot). **Active = owner na manhã.**
  Teste permanece separado/OFF.
- **Fly lab (noite 03/08):** machines **stopped** (app2037, n8n2037, evolution2037, suite-pg)
  para economizar; volumes intactos. Ligar: `bash deploy/fly/up-all.sh --3vm` e checklist
  em [`handoff-contexto.md`](handoff-contexto.md) § “Ligar amanhã”.
- **WhatsApp:** Chatbot dono de canais/conversas; Loja UI de canais + grupo estoque; n8n orquestra.
- **Motor:** Playwright sob demanda; simulação ao cliente ainda **humana** (bot não devolve parcela).

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
| Operação (manhã) | `up-all --3vm` → Active no workflow oficial → QR/canal Conectado → smoke bot + simulação humana |
| Rollout Control/Loja | Redirect legado opcional; dual-path ainda on |
| Multi-WhatsApp | E2E dois canais + `canal_id` correto |
| Google Ads | Secrets GCP + OAuth/métricas/conversões |
| Motor | Smoke real por banco (resultado ao cliente ainda não via bot) |
| Loja | Deep-links simulação/venda no workspace; telemetria |

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
