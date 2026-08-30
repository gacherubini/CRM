# Revy — instruções para agentes

Leia este arquivo e pare. Não abra `docs/` inteiro, não abra `app/main.py`
inteiro, não abra um plano de 3 mil linhas “para se contextualizar”.

## 1. Antes de qualquer ferramenta

0. Invoque a skill `revy-research`. Ela dá `arquivo:linha` de tudo, as
   armadilhas conhecidas e as decisões que não se re-propõem.
1. Identifique o **um** produto da tarefa (tabela abaixo).
2. Leia **só** o `README.md` daquele produto (armadilhas + onde editar).
3. Ache o símbolo com `rg`. Leia o módulo do domínio, não o bootstrap.
4. Se for implementar algo da fila: abra **um** card em `docs/fila/`.
5. Se for entender código já feito: abra **um** arquivo em `docs/referencia-viva/`.
6. `docs/nao-plano/` não entra no boot. Só se o humano pedir história, marca ou tutorial.

Teto: no máximo **3 arquivos de docs** antes da primeira edição. Se passou disso,
você está relendo o monorepo — volte ao card da tarefa.

## 2. Mapa (não explore o resto)

| Produto | Pasta | Dono de |
|---|---|---|
| Chatbot API | `chatbot-api/` | canais, leads, conversas, mensagens |
| Motor | `motor-simulacao/` | `/v1/simulacoes`, Playwright, credenciais bancárias |
| Estoque API | `estoque-api/` | veículos, fotos, publicação |
| Revy Loja | `portal-gestao/` | CRM, vendas, metas, atendimento |
| Revy Control | `revy-trafego/` | lojas, cargos, módulos, Ads, ROI |
| Catálogo | `catalogo-publico/` | vitrine pública |
| Site | `site/` | landing + páginas legais; publica no Cloudflare Pages, **não** no Fly |
| n8n | `n8n/` | orquestração; canônico `workflow-ai-nao-salvos.json` |

Integração **só** por HTTP/evento versionado. Sem import `app` entre produtos.
Cada produto tem banco e migrations próprios.

WhatsApp: Evolution → n8n → Chatbot → Motor/Estoque; parcela **não** vai ao cliente pelo bot.
Veículos: só Estoque. Venda: Loja → outbox → Control. Segredo bancário: só Motor.

Quadro de docs: [`docs/README.md`](docs/README.md).

## 3. O que abrir (e o que não abrir)

| Tarefa | Abrir | Não abrir |
|---|---|---|
| Bug / feature num produto | `README` do produto + módulo | `docs/fila/`, handoff, specs |
| Card da fila | `docs/fila/<card>.md` **Task N + constraints** | o plano inteiro, Fases 1–6 |
| Entender as-built Control/Loja | `docs/referencia-viva/design/` as-built | planos DONE |
| Vocabulário (loja, cargo, dono) | `CONTEXT.md` | tutoriais |
| Mudança de UI Loja/Control | `docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md` | redesenhar o que o dono recusou |
| RPA / banco | README do Motor + **uma** lição Playwright | todos os `*licoes*` |
| Deploy Fly | `deploy/fly/3vm/README.md` | plano 3-VM de 600 linhas |
| Estado / prioridade | `docs/referencia-viva/contexto-compacto.md` | `handoff` (só ops recente) |
| História / marca / tutorial | `docs/nao-plano/` sob pedido | no boot |

`docs/nao-plano/arquivados/` = não executar. Código e testes vencem o bloco Status de plano antigo.

Plano novo vai para `docs/fila/`. Spec/design válido vai para `docs/referencia-viva/`. História e plano substituído vão para `docs/nao-plano/`.

## 4. Subagente — sem brief, não dispara

O pai pesquisa. O filho executa. O filho **não** relê `AGENTS.md` + contexto + fila.

Brief obrigatório (modelo em [`docs/referencia-viva/agents/task-brief.md`](docs/referencia-viva/agents/task-brief.md)):

- objetivo em uma frase
- produto + arquivos que pode tocar
- invariantes desta tarefa
- não faça (o erro óbvio)
- como saber que acabou (comando de teste)
- docs permitidos (1–3 paths)
- docs proibidos nesta tarefa

Proibido no prompt do filho: “leia o AGENTS.md e o contexto e depois faça X”.
Se o card do plano tem 1k+ linhas, o brief cola **só** a Task N + Global Constraints.

Não espalhe um eixo em vários filhos (código + Fly + n8n na mesma leva).

**Um filho por vez.** Não dispare subagentes em paralelo. Cada filho relê o repo
por conta própria, então o custo em token multiplica em vez de somar, e leva
junto o risco de dois filhos editarem o mesmo arquivo. Paralelizar só com pedido
explícito do dono — e dizendo antes quantos filhos e por quê.

Filho caro é filho mal briefado: sem `arquivo:linha` e sem a lista de docs
permitidos ele varre o monorepo inteiro para descobrir o que o brief já sabia.
Antes de disparar, pergunte se você mesmo não resolve em duas leituras.

## 5. Invariantes (quebrar = revert)

- Sem secret, token, cookie, `.env*` real ou `workflow-fly.ready.json` no git ou no log.
- Flags de rollout default OFF no código.
- Suspensão de loja é gate de backend, não item de menu.
- Estoque = veículos. Chatbot = conversa. Loja = venda. Motor = banco. Control = estrutura.
- Testes a partir da pasta do produto, senão importa o `app` errado. Cada produto tem seu
  **próprio `.venv`**, e `python` puro não existe no Mac do dono. O dono usa **Mac e Windows** —
  card novo traz as duas formas: `.venv/bin/python -m pytest -q` (macOS) e
  `.\.venv\Scripts\python.exe -m pytest -q` (Windows).
- Não destruir app/volume Fly. Não `git clean -fdX`.
- Deploy Fly só por `deploy/fly/3vm/`. Os `fly.toml` na pasta do produto apontam para
  apps monolíticos destruídos (`portal2037`, `chatbot2037`…) — não usar.
- O **site não é Fly**: publica no Cloudflare Pages com
  `npx wrangler pages deploy site --project-name=revyapp --branch=main`. Sem `--branch=main`
  o deploy vira *preview* silencioso e o domínio segue na versão anterior. Ver `site/README.md`.
- UI Loja/Control: 13 itens recusados não voltam como proposta.

## 6. Antes de dizer que acabou

Testes do produto (e consumidores do contrato, se mudou HTTP).
Migration: `alembic upgrade head` no produto certo.
n8n: `python n8n/validate_workflow.py` na raiz — e, se mexeu na topologia ou no jsCode
de algum no, os `node n8n/test_*.js` (lista em `n8n/GUIA-WORKFLOW.md`).
`git diff --check` e `git status --short`. Não commitar mudança alheia.
Mexeu em rota, modelo, worker, migration ou flag? Regere o mapa **e a arquitetura** e
commite junto com o código: `cd .claude/skills/revy-research && python gerar_mapa.py &&
python gerar_arquitetura.py` (Windows) ou `python3 gerar_mapa.py && python3
gerar_arquitetura.py` (macOS).
Algo te surpreendeu? Escreva um learning — procurando duplicata pelo gatilho antes.
