# Histórico — lab Fly 3-VM

Contexto que saiu de `deploy/fly/3vm/README.md`.

## Por que a stack está dividida em duas regiões (2026-07-31)

`gru` é a região **mais cara da Fly**: markup de **1,615** sobre a tabela base, contra
**1,0** de `iad` (valor publicado em `regionMarkups` na página de preços). Migrar os quatro
always-on derrubou o custo com tudo ligado de **~US$ 36,80 para ~US$ 20,28/mês**.

O `motor2037` **fica em `gru` de propósito**: os drivers Playwright logam em portal de
lojista brasileiro e já falham com `captcha_login` por reputação de IP de datacenter
(`docs/referencia-viva/planos/2026-07-16-fly-rpa-captcha-opcoes.md`). IP dos EUA piora o scoring e arrisca
geo-block; e como as machines ficam `stopped`, mover não economizaria nada.

**Consequência aceita:** `motor2037` (`gru`) consulta `suite-pg` (`iad`) via `flycast`,
então cada query do RPA custa ~120ms de RTT. Decisão do owner em 2026-07-30. Se o RPA
degradar de forma perceptível, a saída é dar ao motor um Postgres próprio em `gru`.

**Pendência após a migração:** o volume da Evolution nasceu vazio — os números de WhatsApp
precisam ser pareados de novo por QR, em Ajustes na Revy Loja.

## Por que o catálogo saiu de `/loja/` para `/catalogo/` (2026-07-31)

`/loja/` colidia com o vocabulário do shell Revy Loja, que vive em `/app/loja/…` no Portal.
`/loja/` no edge redireciona 301 para `/catalogo/`.

## Cutover do motor para worker-only

Se `motor2037` ainda tiver process group `app` (API HTTP :8000 do perfil
`motor-simulacao/fly.toml`), **não** rode o deploy completo worker-only até a motor-api
estar healthy em `app2037` e os clientes apontando para o bundle.

```bash
# PERIGOSO pré-cutover — remove [[services]] / process `app` e derruba a API:
# fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false

# Seguro: só validar/buildar a imagem (não aplica release às machines)
fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --build-only
```

Ordem recomendada:

1. Secrets de fan-out em **`app2037`** (`FLY_API_TOKEN` com scope no app `motor2037`).
2. Deploy **`app2037`** healthy (`curl 127.0.0.1:8004/health/ready` → ok; mock 2xx).
3. Tráfego só no bundle (`app2037`); monólitos legados já não existem.
4. Opcional: `--build-only` + `fly machine update` nos **slots** `motor-worker-*`
   (imagem nova) **sem** mexer no process `app` ainda.
5. Deploy worker-only: `fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false`.
6. Confirmar: `fly machines list -a motor2037` → sem machine `app` started 24/7;
   só seed stopped + slots stopped.
7. Smoke mock em `app2037` (nenhuma VM 4 sobe) → smoke 1 banco real (1 machine started →
   stopped).

### O que o deploy worker-only faz / não faz

| Faz | Não faz |
|-----|---------|
| Publica imagem `registry.fly.io/motor2037:…` com Chromium + entrypoint on-demand | Criar/acordar slots `motor-worker-*` por si só |
| Atualiza a machine **Launch** do app (seed; `MOTOR_WORKER_SEED=1` → exit 0 → **stopped**) | Manter `min_machines` / HTTP always-on do perfil legado |
| Deixa app **sem** `[[http_service]]` / `[[services]]` | Migrar o inventário `worker_slots` |
| size Launch seed = `shared-cpu-2x` / **2048 MB** | Destruir apps (`fly apps destroy` proibido sem pedido) |

### Alinhar os slots Playwright existentes

Slots (`motor-worker-santander`, `fontecred`, `bradesco`, `pan`) são Machines **fora** do
Fly Launch. Depois de publicar a imagem:

```bash
fly image show -a motor2037
fly machines list -a motor2037

# IMG=registry.fly.io/motor2037:deployment-XXXXXXXX
# fly machine update <ID> -a motor2037 --image "$IMG" --yes   # um por slot
# NÃO rode machine update no process group `app` (API always-on) pré-cutover.
```

Cada slot deve ter (já é o padrão atual):

- entrypoint `/srv/scripts/on-demand-worker-entrypoint.sh`
- `MOTOR_WORKER_PROVEDOR=<santander|fontecred|bradesco|pan>`
- `MOTOR_WORKER_ON_DEMAND=1`, `MOTOR_WORKER_TIPOS=playwright`
- restart policy **`on-failure`** (exit 0 após idle → machine **stopped**)
- size `shared-cpu-2x` / **2048 MB**, **sem** serviço HTTP

Registrar IDs no Postgres do Motor (tabela `worker_slots`):

```bash
bash deploy/fly/sync-motor-worker-machines.sh \
  santander:286501db405d68 fontecred:48ed461ce22718 \
  bradesco:1850921c91d648 pan:080e207bed0068
```

## Rollback

Monólitos legados (`portal2037`, `catalogo2037`, `estoque2037`, `chatbot2037`, `site2037`)
foram removidos a pedido do owner e **não** estão mais no inventário. Rollback realista:

1. Stop / redeploy `app2037` se o bundle estiver quebrado.
2. Motor: se precisar da API HTTP de novo em `motor2037`, redeploy
   `motor-simulacao/fly.toml` (orquestrador + serviço HTTP) **só** com intenção explícita
   — e reaponte quem consumir essa URL.
3. Evolution / Postgres: não destruir `suite-pg` nem volume da Evolution sem intenção de
   zerar sessão WA e dados.
4. Recriar monólitos legados só se o owner pedir (não é o path padrão).

## Feito no cutover 3-VM

Monólitos legados removidos; bundle `app2037` + Evolution isolada; workflow n8n
importado/publicado; webhook Evolution → `n8n2037` `/webhook/whatsapp-ai`; roteamento de
mensagens no chatbot (3 casos); portal dono; `MOTOR_ENCRYPTION_KEY` no Motor para Acessos
bancos.

Residual **operacional** (não de deploy): credencial Gemini no n8n (UI); E2E estável de 1ª
conversa; transcritor de áudio real (hoje fallback para texto).
