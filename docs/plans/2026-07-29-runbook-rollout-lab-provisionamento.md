# Runbook — Rollout lab da projeção operacional (Revy Control)

**Objetivo:** ligar no lab Fly (`app2037`) o código **já no `main`**: outbox de
provisionamento + projeção nos 5 destinos + gates. **Sem feature nova.**

**App:** `app2037` · org `crm-419` · região `gru`  
**Público Control:** `https://app2037.fly.dev/trafego`  
**Status:** checklist operacional (2026-07-29)

---

## 0. Pré-condições

- [ ] Lab up: `bash deploy/fly/up-all.sh --3vm`
- [ ] `fly status -a app2037` com machine running
- [ ] Código deployado = `main` ≥ `573348e` (fan-out motor/catalogo)
- [ ] Snapshot/backup do volume `/data` **antes** das migrations (Fase 0 residual)

```bash
# Snapshot volume (ajuste o id do volume se necessário)
fly volumes list -a app2037
# Preferir snapshot agendado já existente; se criar manual, anotar horário
```

---

## 1. Migrations (automáticas no boot)

O `entrypoint-app.sh` roda `alembic upgrade head` fail-fast em:

| Serviço | Path no container | Head esperado (projeção) |
|---|---|---|
| Chatbot | `/srv/chatbot` | `0014_loja_operacional_projecao` |
| Estoque | `/srv/estoque` | `0008_loja_operacional_projecao` |
| Motor | `/srv/motor` | `0014_cliente_operacional_projecao` |
| Portal | `/srv/portal` | `0013_loja_operacional_projecao` |
| Revy Control | `/srv/revy-trafego` | `0013_revy_control_readiness_alert_acceptances` (após `0011` metrics + `0012` conversions) |

Catálogo **não** usa Alembic: SQLite em `CATALOGO_DATABASE_PATH` (tabela criada no
primeiro `apply` / boot do módulo de provisioning).

```bash
# Deploy (rebuild + restart → entrypoint migra)
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false

# Se a machine ficar stopped:
fly machine list -a app2037
fly machine start <id> -a app2037

# Confirmar health
curl -sS https://app2037.fly.dev/healthz | head
curl -sS https://app2037.fly.dev/trafego/health/live
curl -sS https://app2037.fly.dev/trafego/health/ready
```

Se o boot falhar em alembic, o log do entrypoint mostra o diretório. **Não** ligar
flags de delivery até migrations OK.

---

## 2. Secrets / env (piloto de 1 loja)

Substitua `LOJA_SLUG` (ex.: `moto-center`) e tokens **já existentes** no lab.
Gerar tokens novos só se o lab ainda não tiver credenciais de serviço por loja.

### 2.1 Control (entrega)

```bash
# Flags — ligar delivery; UI Control só se for usar o painel
fly secrets set --stage \
  REVY_CONTROL_ENABLED=1 \
  REVY_CONTROL_RBAC_ENABLED=0 \
  REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1 \
  REVY_CONTROL_PROVISIONING_INTERVAL_SECONDS=30 \
  REVY_CONTROL_PROVISIONING_INITIAL_DELAY_SECONDS=10 \
  -a app2037
```

> `REVY_CONTROL_RBAC_ENABLED=0` no primeiro piloto evita travar gestores legados.
> Ligue RBAC só depois de vínculos e smoke de isolamento.

### 2.2 Destinos (URLs internas já default no entrypoint)

No bundle, defaults locais bastam:

| Destino | URL default no process |
|---|---|
| Chatbot | `http://127.0.0.1:8001` |
| Estoque | `http://127.0.0.1:8002` |
| Motor | `http://127.0.0.1:8004` |
| Portal | `http://127.0.0.1:9000` |
| Catálogo | via edge/processo local (ver `run-catalogo.sh`) |

### 2.3 Tokens de entrega (Control → destinos)

```bash
# Chatbot + Estoque + Motor: Bearer por loja (JSON) OU token único + LOJAS
fly secrets set --stage \
  REVY_TRAFEGO_CHATBOT_TOKENS_JSON='{"LOJA_SLUG":"TOKEN_CHATBOT_DA_LOJA"}' \
  REVY_TRAFEGO_ESTOQUE_TOKENS_JSON='{"LOJA_SLUG":"TOKEN_ESTOQUE_DA_LOJA"}' \
  REVY_TRAFEGO_MOTOR_TOKENS_JSON='{"LOJA_SLUG":"TOKEN_MOTOR_DO_CLIENTE"}' \
  -a app2037

# Portal + Catálogo: X-Service-Token compartilhado (gerar se ainda não existir)
fly secrets set --stage \
  PORTAL_SERVICE_TOKEN='GERAR_TOKEN_FORTE' \
  PORTAL_API_URL='http://127.0.0.1:9000' \
  CATALOGO_SERVICE_TOKEN='GERAR_TOKEN_FORTE' \
  CATALOGO_PUBLIC_URL='http://127.0.0.1:8003' \
  -a app2037
```

**Regras:**

- Token Chatbot/Estoque/Motor deve ser o **mesmo Bearer** que a loja/cliente já usa
  nas APIs (credencial no DB de cada serviço).
- `PORTAL_SERVICE_TOKEN` no processo Portal = valor que o Control envia em
  `X-Service-Token` (mesmo secret nos dois lados se for um único env no bundle).
- Catálogo: `CATALOGO_SERVICE_TOKEN` idem.

Aplicar secrets staged:

```bash
# Liberar staged secrets (reinicia machines)
fly secrets deploy -a app2037
```

---

## 3. Smoke funcional (1 loja)

### 3.1 Login Control

1. Abrir `https://app2037.fly.dev/trafego/login`
2. Entrar com bootstrap / admin Revy
3. Com `REVY_CONTROL_ENABLED=1`, abrir `/trafego/app/control/lojas`

### 3.2 Garantir loja canônica

- Slug lab = `LOJA_SLUG` usado nos JSON de tokens
- Módulos Vendas + Estoque ativos (se a loja for operar os dois)
- Pelo menos um Dono com acesso ativável se for marcar `pronta`

### 3.3 Forçar projeção

1. Transicionar loja `em_configuracao` → `pronta` → `ativa` **ou** suspender módulo
2. Esperar ≤ 1 intervalo do worker (~30s) **ou** reiniciar após secrets
3. Conferir outbox no SQLite do Revy (ssh):

```bash
fly ssh console -a app2037 -C "python - <<'PY'
import sqlite3
c=sqlite3.connect('/data/revy-trafego/revy_trafego.db')
for row in c.execute('select destination,status,attempts,substr(event_id,1,60) from control_provisioning_outbox order by created_at desc limit 20'):
    print(row)
PY"
```

Esperado: linhas `chatbot|estoque|portal|motor|catalogo` em `delivered` (ou `pending`
logo após mutação, depois `delivered`). `failed` com `attempts < 5` reprocessa.

### 3.4 Gates por destino

| Destino | Como testar | Esperado com loja **ativa** | Esperado com loja **suspensa** |
|---|---|---|---|
| Chatbot | `POST /v1/simular` Bearer loja | 2xx/202 | **423** `store_not_operational` |
| Estoque | `POST /v1/veiculos` Bearer loja | 201 | **423** |
| Portal | UI nova venda | registra | redirect `?erro=loja-nao-operacional` |
| Motor | `POST /v1/simulacoes` Bearer cliente | 202 | **423** |
| Catálogo | `GET /loja/l/LOJA_SLUG` | vitrine | **404** genérico (se houver projeção) |

**Catálogo é fail-open:** sem nenhuma projeção a vitrine continua. Só esconde depois
que o Control entregou estado e a loja/módulo não está operacional.

### 3.5 Reativar

1. Reativar loja/módulo no Control  
2. Aguardar delivery  
3. Repetir um write em Chatbot/Estoque — deve voltar a 2xx  

---

## 4. Rollback rápido

```bash
# 1) Desliga entrega (outbox para de processar; mutações ainda enfileiram)
fly secrets set \
  REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=0 \
  -a app2037

# 2) Se o painel Control atrapalhar o tráfego legado
fly secrets set \
  REVY_CONTROL_ENABLED=0 \
  -a app2037
```

Gates nos destinos: se a projeção ficou `suspensa`/`ativa` no destino, **reativar no
Control** (com delivery on) ou limpar projeção no destino (último recurso, por SQL).

Não apagar tabelas de projeção em massa sem snapshot.

---

## 5. Ordem recomendada (piloto)

1. Deploy `main` (migrations)  
2. Secrets de tokens **sem** delivery  
3. Smoke login + loja no Control  
4. `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1`  
5. Mutação → outbox delivered  
6. Gate suspensa → reativa  
7. Só então considerar `REVY_CONTROL_RBAC_ENABLED=1`  

---

## 6. Flags e smoke — superfícies Revy Control (código F0–6 lean)

Checklist de **feature flags** (todas default off no código) e endpoints de smoke
para validar no lab **depois** das migrations. Não liga tudo de uma vez.

### 6.1 Flags

| Flag | Superfície | Smoke mínimo |
|---|---|---|
| `REVY_CONTROL_ENABLED=1` | API `/control/v1/*` e UI `/app/control/*` (exceto dashboard se flag própria) | login + `GET /trafego/control/v1/lojas` (com sessão) |
| `REVY_CONTROL_RBAC_ENABLED=1` | Escopo por vínculo em listagens/mutações de gestor | gestor A não vê loja B (403/404) |
| `REVY_CONTROL_DASHBOARD_ENABLED=1` | `GET /control/v1/dashboard` + `/app/control/dashboard` | JSON com `counts`, `items`, `pending_readiness`, `integrations` |
| `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED=1` | Worker outbox → 5 destinos | ver §3 |
| `GOOGLE_ADS_SYNC_ENABLED=1` | OAuth/conexão Google Ads | rotas Google sob `/control/v1/...` (sem métricas F4B) |
| `GOOGLE_CONVERSIONS_ENABLED=1` | Devolução de conversões (F4D; ainda stub) | não ligar sem F4D |
| `MULTI_WHATSAPP_ENABLED=1` | Canais WA no Control (port Chatbot) | listagem de canais se Chatbot expuser |

```bash
# Exemplo: painel + dashboard, sem RBAC rígido nem Google/WA
fly secrets set --stage \
  REVY_CONTROL_ENABLED=1 \
  REVY_CONTROL_DASHBOARD_ENABLED=1 \
  REVY_CONTROL_RBAC_ENABLED=0 \
  GOOGLE_ADS_SYNC_ENABLED=0 \
  GOOGLE_CONVERSIONS_ENABLED=0 \
  MULTI_WHATSAPP_ENABLED=0 \
  -a app2037
fly secrets deploy -a app2037
```

### 6.2 Endpoints de smoke (base `https://app2037.fly.dev/trafego`)

Autenticado (cookie de sessão admin/gestor após `POST /login`):

| Método | Path | Esperado |
|---|---|---|
| GET | `/health/live` e `/health/ready` | 200 |
| GET | `/control/v1/lojas` | 200 lista no escopo |
| GET | `/control/v1/lojas/{id}/prontidao` | 200 `pronta` + `checks[]` com `aceito` |
| POST | `/control/v1/lojas/{id}/prontidao/alertas/{code}/aceitar` | 200 com `motivo`; 400 se check required |
| GET | `/control/v1/lojas/{id}/integracoes` | 200 pixel/capi/meta_ads **sem** token cru |
| POST | `/control/v1/lojas/{id}/integracoes/pixel/desconectar` | 403 colaborador; 200 admin/responsável |
| GET | `/control/v1/dashboard` | 200 com `counts.ativas|em_configuracao|suspensas|erro` |
| GET | `/app/control/dashboard` | 200 HTML cards + tabela |
| POST | `/control/v1/lojas/{id}/estado` body `{"estado":"ativa"}` | 409 `store_readiness_blocked` se required falhar |

```bash
# Live/ready (sem auth)
curl -sS https://app2037.fly.dev/trafego/health/live
curl -sS https://app2037.fly.dev/trafego/health/ready

# Dashboard (precisa cookie de sessão — usar browser ou curl -c/-b após login)
# Esperado com flag off: HTTP 404
# Esperado com flags on + sessão: HTTP 200 + counts
```

### 6.3 Alembic head Control (lab)

Após deploy do código com F3 aceite de alerta:

- Head esperado: `0013_revy_control_readiness_alert_acceptances`
- Tabela nova: `readiness_alert_acceptances` (`loja_id`, `check_code`, `accepted_by`, `reason`, `accepted_at`)

### 6.4 Residual F7 (ainda não fazer neste checklist)

- [ ] Suíte completa pré/pós migration no lab  
- [ ] Piloto multi-WA (2 números)  
- [ ] Restore drill com tabelas novas  
- [ ] Cutover `REVY_CONTROL_RBAC_ENABLED=1` após vínculos  
- [ ] Remover seletor manual de slug / fallbacks legados  

---

## 6. Não fazer neste rollout

- Ligar Google Ads / Multi-WA / dashboard Control  
- Cortar auth do Portal  
- Import em massa de usuários sem mapear slugs  
- Apagar `GestorRevy` legado  
- Rollout multi-loja sem JSON de tokens por slug  

---

## 7. Evidência para marcar “lab OK”

- [ ] Deploy verde + health Revy ready  
- [ ] Outbox com `delivered` para os 5 destinos da loja piloto  
- [ ] 423/redirect/404 na suspensão  
- [ ] Escrita liberada após reativação  
- [ ] Rollback por flag testado (delivery off)  

Quando os 5 itens passarem, a fatia de **projeção operacional no lab** está fechada.
Próximo produto: Fase 3 Control (integrações) ou Revy Loja — não mais fan-out.
