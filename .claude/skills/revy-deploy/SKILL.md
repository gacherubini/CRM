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
| `n8n/**` — inclui o **`systemMessage`, que e a operacao do bot** | `n8n2037` |
| `chatbot-api/app/agente_prompt.py` — identidade e tom **de cada loja** | `app2037` |
| `motor-simulacao/app/**` | `app2037` (motor-api) **e** `motor2037` (worker) |
| `docs/`, `tests/`, `AGENTS.md`, mapa da revy-research | nada |

**Desde 25/08 o prompt do bot tem duas metades, e elas sobem em lugares diferentes.**
A **operacao** (jornada, ferramentas, anti-alucinacao) e o `systemMessage` no
`n8n/workflow-ai-nao-salvos.json` → `n8n2037`. A **identidade, o tom e as regras de cada
loja**, mais o nucleo Revy, sao gerados em `chatbot-api/app/agente_prompt.py` e servidos
por `GET /v1/agente/config` → `app2037`, e valem na proxima mensagem de cliente, sem
tocar no n8n.

Se voce nao sabe qual metade mexeu: procure o texto no `systemMessage`. Se nao estiver la,
e do gerador.

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

**n8n2037** — desde 24/08 os dois scripts cobrem os tres modos, e a sequencia inteira
cabe em tres comandos:

    .\deploy\fly\3vm\prepare-workflow.ps1 -Mode production|test|cloud|preview
    .\deploy\fly\3vm\upload-and-import-workflow.ps1 -Mode production|test|cloud|preview
    fly apps restart n8n2037

O `upload` agora faz o `update:workflow --active=true` sozinho — antes ele parava no
`publish` e o passo que realmente ativa ficava na mao, esquecido. O n8n avisa que o
comando esta deprecated e manda usar `publish`: ignore, nesta versao o publish sozinho
nao liga e o webhook fica **404 para sempre**. Confira com
`n8n list:workflow --active=true` (o `list:workflow` puro nao distingue).

**`-Mode preview`** publica o workflow da tela de configuracao do agente (o lojista
conversa com o rascunho antes de publicar). Ele e **gerado** —
`python n8n/build_preview_workflow.py` — e usa `CHATBOT_API_TOKEN_CLOUD` pela mesma razao
do Modo 2: serve N lojas e diz de qual fala pela `instance`. Depois de publicar, o secret
`CHATBOT_AGENTE_PREVIEW_URL` no `app2037` aponta para
`https://n8n2037.fly.dev/webhook/whatsapp-ai-preview`; sem ele a rota responde 503 e a
tela esconde o botao Testar (default seguro, nao bug).

**`-Mode cloud` e `-Mode preview` exigem `CHATBOT_API_TOKEN_CLOUD`** no `.secrets.local` e
falham sem ela.
Reusar o `CHATBOT_API_TOKEN` ali ressuscita o bug multi-loja da spec §6.2 — o token do
Modo 1 aponta para uma loja so, e o sintoma e silencio. Ver
`deploy/fly/3vm/README.md`, secao Workflow cloud.

**Agente por loja: a ordem importa, e ela tem tres passos, nao um.**

1. `app2037` primeiro. Workflow subindo antes busca `GET /v1/agente/config` numa rota que
   nao existe — e por isso o fallback do no de config nao e luxo.
2. **Semear a config da loja que ja atendia**, ainda antes do workflow:
   `fly ssh console -a app2037 -C "sh -lc 'cd /srv/chatbot && DATABASE_URL=\$CHATBOT_DATABASE_URL python -m scripts.semear_config_agente moto-center'"`.
   Duas coisas que o palpite natural erra: o slug e **`moto-center`** (e assim que a loja
   do piloto esta gravada; "vitor motos" e so o nome no prompt), e a variavel e
   **`DATABASE_URL`** — `app/db.py` le essa, e num shell avulso o entrypoint nao traduziu
   `CHATBOT_DATABASE_URL`, entao so ela faz o engine responder SQLite e mentir. O script
   recusa os dois casos. Sem este passo a loja estreia se apresentando como "loja".
3. So entao `-Mode production`. Teste de aceite: a loja **nao muda de jeito de falar** no
   dia do deploy. Se mudar, e bug.

Depois do restart, conte ate ~6 min de 404 com a Evolution cancelando retry. (Em 24/08 o
webhook voltou em ~30 s; um caso so nao derruba o numero — planeje pelo pior.)

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
