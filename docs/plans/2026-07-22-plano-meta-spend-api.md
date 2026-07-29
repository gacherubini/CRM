# Plano — Sincronizar gasto de mídia via Meta Marketing API (sem lançamento manual)

> **FRONTEIRA FUTURA:** este é o desenho do MVP já entregue no Portal. OAuth/token,
> sincronização e diagnóstico Meta passam a ser administrados pelo
> [Revy Control](2026-07-29-plano-revy-control.md); dono e gerente não configuram isso no Revy Loja.

> **Status 2026-07-22: MVP CÓDIGO (S1–S4)** — botão 7d + job background 24h + endpoint interno + UI + testes.  
> Residual: listar campanhas Meta para vincular (S6), App Review multi-tenant, OAuth.  
> Pedido: o dono **não** deve precisar digitar quanto gastou na campanha; o Revy puxa da Meta.  
> **Só Meta** neste plano (Google Ads spend **fora** — alinhado ao uso atual).

**Status:** **MVP + job diário no Portal** — eixo **C · CRM dono**  
**Detalha / estende:** campanhas + `CampanhaGasto` + ROI (6.1); config Tráfego (E10); CTWA keys `meta_campaign_id` (6.2b)  
**Não implementa:** criar/pausar anúncios; Google spend; TikTok spend; reconciliação contábil fiscal  
**Depende de:** Portal campanhas/ROI; cifra de segredos (`cripto`); preferível **6.2b Fase C** (`meta_campaign_id` na campanha) — se CTWA atrasar, este plano **inclui** o campo `meta_campaign_id` na Task S1

**Goal:** O dono conecta a conta de anúncios Meta uma vez; o Revy importa **spend diário por campanha**, grava em `CampanhaGasto` com origem API, e o ROI (CPL/CPA/ROAS) atualiza **sem** formulário de gasto (manual continua só como fallback).

**Architecture:** Portal é o único dono do token Marketing API e do job de sync. Insights API (`/{object_id}/insights` ou `act_{ad_account}/insights` level=campaign) devolve `spend` por dia. Match Revy ↔ Meta por `campanha.meta_campaign_id` (obrigatório para auto). Upsert idempotente de `CampanhaGasto` por `(campanha_id, referencia, origem=meta_api)`. Cron interno ou botão “Sincronizar agora” + opcional agendamento diário. **Token CAPI (events) ≠ token ads_read** — config separada na aba Tráfego.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, httpx, pytest; Meta Graph Marketing API (Insights); cifra existente no Portal.

---

## Por que isso importa (produto)

| Hoje | Com este plano |
|---|---|
| Dono copia gasto do Ads Manager → cola no Revy | Revy **puxa** spend |
| ROI “—” se esquecer de lançar | ROI acompanha a Meta (atraso de sync) |
| CSV/lote ajudam, mas ainda são manuais | Manual vira **exceção** (ajuste, offline, não-Meta) |

Combina com a narrativa: **CTWA/catálogo vendem; placar fecha sozinho no gasto**.

---

## Fora de escopo

| Item | Motivo |
|---|---|
| Google / TikTok spend | Usuário só Meta agora |
| Criar campanha no Ads a partir do Revy | Continua Ads Manager |
| Importar impressões/CTR para dashboard completo de mídia | MVP = **só `spend`** (e opcionalmente `impressions`/`clicks` em nota ou tabela futura) |
| Multi-moeda complexa | MVP: BRL; se conta em outra moeda, documentar e converter depois |
| App Review completo multi-tenant global no dia 1 | Ver §Modelo de app Meta |
| Apagar gastos manuais antigos automaticamente | Sync **não** sobrescreve `origem=manual` no mesmo dia sem regra explícita |

---

## Decisões de produto

| Tema | Decisão |
|---|---|
| O que importar | **`spend`** diário por **campanha** Meta (`level=campaign`, `time_increment=1`) |
| Janela default | Últimos **7 dias** no botão; job diário = **D-1** (dia anterior fechado) + retry D-2 |
| Match | `Campanha.meta_campaign_id` = id da campanha no Ads (`1203…`). Sem id → **não importa** essa linha (alerta UI) |
| Modelo de gasto | Continua `CampanhaGasto`; campos novos: `origem` (`manual` \| `meta_api`), `external_key` (unique lógica) |
| Conflito manual vs API | Mesmo `(campanha_id, referencia)`: se já existe **manual**, **não** sobrescrever no MVP (ou flag “preferir API”); se `meta_api`, **atualiza valor** |
| Manual | Lote/CSV/detalhe **permanecem** para campanhas sem Meta ou correção |
| Quem conecta | Dono/gerente; token **cifrado** por loja |
| Frequência | Botão sob demanda + job diário (APScheduler/cron no processo Portal **ou** endpoint interno chamado pelo n8n/cron Fly) |
| RBAC | Igual tráfego |
| Falha | Nunca quebra venda; status “última sync” na Tráfego |

### Modelo de app Meta (SaaS multi-loja)

Cada **loja** tem (ou compartilha) um **Ad Account**.

MVP operacional (mais rápido para lab/clientes iniciais):

1. Dono cola **Ad Account ID** (`act_XXXX`)  
2. Dono cola **token** com permissão `ads_read` (System User no BM **ou** long-lived user token)  
3. Revy só **lê** insights  

Evolução (melhor UX):

- OAuth “Login com Facebook” + `ads_read` + escolher ad account  

**MVP = colar token + account id** (espelha como CAPI é configurado hoje). Documentar geração de System User no guia.

> **Atenção:** app Meta em modo dev só funciona para roles do app; produção multi-cliente pode exigir **App Review** (`ads_read`). Planejar isso como ops do produto Revy, não como feature de loja.

---

## API Meta (referência de implementação)

Endpoint típico:

```http
GET https://graph.facebook.com/v21.0/act_{AD_ACCOUNT_ID}/insights
  ?level=campaign
  &fields=campaign_id,campaign_name,spend,date_start,date_stop
  &time_increment=1
  &time_range={"since":"2026-07-01","until":"2026-07-21"}
  &limit=500
  &access_token=...
```

Ou por campanha:

```http
GET /{CAMPAIGN_ID}/insights?fields=spend&time_increment=1&time_range=...
```

- Paginação `paging.next`  
- `spend` vem string decimal em moeda da conta  
- Rate limit Ads — backoff + cache de última sync  
- Erros: token inválido, falta de permissão, account id errado → UI amigável

**Não** reutilizar o token CAPI do Events Manager (escopos diferentes). Config **separada**:

| Config | Uso |
|---|---|
| Pixel ID + token CAPI | Conversões (já existe) |
| Ad Account ID + token Marketing (`ads_read`) | **Spend** (este plano) |

---

## Modelo de dados

### `meta_ads_config` (nova tabela ou colunas em config por loja)

```text
loja_slug              PK/unique
ad_account_id          str   # act_123 sem ou com prefixo — normalizar
access_token_cipher    str   # cifrado
sync_enabled           bool
ultima_sync_em         datetime null
ultima_sync_status     str   # ok | erro | partial
ultima_sync_erro       str(500) null  # sanitizado
janela_dias_default    int default 7
```

### `campanhas`

```text
meta_campaign_id   str(64) null index  # se 6.2b ainda não criou, criar aqui
```

### `campanha_gastos` — colunas novas

```text
origem         str(20) default 'manual'   # manual | meta_api
external_key   str(120) null              # ex.: meta:{campaign_id}:{YYYY-MM-DD}
```

Unique parcial lógico: `(loja_slug, external_key)` where external_key not null.

```text
nota exemplos:
  "Meta API sync 2026-07-22"
  criada_por: "meta_api" ou email do job
```

---

## Fluxo

```text
[Cron diário / botão Sincronizar]
      │
      ▼
Ler meta_ads_config da loja (token decifrado em memória)
      │
      ▼
GET act_XX/insights level=campaign time_increment=1
      │
      ▼
Para cada linha (campaign_id, date, spend):
  achar Campanha where loja + meta_campaign_id == campaign_id
  se não achar → contar "órfão" (não cria campanha automática no MVP)
  se achar → upsert CampanhaGasto(origem=meta_api, referencia=date, valor=spend)
      │
      ▼
Atualizar ultima_sync_* 
ROI usa gastos como hoje (soma no período)
```

**Não** criar campanha Revy automática a partir da Meta no MVP (evita lixo e mismatch de utm).  
Dono cadastra campanha **uma vez** e cola o **ID da campanha Meta** (copy do Ads Manager).

Opcional fase 2: listar campanhas da conta (`GET act_XX/campaigns`) e UI “vincular”.

---

## Mapa de arquivos

| Arquivo | Papel |
|---|---|
| `portal-gestao/app/meta_ads_spend.py` | Cliente Insights + normalização + upsert |
| `portal-gestao/app/models.py` | Config + colunas gasto/campanha |
| `portal-gestao/alembic/versions/00xx_meta_spend.py` | Migration |
| `portal-gestao/app/main.py` | UI Tráfego: form token/account; POST sync; status |
| `portal-gestao/app/templates/trafego/form.html` | Bloco “Gasto automático Meta” |
| `portal-gestao/app/templates/campanhas/form.html` | Campo ID campanha Meta (se ainda não em 6.2b) |
| `portal-gestao/app/campanhas.py` / `roi_calc.py` | Sem mudança de fórmula; só origem dos gastos |
| `portal-gestao/tests/test_meta_ads_spend.py` | Mock httpx, upsert, skip sem match |
| `docs/trafego-pago-loja.md` | Como gerar System User + copiar campaign id |
| `docs/plans/2026-07-22-plano-ctwa-...` | Cross-link: spend desbloqueia ROI CTWA sem digitação |

---

## Fases

| Fase | Nome | LOE | Entrega |
|---|---|---|---|
| **S0** | Spike API | XS–S | Script/lab: 1 call real insights com token de teste |
| **S1** | Modelo + match id | S | `meta_campaign_id`, `origem`, `external_key` |
| **S2** | Cliente + upsert | M | Import por período, testes mock |
| **S3** | UI config + botão sync | S | Tráfego + feedback órfãos |
| **S4** | Job diário | S | Cron/endpoint agendável |
| **S5** | Docs + checklist dono | XS | Guia System User / campaign id |
| **S6** | (Opcional) listar campanhas Meta para vincular | M | Menos erro de colar id |

**Ordem:** `S0 → S1 → S2 → S3 → S5 → S4` (job depois do botão manual estável). S6 se friction de id for alta.

---

## Fase S0 — Spike

- [ ] Com token `ads_read` + `act_`, chamar insights 7d level=campaign  
- [ ] Confirmar campos `campaign_id`, `spend`, `date_start`  
- [ ] Anotar rate limits / permissões no plano  
- [ ] Go/no-go: se o app Revy não tiver como obter token em produção, documentar App Review  

---

## Fase S1 — Modelo

- [ ] Migration `meta_ads_config` (ou equivalente por loja)  
- [ ] `Campanha.meta_campaign_id`  
- [ ] `CampanhaGasto.origem`, `external_key`  
- [ ] Backfill `origem=manual` nos existentes  
- [ ] Testes model/migration  

---

## Fase S2 — Sync core

### Aceite

- Dado fixture JSON Insights com 2 campanhas / 3 dias:  
  - 1 campanha matched → 3 rows `meta_api`  
  - 1 órfã → 0 rows, contador orphans=1  
- Re-rodar sync → **não** duplica (upsert por `external_key`)  
- Spend “12.50” → `Decimal("12.50")`  
- Token inválido → status erro, zero partial corrupt  

### Funções alvo

```python
def sincronizar_gastos_meta(
    db: Session,
    loja_slug: str,
    *,
    since: date,
    until: date,
) -> SyncResult:  # imported, updated, orphans, errors
    ...
```

---

## Fase S3 — UI

- Bloco na **Tráfego**: Ad Account, token (password), toggle sync, “Última sync”, botão **Sincronizar gastos agora**  
- Após sync: “Importados X · Atualizados Y · Sem campanha no Revy: Z” + link para vincular ids  
- Form campanha: “ID da campanha no Meta Ads” com ajuda (“Gerenciador → Campanha → copiar ID”)  
- Gastos no detalhe: badge **Meta** vs **Manual**  

---

## Fase S4 — Job diário

Opções (escolher na implementação a que encaixar no Fly 3-VM):

| Opção | Prós |
|---|---|
| `POST /internal/jobs/meta-spend-sync` + secret + cron externo | Simples no monólito Portal |
| Thread/APScheduler no startup Portal | Sem dependência externa |
| n8n cron → HTTP | Já há n8n no lab |

MVP: endpoint autenticado por segredo de job **ou** só botão até provar valor; job na mesma PR se barato.

Default janela job: ontem (e anteontem se ontem falhou).

---

## Fase S5 — Docs

Atualizar `docs/trafego-pago-loja.md`:

1. Conectar conta de anúncios (System User + `ads_read`)  
2. Colar ID da campanha Meta em cada campanha Revy  
3. Sincronizar (ou esperar job)  
4. ROI sem digitar gasto  
5. Quando ainda usar manual (OLX, indicação, campanha sem Meta)  

Linguagem dono: **“o Revy busca o gasto no Meta”**, não “API Insights”.

---

## Relação com CTWA e Pixel

```text
Pixel + catálogo     → persona / remarketing
CTWA + ctwa_clid     → conversa e conversão messaging
meta_campaign_id     → amarra lead/venda E spend
Marketing API spend  → dono não digita custo
ROI                  → gasto API + vendas Revy
```

Sem `meta_campaign_id`, o spend **não sabe** em qual linha do Revy cair.  
Por isso este plano e o **6.2b (CTWA)** compartilham o mesmo campo de vínculo Meta.

Ordem sugerida de implementação conjunta:

1. **S1** `meta_campaign_id` (serve CTWA match + spend)  
2. CTWA A/C (lead + match)  
3. **S2–S3** spend auto  
4. CTWA B (CAPI messaging)  

---

## Riscos

| Risco | Mitigação |
|---|---|
| Token expira (60d user token) | Preferir System User; UI “token inválido, reconecte”; alerta no dashboard |
| App Review `ads_read` | Lab com dev roles; produção: processar review ou onboarding assistido |
| Dono cola campaign id errado | UI listar órfãos; fase S6 vincular |
| Spend atrasa na Meta (fuso) | Sync D-1; re-sync 7d no botão |
| Duplicar com lançamento manual | `origem` + regra não sobrescrever manual |
| Custo de API / rate limit | 1 sync/loja/dia default; botão com cooldown |
| Conta em USD | MVP documentar; converter depois se precisar |

---

## Critérios DONE

- [ ] Loja com config válida sincroniza spend → `CampanhaGasto` `meta_api`  
- [ ] ROI reflete gasto sem form manual  
- [ ] Re-sync idempotente  
- [ ] Campanha sem `meta_campaign_id` não quebra sync (órfão contado)  
- [ ] Manual ainda funciona para não-Meta  
- [ ] Segredo cifrado; nunca no log  
- [ ] Doc do dono atualizado  

---

## Estimativa

| Fase | Tempo |
|---|---|
| S0 | 0,5 dia |
| S1 | 0,5–1 dia |
| S2 | 1,5–2 dias |
| S3 | 1 dia |
| S4 | 0,5–1 dia |
| S5 | 0,5 dia |
| **Total MVP** | **~4–6 dias** dev (+ App Review/ops se multi-cliente) |

---

## O que muda na conversa com o dono

**Antes:** “Cadastre a campanha e **lance o gasto** toda semana.”  

**Depois:** “Cadastre a campanha **uma vez** com o ID do Meta, conecte a conta de anúncios, e o **gasto entra sozinho**. Você só lança manual o que não for Meta.”

---

## Próximo passo

1. Confirmar: MVP = **colar token + act_id** (sem OAuth full) — recomendado.  
2. Rodar **S0** com uma conta Ads real de lab.  
3. Implementar S1–S3 antes ou em paralelo ao CTWA A (campo `meta_campaign_id` unificado).  
