# Migração Fly.io `gru` → `iad` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover `suite-pg`, `app2037`, `evolution2037` e `n8n2037` de `gru` para `iad`, mantendo `motor2037` em `gru`, preservando os workflows/credenciais do n8n e reduzindo o `evolution2037` para 512MB.

**Architecture:** Volume no Fly não muda de região. Cada app é migrado recriando volume + machine em `iad` e destruindo os de `gru` **só depois** do substituto verificado. Secrets, IPs anycast e certificados são app-scoped e sobrevivem sem reconfiguração. Dos 4 volumes, apenas o `n8n_data` tem conteúdo que deve sobreviver (decisão do owner, 2026-07-30); os outros três nascem vazios.

**Tech Stack:** flyctl, Fly Machines + Volumes, `flyio/postgres-flex:18.1`, `n8nio/n8n:2.26.8`, `evoapicloud/evolution-api:v2.3.7`, sqlite3 (inspeção local).

## Global Constraints

- **`motor2037` NÃO migra.** Permanece em `gru`. Razão em `docs/referencia-viva/planos/2026-07-16-fly-rpa-captcha-opcoes.md`: o RPA já falha com `captcha_login` por reputação de IP de datacenter; IP americano logando em portal de lojista brasileiro piora o scoring e arrisca geo-block. Economia de mover: ~zero (as 5 machines ficam `stopped`).
- **Só o conteúdo do `n8n_data` deve sobreviver.** `pg_data`, `app_data` e `evolution_instances` podem nascer vazios (decisão explícita do owner).
- **Nunca imprimir segredo** no terminal, log ou arquivo versionado. A `N8N_ENCRYPTION_KEY` trafega arquivo→secret sem passar por stdout.
- **Nada em `gru` é destruído antes** do substituto em `iad` responder health check.
- `evolution2037` sobe com `shared-cpu-1x:512MB`. Se acusar OOM, volta para 1024MB e o ganho desse app é abandonado.
- `deploy/fly/3vm/README.md:404` proíbe destruir `suite-pg`/volumes sem pedido do owner. **O pedido existe** (2026-07-30) e cobre `pg_data`, `app_data`, `evolution_instances`.
- Toda evidência de execução vai para `/private/tmp/.../scratchpad/migracao-iad/`, fora do repo.

## Por que (números verificados)

`regionMarkups` extraído da página de preços da Fly: **`iad` = 1.0 (baseline)**, **`gru` = 1.615384615** — o markup mais alto de toda a malha da Fly.

| App | Tamanho real | GRU/mês | IAD/mês |
|---|---|---|---|
| `app2037` | shared-cpu-1x 1536MB | $13,24 | $8,20 |
| `n8n2037` | shared-cpu-1x 1024MB | $9,20 | $5,70 |
| `evolution2037` | 1024MB → **512MB** | $9,20 | **$3,19** |
| `suite-pg` | shared-cpu-1x 512MB | $5,16 | $3,19 |
| **Total ligado** | | **$36,80** | **$20,28** |

Economia: **$16,52/mês (45%)**, já contando o downgrade do Evolution. Volumes ($0,15/GB) e o `motor2037` on-demand não mudam.

**Contexto que relativiza o ganho:** hoje só o `n8n2037` está `started`; o resto está `stopped`. O gasto corrente é ~$9,80/mês, não $36,80. A economia só se realiza com o lab no ar.

## Inventário congelado (2026-07-30)

| App | Machine | Size | Volume | Estado |
|---|---|---|---|---|
| `app2037` | `28630e2a0d4318` | 1x:1536MB | `vol_458k6nlygkw18614` (app_data, 1GB) | stopped |
| `evolution2037` | `0807561fd39268` | 1x:1024MB | `vol_vp257j13oj323wy4` (evolution_instances, 1GB) | stopped |
| `n8n2037` | `48ed9deea05418` | 1x:1024MB | `vol_42k77wj2n8zm2z74` (n8n_data, 1GB) | **started** |
| `suite-pg` | `d8946d2f320de8` | 1x:512MB | `vol_v3gzk1xpxj0d2gm4` (pg_data, 1GB) | stopped |
| `motor2037` | 5 machines (app + 4 workers) | 2x:2048MB | — | stopped, **fica em gru** |

## Riscos e decisões abertas

**R1 — `motor2037` (gru) ↔ `suite-pg` (iad) fica cross-region.** `MOTOR_DATABASE_URL` aponta para `suite-pg.flycast`. Hoje é intra-região; depois vira ~120ms de RTT por query. Um job de RPA leva ~100s e faz dezenas/centenas de queries de timeline e evento. Não é fatal, mas degrada. **Alternativas:** (a) aceitar; (b) mover `suite-pg` de volta para `gru` e migrar só `app2037`+`n8n2037` (economia cai para ~$13/mês); (c) dar ao motor um Postgres próprio em `gru`.

**DECIDIDO pelo owner em 2026-07-30: (a) aceitar a latência.** Razão: o motor é on-demand e roda esporadicamente no lab; ~$3,50/mês não se paga para evitar latência num worker cujo job já leva ~100s. A Task 3 executa normalmente. Se o RPA degradar de forma perceptível em produção, reavaliar (c).

**R2 — RESOLVIDO em 2026-07-30 (Task 2 executada).** O "no workflows" era falso negativo: `N8N_USER_FOLDER` é a pasta **que contém** o `.n8n`, e o n8n concatena `.n8n` ao valor. Passando `/home/node/.n8n` ele procurava em `/home/node/.n8n/.n8n` e criava um banco vazio. O valor correto é `N8N_USER_FOLDER=/home/node`. Conteúdo real do banco:

| Item | Quantidade |
|---|---|
| workflows | **2** |
| credentials | **1** (`Google Gemini(PaLM) Api account`, `googlePalmApi`) |
| executions | 9.755 |

**R5 (novo) — o workflow do repo está defasado em relação ao live.** `n8n/workflow-ai-nao-salvos.json` tem **25 nós**; o live `WhatsApp IA - Somente Nao Salvos` tem **31**. O live é superconjunto estrito — o repo não tem nenhum nó a mais. Faltam no repo: `Transcrever audio1`, `E audio1`, `Aplicar transcricao1`, `consultar_por_placa1`, `registrar_consentimento1`, `registrar_lead1`. Ou seja, transcrição de áudio, consulta por placa, registro de consentimento e registro de lead **só existem no banco do n8n**. O `CLAUDE.md` afirma que o arquivo do repo é canônico; **não é.** Se a migração tivesse seguido o caminho "recriar limpo e reimportar do repo", essas seis funcionalidades seriam perdidas silenciosamente.

**R6 (novo) — o export live carrega segredos reais.** `workflows.json` exportado tem **zero** placeholders (`__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`, `__CHATBOT_WEBHOOK_TOKEN__`) e 96 strings longas com cara de token. **Nunca commitar esse arquivo.** Ele fica só no scratchpad, fora do repo. Sincronizar repo ← live exige re-placeholderizar antes.

**R7 (novo) — o workflow de produção está INATIVO.** `WhatsApp IA - Somente Nao Salvos` está com `active = 0`; o único ativo é `WhatsApp IA - TESTE 5551980336365`. O lab hoje atende **só** aquele número de teste. Depois da migração, ativar o workflow certo é passo manual — não assumir que "voltou igual" significa produção no ar.

**R3 — `evolution2037` a 512MB.** Baileys com várias instâncias pode estourar. Mitigação: `fly scale memory 1024` reverte em segundos.

**R4 — `CACHE_REDIS_URI` no `evolution2037`** aponta para um Redis que não existe na lista de apps. Verificar na Task 5 se está desligado por env; se houver um Redis externo, ele não muda de região.

---

### Task 1: Congelar evidência e snapshots — ✅ EXECUTADA 2026-07-30

**Files:**
- Create: `scratchpad/migracao-iad/00-inventario.txt`

- [x] **Step 1: Criar diretório de evidência**

```bash
export SCRATCH=/private/tmp/claude-501/-Users-gabrielabreucherubini-Documents-codigo-CRM/246546f6-14b2-4a2b-bc7b-96ceac8201bf/scratchpad
mkdir -p "$SCRATCH/migracao-iad" && cd "$SCRATCH/migracao-iad"
```

`$SCRATCH` é usado em todas as tasks seguintes; reexportar em cada sessão nova.

- [x] **Step 2: Snapshot dos 4 volumes**

```bash
fly volumes snapshots create vol_42k77wj2n8zm2z74 -a n8n2037
fly volumes snapshots create vol_v3gzk1xpxj0d2gm4 -a suite-pg
fly volumes snapshots create vol_458k6nlygkw18614 -a app2037
fly volumes snapshots create vol_vp257j13oj323wy4 -a evolution2037
```

Esperado: `Scheduled to snapshot volume ...` em cada um. A Fly já mantém snapshot diário com 5 dias de retenção nesses volumes — estes são adicionais.

- [x] **Step 3: Congelar inventário e nomes de secrets**

```bash
for a in app2037 evolution2037 n8n2037 suite-pg motor2037; do
  echo "=== $a"; fly machines list -a $a; fly volumes list -a $a
  fly secrets list -a $a; fly ips list -a $a
done > 00-inventario.txt 2>&1
```

Guarda só **nomes** de secrets (o `fly secrets list` nunca mostra valor).

- [x] **Step 4: Verificar snapshots existem**

```bash
fly volumes snapshots list vol_42k77wj2n8zm2z74 -a n8n2037 | tail -3
```

Esperado: pelo menos um snapshot `created` de hoje.

**Gate:** não seguir sem os 4 snapshots confirmados.

---

### Task 2: GATE — extrair e verificar o conteúdo do n8n — ✅ PASSOU 2026-07-30

Esta é a única tarefa cujo fracasso cancela o plano inteiro. `n8n2037` está `started`, que é a condição necessária para extrair.

**Files:**
- Create: `scratchpad/migracao-iad/n8n-config` (chave de criptografia — **nunca** commitar)
- Create: `scratchpad/migracao-iad/database.sqlite`
- Create: `scratchpad/migracao-iad/workflows.json`

**Interfaces:**
- Produces: `N8N_ENCRYPTION_KEY` (string, do arquivo `config`), consumida pela Task 6.

- [x] **Step 1: Puxar a chave de criptografia sem imprimi-la**

```bash
fly ssh sftp get /home/node/.n8n/config "$SCRATCH/migracao-iad/n8n-config" -a n8n2037
test -s "$SCRATCH/migracao-iad/n8n-config" && echo "OK: config recebido ($(wc -c < "$SCRATCH/migracao-iad/n8n-config") bytes)"
```

Esperado: `OK: config recebido (56 bytes)`. **Não usar `cat`.** O arquivo é JSON `{"encryptionKey":"..."}`.

- [x] **Step 2: Puxar o banco real para inspeção local**

```bash
fly ssh sftp get /home/node/.n8n/database.sqlite "$SCRATCH/migracao-iad/database.sqlite" -a n8n2037
ls -la "$SCRATCH/migracao-iad/database.sqlite"
```

Esperado: ~447MB. Cópia de sqlite com o n8n rodando pode pegar WAL parcial; para a inspeção de contagem isso é suficiente.

- [x] **Step 3: Responder a pergunta em aberto (R2) com sqlite local**

```bash
sqlite3 "$SCRATCH/migracao-iad/database.sqlite" \
  "SELECT 'workflows', COUNT(*) FROM workflow_entity
   UNION ALL SELECT 'credentials', COUNT(*) FROM credentials_entity
   UNION ALL SELECT 'executions', COUNT(*) FROM execution_entity;"
sqlite3 "$SCRATCH/migracao-iad/database.sqlite" "SELECT id, name, active FROM workflow_entity;"
```

Esperado: uma das duas realidades, e cada uma define o caminho:

| Resultado | Leitura | Caminho |
|---|---|---|
| `workflows > 0` | O n8n tem estado real. As credenciais **só** existem aqui. | Step 4 (export) + Task 6 restaura o banco inteiro |
| `workflows = 0` | Os 447MB são histórico de execução. Nada de workflow a preservar. | Pular Step 4. Task 6 sobe n8n limpo e reimporta `n8n/workflow-ai-nao-salvos.json`; **as credenciais serão recriadas à mão pelo owner** |

- [x] **Step 4: (Só se `workflows > 0`) Exportar em formato portátil**

```bash
fly ssh console -a n8n2037 -C "env N8N_USER_FOLDER=/home/node n8n export:workflow --all --output=/tmp/workflows.json"
fly ssh sftp get /tmp/workflows.json "$SCRATCH/migracao-iad/workflows.json" -a n8n2037
python3 -c "import json,sys; d=json.load(open('$SCRATCH/migracao-iad/workflows.json')); print('workflows exportados:', len(d))"
```

Esperado: contagem igual à do Step 3. Isso dá um segundo caminho de restauração além do `database.sqlite`.

- [x] **Step 5: Registrar o veredito**

```bash
sqlite3 "$SCRATCH/migracao-iad/database.sqlite" \
  "SELECT COUNT(*) FROM workflow_entity;" > "$SCRATCH/migracao-iad/02-veredito-n8n.txt"
```

**Gate:** Task 6 não começa sem `n8n-config` no disco (>0 bytes) **e** o veredito registrado. Se o `sftp get` do banco falhar, parar e reportar — não improvisar.

---

### Task 3: `suite-pg` → `iad`

**Pré-requisito:** decisão do owner sobre **R1** (motor cross-region). Se a resposta for (b), esta task é pulada e o `suite-pg` fica em `gru`.

- [ ] **Step 1: Confirmar que os dados são descartáveis**

Releitura da constraint global: `pg_data` nasce vazio. Todos os DBs de produto (chatbot, portal, estoque, motor, revy-trafego) são recriados por migration no primeiro boot do `app2037`.

- [ ] **Step 2: Clonar a machine para iad**

```bash
fly machine clone d8946d2f320de8 --region iad -a suite-pg
fly volumes list -a suite-pg
```

**Não criar o volume à mão aqui.** `fly machine clone` provisiona automaticamente um `pg_data` novo na região destino para a machine clonada; criar antes produziria um volume órfão. Esperado: dois volumes `pg_data`, um `gru` e um `iad`.

- [ ] **Step 3: Verificar saúde**

```bash
fly machines list -a suite-pg
fly checks list -a suite-pg
```

Esperado: machine `iad` com checks passando (3/3 no postgres-flex).

- [ ] **Step 4: Destruir a machine e o volume de gru**

```bash
fly machine destroy d8946d2f320de8 --force -a suite-pg
fly volumes destroy vol_v3gzk1xpxj0d2gm4 --yes -a suite-pg
```

**Rollback:** `fly volumes create pg_data --region gru --size 1` + restaurar do snapshot `vs_...` da Task 1.

---

### Task 4: `app2037` → `iad`

- [ ] **Step 1: Criar volume em iad**

```bash
fly volumes create app_data --region iad --size 1 -a app2037 --yes
```

- [ ] **Step 2: Atualizar `primary_region` no toml**

Modify `deploy/fly/3vm/fly.app.toml:2`:

```toml
primary_region = "iad"
```

- [ ] **Step 3: Deploy a partir da raiz do repo**

```bash
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

- [ ] **Step 4: Verificar que a machine nova está em iad e saudável**

```bash
fly machines list -a app2037
curl -sS -o /dev/null -w "%{http_code}\n" https://app2037.fly.dev/healthz
```

Esperado: `200`, machine em `iad`.

- [ ] **Step 5: Destruir sobra em gru**

```bash
fly machine destroy 28630e2a0d4318 --force -a app2037
fly volumes destroy vol_458k6nlygkw18614 --yes -a app2037
```

---

### Task 5: `evolution2037` → `iad` a 512MB

- [ ] **Step 1: Checar R4 (Redis)**

```bash
fly ssh console -a evolution2037 -C "printenv CACHE_REDIS_ENABLED"
```

Se `true` e não houver Redis no org, registrar como pendência — não bloqueia a migração.

- [ ] **Step 2: Criar volume em iad**

```bash
fly volumes create evolution_instances --region iad --size 1 -a evolution2037 --yes
```

- [ ] **Step 3: Deploy (o toml já pede 512MB)**

```bash
fly deploy . -a evolution2037 -c deploy/fly/3vm/fly.canal.toml --ha=false
```

`deploy/fly/3vm/fly.canal.toml:42-43` já declara `shared-cpu-1x` / `512` — a máquina em `gru` é que estava divergente em 1024MB. Trocar `primary_region` para `iad` na linha 3.

- [ ] **Step 4: Verificar boot sem OOM**

```bash
fly machines list -a evolution2037
fly logs -a evolution2037 --no-tail | grep -iE "out of memory|OOM|killed" | tail -5
```

Esperado: nenhuma linha de OOM. Se houver: `fly scale memory 1024 -a evolution2037` e anotar que o ganho desse app não se sustenta.

- [ ] **Step 5: Re-parear o WhatsApp**

O `evolution_instances` novo está vazio: as instâncias precisam ser recriadas e o QR lido de novo, pela tela de Ajustes da Revy Loja (`portal-gestao/app/web/loja_whatsapp.py`). Registrar no handoff.

- [ ] **Step 6: Destruir sobra em gru**

```bash
fly machine destroy 0807561fd39268 --force -a evolution2037
fly volumes destroy vol_vp257j13oj323wy4 --yes -a evolution2037
```

---

### Task 6: `n8n2037` → `iad` com restauração

**Interfaces:**
- Consumes: `n8n-config` e (se aplicável) `database.sqlite` / `workflows.json` da Task 2.

- [ ] **Step 1: Fixar a chave de criptografia como secret antes do primeiro boot**

```bash
fly secrets set N8N_ENCRYPTION_KEY="$(python3 -c "import json;print(json.load(open('$SCRATCH/migracao-iad/n8n-config'))['encryptionKey'])")" -a n8n2037
```

Isso tira a chave do arquivo no volume e a torna explícita — corrige a fragilidade atual (hoje ela só existe dentro do `n8n_data`, sem backup fora do volume). O valor não aparece em stdout.

- [ ] **Step 2: Criar volume em iad e apontar o toml**

```bash
fly volumes create n8n_data --region iad --size 1 -a n8n2037 --yes
```

Modify `deploy/fly/3vm/fly.n8n.toml:3` → `primary_region = "iad"`.

- [ ] **Step 3: Deploy**

```bash
fly deploy . -a n8n2037 -c deploy/fly/3vm/fly.n8n.toml --ha=false
```

- [ ] **Step 4: Restaurar (caminho depende do veredito da Task 2)**

Se `workflows > 0`:

```bash
fly ssh sftp put "$SCRATCH/migracao-iad/workflows.json" /tmp/workflows.json -a n8n2037
fly ssh console -a n8n2037 -C "env N8N_USER_FOLDER=/home/node n8n import:workflow --input=/tmp/workflows.json"
```

Se `workflows = 0`: importar o canônico do repo.

```bash
fly ssh sftp put n8n/workflow-ai-nao-salvos.json /tmp/wf.json -a n8n2037
fly ssh console -a n8n2037 -C "env N8N_USER_FOLDER=/home/node n8n import:workflow --input=/tmp/wf.json"
```

**Nota:** o `-C` do flyctl não lida bem com aspas aninhadas. Usar a forma `env VAR=x cmd`, nunca `sh -c '...'` — foi o que produziu o falso negativo de "no workflows" (rodou como root contra `/root/.n8n`, um banco vazio).

- [ ] **Step 5: Verificar**

```bash
fly ssh console -a n8n2037 -C "env N8N_USER_FOLDER=/home/node n8n list:workflow"
curl -sS -o /dev/null -w "%{http_code}\n" https://n8n2037.fly.dev/healthz
```

Esperado: workflows listados e `200`.

- [ ] **Step 6: Reapontar o webhook da Evolution**

```bash
pwsh deploy/fly/3vm/set-evolution-webhook.ps1
```

A URL (`https://n8n2037.fly.dev/`) não muda, mas a instância da Evolution foi recriada na Task 5 e precisa reassinar.

- [ ] **Step 7: Destruir sobra em gru**

```bash
fly machine destroy 48ed9deea05418 --force -a n8n2037
fly volumes destroy vol_42k77wj2n8zm2z74 --yes -a n8n2037
```

**Gate:** só destruir depois do Step 5 verde.

---

### Task 7: Atualizar o repo

**Files:**
- Modify: `deploy/fly/3vm/fly.app.toml:2`, `fly.n8n.toml:3`, `fly.canal.toml:3` (`primary_region = "iad"`)
- Modify: `deploy/fly/3vm/fly.worker.toml:19` — **mantém `gru`**, com comentário explicando por quê
- Modify: `deploy/fly/3vm/README.md:7` (`crm-419 / gru` → topologia dividida)
- Modify: `docs/referencia-viva/handoff-contexto.md` (arquitetura do lab)

- [ ] **Step 1: Aplicar as edições de toml**

- [ ] **Step 2: Documentar a topologia dividida no README**

Tabela nova: `app2037`/`n8n2037`/`evolution2037`/`suite-pg` em `iad`; `motor2037` em `gru` com a justificativa de IP bancário e o link para `docs/referencia-viva/planos/2026-07-16-fly-rpa-captcha-opcoes.md`. Registrar R1 (motor↔pg cross-region) como característica conhecida.

- [ ] **Step 3: Validar**

```bash
git diff --check && git status --short
```

- [ ] **Step 4: Commit**

```bash
git add deploy/fly/3vm/ docs/referencia-viva/handoff-contexto.md
git commit -m "ops(fly): migra stack always-on para iad e mantem motor em gru"
```

---

### Task 8: Smoke e encerramento

- [ ] **Step 1: Subir o lab**

```bash
bash deploy/fly/up-all.sh --3vm
```

- [ ] **Step 2: Health dos quatro**

```bash
for u in app2037 n8n2037 evolution2037; do
  echo -n "$u: "; curl -sS -o /dev/null -w "%{http_code}\n" "https://$u.fly.dev/healthz"
done
fly checks list -a suite-pg
```

- [ ] **Step 3: Confirmar que nada ficou em gru além do motor**

```bash
for a in app2037 evolution2037 n8n2037 suite-pg; do fly machines list -a $a | grep -c gru; done
```

Esperado: `0` para os quatro.

- [ ] **Step 4: Conferir o custo projetado**

```bash
fly machines list -a app2037 -a n8n2037 2>/dev/null; open https://fly.io/dashboard/crm-419/billing
```

Esperado: projeção convergindo para ~$20/mês com tudo ligado.

- [ ] **Step 5: Atualizar `docs/referencia-viva/handoff-contexto.md`** com a data da migração e a pendência de re-pareamento do WhatsApp.

---

## Rollback global

Cada task destrói o recurso em `gru` só no último passo. Antes disso, reverter é apagar o recurso novo em `iad` e voltar o `primary_region` do toml. Depois disso, o caminho é recriar o volume em `gru` a partir do snapshot da Task 1 (retenção de 5 dias — **a janela de rollback é de 5 dias**, não indefinida).

O único ponto sem rollback barato é o pareamento do WhatsApp na Task 5: o QR precisa ser lido de novo no celular da loja, independente de qualquer reversão.
