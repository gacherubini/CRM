---
name: revy-deploy
description: Use ao publicar qualquer coisa da Revy em producao - subir o app2037, o site em revyapp.com.br, o workflow do n8n ou o worker do motor2037 - e tambem quando o dono pergunta se algo ja esta no ar, se o deploy pegou, ou o que precisa subir depois de uma mudanca.
---

# revy-deploy

Cinco alvos, quatro comandos diferentes e seis armadilhas que ja custaram um dia
cada. Duas delas falham **em silencio**: o Cloudflare responde 200 para um preview
que ninguem esta vendo, e o n8n aceita o import deixando o workflow desativado.

Principio: **o deploy so acabou quando prod prova, do lado de fora, que esta no
SHA que voce mandou.** Comando sem erro nao e prova.

## 1. Pre-flight — sempre, e ele que bloqueia

    cd .claude/skills/revy-deploy
    python preflight.py          # Windows; no Mac do dono, python3

Ele lê o carimbo do `/healthz`, compara com o `HEAD` e diz **quais alvos mudaram**.
Sai 1 se houver bloqueio. Bloqueio nao se contorna: se resolve.

Primeira vez apos o carimbo entrar no ar, prod ainda nao tem SHA — use
`--desde <sha>` uma vez e siga.

## 2. Alvos — so sobe o que mudou

| Mudou | Sobe |
|---|---|
| `<produto>/app/**`, `<produto>/alembic/**` | `app2037` |
| `site/**` | Cloudflare Pages |
| `n8n/**` — inclui o **`systemMessage`, que e o prompt do bot** | `n8n2037` |
| `motor-simulacao/app/**` | `app2037` (motor-api) **e** `motor2037` (worker) |
| `docs/`, `tests/`, `AGENTS.md`, mapa da revy-research | nada |

O prompt do bot **nao esta no chatbot-api**. Subir o `app2037` depois de mexer no
prompt deixa o bot falando exatamente igual.

## 3. Deploy

**app2037** — o carimbo e o que torna o pos-flight possivel:

    fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false \
      --build-arg GIT_SHA=$(git rev-parse --short HEAD)

O bundle roda todas as migrations em fail-fast antes de subir os servicos: migration
quebrada = VM que nao sobe. Antes de deploy que altera schema, snapshot do volume.

**site** — o `--branch=main` nao e opcional:

    python .claude/skills/revy-deploy/preflight.py --carimbar-site
    npx wrangler pages deploy site --project-name=revyapp --branch=main

Nao e Fly. Nao precisa subir o `app2037` para trocar a landing.

**n8n2037** — a sequencia completa esta em
`revy-research/learnings/2026-08-23-import-do-n8n-desativa-o-workflow.md`. O resumo
que importa: `prepare-workflow.ps1` **so trata o `workflow-ai-nao-salvos.json`**;
`upload-and-import-workflow.ps1` faz sftp + import + publish e **para ai**; o passo
que realmente ativa e

    fly machine exec <id> "env HOME=/home/node n8n update:workflow --id=<id> --active=true" -a n8n2037

O n8n avisa que esta deprecated e manda usar `publish`. Ignore: nesta versao o
publish sozinho nao liga. Depois `fly apps restart n8n2037` — e conte ~6 min de 404
ate o webhook registrar, durante os quais a Evolution cancela o retry.

**motor2037** — so sob pedido explicito. Pre-cutover, valide sem tocar nas machines
com `--build-only`.

## 4. Pos-flight — prova, nao esperanca

    python verificar.py app2037 site

Sai 1 se prod nao estiver no SHA do `HEAD`. Enquanto sair 1, **nao diga que acabou**.

## 5. Nunca

- `fly apps destroy`, destroy de volume, `git clean -fdX`.
- Os `fly.toml` da pasta do produto: apontam para os monolitos ja destruidos.
- Imprimir valor de secret. Conferencia de secret e **pelo nome**.
- Commitar `*.ready.json` ou gerar workflow com token real dentro do repo.
- Deployar `evolution2037` de passagem: mexe na sessao do WhatsApp.

## 6. Racionalizacoes — todas ja aconteceram aqui

| O que voce vai pensar | O que e verdade |
|---|---|
| "e uma linha so, commito depois" | `fly deploy` empacota a **arvore local**. Prod passa a rodar codigo que nao existe em commit nenhum. |
| "o comando terminou sem erro, subiu" | O Fly volta a versao anterior calado. So o carimbo distingue. |
| "o wrangler respondeu 200" | Preview responde 200. Sem `--branch=main` o dominio segue na versao velha. |
| "o publish ja ativou o workflow" | Nao ativou. Webhook em 404 **para sempre** ate o `update --active=true`. |
| "reinicio o n8n so por garantia" | Cada restart custa ~6 min de 404 com a Evolution cancelando retry. |
| "o alembic disse que esta em dia" | Sem `CHATBOT_DATABASE_URL` ele responde do SQLite local e mente. |
| "so mexi no CSS, nao precisa bumpar" | Sem bumpar o `?v=`, prod serve o CSS antigo e a mudanca nao aparece. |
| "bumpei o base.html" | Login, convite e as telas de senha tem `?v=` proprio. |

## 7. Pare e pergunte

- Pre-flight bloqueou e voce ia deployar assim mesmo.
- O alvo e `motor2037` ou `evolution2037` sem o dono ter pedido.
- Migration nova e voce nao tem snapshot do volume.
- O pos-flight reprovou duas vezes seguidas: e outro problema, nao mais deploy.

## Testes

    cd .claude/skills/revy-deploy
    python -m pytest -q          # Windows
    python3 -m pytest -q         # Mac do dono
