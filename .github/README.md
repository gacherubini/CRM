# CI/CD da Revy

Cinco workflows. Cada um tem um gatilho e um destino, e nenhum depende do outro.

| Workflow | Dispara quando | Faz |
|---|---|---|
| `pr-gate.yml` | PR para `main` | testes dos 6 produtos, migrations em Postgres, n8n, varredura de segredo |
| `deploy-fly.yml` | push na `main` tocando produto ou `deploy/fly/3vm/` | sobe `app2037` (e `motor2037` quando o motor muda), com smoke e rollback |
| `deploy-site.yml` | push na `main` tocando `site/` | Cloudflare Pages, `revyapp.com.br` |
| `deploy-n8n.yml` | push na `main` tocando `n8n/` | gera o `.ready.json`, importa, **ativa** e espera o webhook voltar |
| `e2e-bancos.yml` | só na mão (`workflow_dispatch`) | `probe_todos.py` contra os portais reais, em runner self-hosted |

O corte é por destino de deploy, não por produto: os seis produtos de aplicação
sobem juntos no bundle `app2037`, o site vai para o Cloudflare e o n8n é outra
API. Um PR que mexe em `portal-gestao/` e em `site/` dispara dois deploys
independentes; um falhar não segura o outro.

---

## 1. Ligar o portão de merge

Os workflows sozinhos só pintam um ✗. O que trava o botão de merge é branch
protection, e ela ainda não existe na `main`. Um comando:

```bash
gh api -X PUT repos/gacherubini/CRM/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": { "strict": false, "contexts": ["gate"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Três escolhas aí, e o motivo de cada uma:

- **`contexts: ["gate"]`, um check só.** O `gate` é um job que depende de todos
  os outros e só passa se todos passarem. Exigir `testes / portal-gestao` pelo
  nome travaria o merge no dia em que um produto nascesse, sumisse ou mudasse de
  nome — a matriz muda, o `gate` não.
- **`strict: false`.** Com `true`, todo merge na `main` obriga cada PR aberto a
  atualizar e rodar o CI de novo. Você trabalha sozinho; isso seria fila à toa.
- **`enforce_admins: false`.** Deixa você furar a fila às 3 da manhã quando a
  produção está queimando. A trava existe para o dia normal.

Conferir depois: `gh api repos/gacherubini/CRM/branches/main/protection --jq .required_status_checks`

---

## 2. Secrets que os deploys precisam

Nenhum workflow roda antes destes existirem. Os quatro primeiros são de deploy;
os de banco estão na seção 4.

| Secret | Usado por | Como tirar |
|---|---|---|
| `FLY_API_TOKEN` | `deploy-fly` | `fly tokens create deploy -a app2037 -x 8760h` |
| `FLY_API_TOKEN_N8N` | `deploy-n8n` | `fly tokens create org -x 8760h` — precisa de escopo maior: o job usa `ssh sftp` e `machine exec`, que token de deploy não cobre |
| `CLOUDFLARE_API_TOKEN` | `deploy-site` | dash.cloudflare.com → My Profile → API Tokens → **Create Custom Token** com `Account` → `Cloudflare Pages` → **Edit**. O template *Edit Cloudflare Workers* não cobre Pages |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy-site` | canto direito do dashboard do Cloudflare |
| `CHATBOT_WEBHOOK_TOKEN` | `deploy-n8n` | mesmo valor de `deploy/fly/3vm/.secrets.local` |
| `EVOLUTION_API_KEY` | `deploy-n8n` | idem |

```bash
fly tokens create deploy -a app2037 -x 8760h -n actions-deploy-app2037 | gh secret set FLY_API_TOKEN
fly tokens create org -o crm-419 -x 8760h -n actions-n8n-ssh           | gh secret set FLY_API_TOKEN_N8N

# Os que já existem em arquivo local
gh secret set CHATBOT_WEBHOOK_TOKEN   # de deploy/fly/3vm/.secrets.local
gh secret set EVOLUTION_API_KEY       # de deploy/fly/3vm/.evolution_key.local

# Cloudflare: o `gh` pergunta "Paste your secret:", cola e dá Enter
gh secret set CLOUDFLARE_API_TOKEN
npx wrangler@3 whoami | grep -A2 'Account ID'   # pega o id e grava:
gh secret set CLOUDFLARE_ACCOUNT_ID
```

Dois tokens do Fly de propósito. O de deploy é estreito e vive no workflow que
roda a cada push; o de org é largo e só o `deploy-n8n` usa.

> `EVOLUTION_API_KEY` **não** está no `.secrets.local`. Ela mora em
> `.evolution_key.local`, que é o segundo lugar da cadeia que o
> `prepare-workflow.ps1` consulta (`env` → `.evolution_key.local` →
> `.secrets.local`).

---

## 3. Deploy automático: o que acontece de verdade

Merge na `main` sobe sozinho, sem parar para aprovação. A sequência que torna
isso seguro está no `deploy-fly.yml`, nesta ordem:

1. guarda a referência da imagem que está no ar hoje;
2. `fly deploy` a partir da árvore do commit da `main`;
3. bate no `https://app2037.fly.dev/healthz` por até ~7 min (o health check do
   `fly.app.toml` tem `grace_period` de 180s);
4. se o healthz não voltar 200, **redeploya a imagem guardada** e o job fica
   vermelho dizendo que o commit não está no ar.

O `/healthz` do `app2037` é agregado: exige 2xx de Chatbot, Estoque, Portal e
Revy. Uma migration ruim derruba o boot do bundle, que é fail-fast, e o rollback
pega exatamente esse caso.

**Se o rollback automático não estiver disponível** (o job avisa quando não
conseguiu ler a imagem atual), o manual é:

```bash
fly releases --app app2037
fly deploy --app app2037 --image <ref-anterior> --strategy immediate
```

### O que o deploy não faz

As machines por banco do motor (`motor-worker-bradesco`, `motor-worker-pan`, …)
são machines avulsas e **não** pegam `fly deploy`. O job imprime o lembrete no
resumo da execução. Para atualizar:

```bash
fly machine list --app motor2037
fly machine update <id> --app motor2037 --image <imagem-nova> --yes
```

### n8n custa 6 minutos de bot mudo

`deploy-n8n.yml` reinicia o `n8n2037`, e o webhook leva alguns minutos para
registrar de novo. Nessa janela a Evolution recebe 404 — e ela **cancela** o
retry no 404, não reenfileira. O job espera o webhook voltar antes de dizer que
deu certo, em vez de terminar verde com o bot morto, mas a janela existe. Se for
horário de movimento, mexa em `n8n/` fora dele.

---

## 4. Credenciais dos bancos

Trinta variáveis, em dois cofres diferentes do GitHub:

- **Secret** — escrita só, ninguém lê de volta (nem você): senha de portal,
  usuário, CPF, data de nascimento, celular.
- **Variable** — visível e editável na interface: placa, valor, prazo, UF,
  entrada, categoria, headless.

O split existe porque `gh secret` é via de mão única. Parâmetro de simulação
você precisa conseguir conferir; senha, não.

### Rotacionar uma senha que o portal invalidou

```powershell
# Windows
.\deploy\ci\secrets.ps1 set MOTOR_BRADESCO_SENHA
```

```bash
# macOS
./deploy/ci/secrets.sh set MOTOR_BRADESCO_SENHA
```

Pede o valor sem mostrar na tela e grava **nos dois lugares na mesma chamada**:
`motor-simulacao/.env.local` e o GitHub. É por isso que não dá para esquecer um
lado e descobrir a divergência quando o probe falha.

Outros comandos:

| Comando | O que faz |
|---|---|
| `secrets.ps1 push` | manda para o GitHub tudo que já está no `.env.local` (use uma vez, no começo) |
| `secrets.ps1 list` | lista o que existe no GitHub **e quando cada um mudou** — é o que responde "essa senha é de quando?" |
| `secrets.ps1 check` | compara os nomes dos dois lados e diz o que falta onde |

Rodando de um worktree, o `.env.local` está na árvore principal. Aponte:

```powershell
.\deploy\ci\secrets.ps1 push -EnvLocal C:\caminho\da\arvore\motor-simulacao\.env.local
```

```bash
ENV_LOCAL=/caminho/da/arvore/motor-simulacao/.env.local ./deploy/ci/secrets.sh push
```

> O script grava por arquivo temporário e `cmd /c`, não por pipe. Medido em
> 19/09/2026: `$valor | gh secret set` no PowerShell 5.1 prefixa um U+FEFF
> invisível no valor, e `--body` põe a senha na linha de comando. Os dois
> caminhos óbvios estão errados; não "simplifique" para eles.

### Adicionar um banco novo

Não precisa editar YAML. O workflow monta o `.env.local` a partir de tudo que
tem prefixo `MOTOR_`, `PROBE_` ou `MOTRIX_`. Basta:

```powershell
.\deploy\ci\secrets.ps1 set MOTOR_BANCONOVO_USUARIO
.\deploy\ci\secrets.ps1 set MOTOR_BANCONOVO_SENHA
```

---

## 5. Rodar o E2E dos bancos

Fica fora do caminho de merge de propósito: cada rodada gasta um login real em
cada portal, o Bradesco passa de 4 min só na etapa de análise, e o runner do
GitHub é IP de datacenter — que é justamente a suspeita de bloqueio que já trava
o Bradesco. Não tem `schedule` e não roda em PR.

### Direto na sua máquina (mais simples)

```powershell
cd motor-simulacao
.\.venv\Scripts\python.exe scripts\probe_todos.py
.\.venv\Scripts\python.exe scripts\probe_todos.py --bancos bradesco,pan
```

```bash
# macOS
cd motor-simulacao
.venv/bin/python scripts/probe_todos.py
```

Lê o `.env.local` direto. Não precisa de GitHub, Fly nem banco de dados.

### Pelo GitHub, na sua máquina

Mesma coisa, mas quem injeta as credenciais é o workflow (então o `.env.local`
não precisa estar em dia) e fica registro da rodada:

```bash
gh workflow run e2e-bancos.yml -f bancos=bradesco,pan
gh run watch
```

Exige o runner self-hosted instalado uma vez:

```bash
# pega o token e as instruções da sua plataforma
gh api -X POST repos/gacherubini/CRM/actions/runners/registration-token --jq .token
```

Instruções completas em Settings → Actions → Runners → New self-hosted runner.

Duas coisas na hora de instalar:

- **Não instale como serviço** se quiser ver a janela do navegador. Serviço do
  Windows não tem sessão gráfica e o Playwright headed não abre. Rodando
  `run.cmd` num terminal aberto, o headed funciona. Como serviço, dispare com
  `-f headless=true`.
- Repo público aceita PR de fork, e runner self-hosted executa código. O
  `e2e-bancos.yml` nunca dispara por `pull_request`, só na mão, então um fork
  não alcança a sua máquina. Mantenha assim, e em Settings → Actions → General
  deixe *Require approval for all external contributors*.

Screenshot de falha **não** sobe como artifact. Artifact de repo público é
baixável por qualquer um e a tela de erro do portal está com o CPF preenchido.
As imagens ficam em `motor-simulacao/`, na sua máquina. O relatório em texto,
que o probe já garante não conter senha nem CPF, vai para o resumo da execução.

---

## 6. Rodar o gate na sua máquina antes de abrir o PR

```powershell
# um produto
cd portal-gestao
.\.venv\Scripts\python.exe -m pytest -q

# n8n
cd n8n; npm install
cd ..
python n8n\validate_workflow.py
node n8n\test_expressoes.js
```

```bash
# macOS
cd portal-gestao && .venv/bin/python -m pytest -q
```

O único pedaço que o CI roda e você não tem local é o `migrations PG`: cada
suíte do repo usa SQLite in-memory, então o que quebra só em Postgres
(`batch_alter_table`, tipo, constraint nomeada) não aparece no seu pytest. Se
quiser reproduzir:

```bash
docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=ci -e POSTGRES_USER=ci -e POSTGRES_DB=ci postgres:16-alpine
cd portal-gestao
PORTAL_DATABASE_URL=postgresql+psycopg://ci:ci@localhost:5432/ci alembic upgrade head
```
