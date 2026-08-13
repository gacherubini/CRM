# Histórico — Revy Control (`revy-trafego`)

Contexto que saiu de `revy-trafego/README.md`. Explica o *porquê* das armadilhas
listadas lá; não é fonte de verdade do estado atual.

## Atribuição de venda no ROI (2026-08-08) — a venda herda a campanha do lead

`venda_casa_campanha` só comparava `campanha_id_*` e `utm_campaign_*` gravados **na
própria venda**, e nunca consultava o lead. Na mesma função, a contagem de leads já
casava por `ad_id` via cache do Graph — por isso a linha da campanha mostrava leads e
não mostrava vendas. Eram dois caminhos de código, e só um enxergava o anúncio.

`herdar_campanhas_de_leads` (`app/roi_calc.py`) fecha o buraco **na leitura**:

- vale **retroativamente** para toda venda já projetada — sem backfill, sem `UPDATE`
  em `vendas_projetadas` e sem reenviar evento;
- **atribuição explícita vence herança**: se a venda já tem `campanha_id` ou
  `utm_campaign` no snapshot, é isso que manda;
- a ordem do laço (nome em `casefold`) torna a escolha determinística, então uma venda
  **nunca conta em duas campanhas**;
- o índice de leads sai da lista **completa**, não dos leads do período: a venda é de
  agosto e o lead pode ser de julho;
- Chatbot offline → `leads=[]` → herança vazia → comportamento idêntico ao anterior.

O detalhe da campanha (`app/main.py`) usa a mesma herança; sem isso a linha do ROI diria
"1 venda" e a lista da página ficaria vazia.

> `vendas_projetadas.campanha_id` continua `NULL` — é de propósito. O vínculo existe só
> no cálculo. É exatamente essa escolha que faz o conserto valer para o passado.

### Este é o SEU relatório, não a atribuição da Meta

| | Onde decide | O que mudou em 08/08 |
|---|---|---|
| Linha da campanha no ROI / Loja | `roi_calc.herdar_campanhas_de_leads` | **passou a contar a venda** |
| Compra atribuída no Gerenciador de Anúncios | `POST /eventos/venda-confirmada` → Purchase CAPI, que só liga a compra ao anúncio quando o lead tem `ctwa_clid` | **nada** |

Um lead pode ter `meta_ad_id` e **não** ter `ctwa_clid`. Nesse caso a venda passa a contar
na campanha aqui e continua não contando na Meta. A divergência é o comportamento correto,
não é bug — e ela **aumentou** com esta mudança, porque este lado melhorou e o outro não
foi tocado. Fechar o lado da Meta depende de `ctwa_clid` no lead.

### Por que o UUID de campanha do Portal não é aceito

Em `app/vendas_projection.py`, `campanha_id_first/last` vindo do outbox do Portal só é
gravado se existir em `campanhas` da **mesma loja**. O Portal manda o UUID do cadastro
dele e `Campanha.id` aqui é gerado local; aceitar o id de fora desligaria o casamento por
UTM **e** a herança, e a venda sumiria do ROI sem erro visível.

### Ads travados no teto de tentativas (07/08)

`app/meta_ad_resolver_job.py`: salvar a config de Ads (`upsert_meta_ads`) destrava os ads
que estouraram `max_tentativas` — o `WHERE` é por **`loja_slug`**, não por `store.id` como
o `invalidar` que roda ao lado. A tela de Cliques do WhatsApp mostra quantos anúncios
seguem sem campanha resolvida; sem esse número a falha fica invisível, que foi o que
aconteceu com 10 ads em 07/08.

## Triagem de UX (2026-08-07) — o que mudou na interface

Decisões e itens **recusados** em `docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md`.

| Tela | Mudança |
|---|---|
| **Visão geral** (`/app/control/dashboard`) | Encolheu: saíram "Destaques", "Contagens por status", a tabela "Lojas", a coluna "Falhas", o painel Google e "Alterações recentes". Ganhou **filtro de período** (`?inicio=&fim=`), a declaração de que a venda conta por `confirmada_em`, linhas clicáveis para a ficha e chips **Bloqueio** × **Alerta** na prontidão. |
| **Ficha da loja** | Novo painel **Prontidão** (OK / Bloqueio / Alerta) na aba Visão geral — o dashboard linka "o que falta" para cá. Aba "Auditoria" removida (mostrava `action`/`result` crus); a trilha continua no domínio e na API. |
| **Ajustes › Integrações** (`/app/control/integracoes`) | Página nova, espelhando a que a Revy Loja já tem, sobre a loja selecionada. |
| **Menu** | Seção "Loja" virou "Loja selecionada" e perdeu "Todas as lojas". `page_title` e `h1` casam com o rótulo do menu: Medição, ROI, Cliques do WhatsApp, Conferir Pixel. |
| **`/app`** | Deixou de ser a tela "Escolha a loja": encaminha para Visão geral (ou Lojas sem a flag de dashboard). `home.html` sobrou como estado vazio — `exigir_loja` devolve todo mundo para `/app`, então redirecionar dali para uma página que exige loja fecharia um laço. |

Contratos que mudaram:

- `DashboardControl.network_overview(actor, *, leads_port=None, desde=None, ate=None)` —
  datas **inclusivas**; devolve `periodo_inicio`/`periodo_fim`. Janela padrão
  `[1º do mês, hoje]`; o Δ% compara a janela anterior de **mesmo tamanho**.
- `app/rotulos.py` — mapa único de rótulos dos enums (`rotulo_status`, `rotulo_papel`,
  `rotulo_acesso`, `rotulo_check`, `rotular()`).
- `readiness.REQUIRED_CODES` — alias público de `_REQUIRED_CODES`, usado pela UI para
  separar bloqueio de alerta.

## Integração Meta Graph — incidente 2026-08-06 (moto-center)

Antes de `d5b78cc` a versão da Graph estava espalhada (`v21.0`/`v19.0`) e o erro da Meta
era mascarado como `HTTP {status}` genérico. `erro_api_sanitizado`
(`app/meta_ads_spend.py`) passou a fazer parse do `error` da Meta e traduzir o `code`:

| Código Meta | Significado | Ação |
|---|---|---|
| `190` | Token inválido/expirado | Gerar novo token `ads_read` (System User de preferência) |
| `10` / `200` | Sem acesso/permissão à conta de anúncios | Atribuir a conta ao System User + escopo `ads_read` no Business Manager |
| outro | Erro real da Meta | Ler a mensagem/`message` retornada |

O token é sanitizado da mensagem (`[oculto]`); `fbtrace_id` ainda **não** é exposto.

Após subir `d5b78cc` (deploy v101), o sync retornou `1 loja · 1 erro` e
`ultima_sync_erro` revelou: `Meta negou acesso à conta de anúncios (código 200)`. Ou
seja, **não era token expirado (190)** — o token autentica, mas o System User não tinha
acesso `ads_read`/atribuição à conta. A correção é no **Business Manager** (Usuários do
sistema → Adicionar ativos → Conta de anúncios → Ver desempenho) + token com `ads_read`,
não em código.

**Pendência conhecida:** o Portal (`portal-gestao/app/meta_ads_spend.py`,
`app/meta_capi.py`) continua em `v21.0` e ainda mascara o erro como `HTTP {status}`. Em
prod isso está desligado (`PORTAL_META_SPEND_SYNC_ENABLED=0`), então não afeta o sync
ativo; portar o mesmo tratamento é melhoria pendente.

### Ler o erro real de um sync que falhou

```bash
# 1) rodar o sync sob demanda (precisa do secret do job no app)
JOBTOK=$(openssl rand -hex 16); fly secrets set REVY_TRAFEGO_JOB_SECRET=$JOBTOK -a app2037 \
  && curl -s -X POST https://app2037.fly.dev/trafego/internal/jobs/meta-spend-sync \
       -H "X-Job-Token: $JOBTOK" | python3 -m json.tool
# (o payload traz só o agregado: "N loja(s) · X ok · Y erro")

# 2) mensagem detalhada fica em meta_ads_config.ultima_sync_erro
fly ssh console -a app2037 -C "python3 -c \"import sqlite3; c=sqlite3.connect('/data/revy-trafego/revy_trafego.db'); [print(r) for r in c.execute('SELECT loja_id,ultima_sync_status,ultima_sync_em,ultima_sync_erro FROM meta_ads_config')]\""
```

## Cutover de workers (B5 — concluído no lab, 2026-07-28)

1. `REVY_TRAFEGO_CAPI_WORKER=1` + `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED=1`
2. Portal: `PORTAL_CAPI_RETRY_ENABLED=0`, `PORTAL_META_SPEND_SYNC_ENABLED=0`
3. `run-revy-trafego.sh` força `PORTAL_*=1` só no processo tráfego

Rollback de flags do portal: zerar `PORTAL_REVY_TRAFEGO_*`. Rollback da UI do dono:
`PORTAL_TRAFEGO_UI_LEGACY=1`. Rollback de workers: inverter os `PORTAL_*_ENABLED` /
`REVY_TRAFEGO_*_WORKER`.

Flags aplicadas no lab nesse cutover:

| Env | Valor lab | Nota |
|---|---|---|
| `REVY_TRAFEGO_URL` | `http://127.0.0.1:9010` | Portal → API |
| `REVY_TRAFEGO_PUBLIC_URL` | `http://127.0.0.1:9010` | Catálogo Pixel (prioridade) |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | `1` | Cards ROI via API |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | `1` | Notifica venda-confirmada |
| `PORTAL_TRAFEGO_UI_LEGACY` | `0` | Dono sem menus técnicos |
| `REVY_TRAFEGO_LOJAS` | `loja1,moto-center` | Dropdown mesmo sem campanha no DB |

## Entrega no bundle Fly (2026-07-28)

- App copiado em `Dockerfile.app` → `/srv/revy-trafego`
- Supervisor: `program:revy-trafego` → `run-revy-trafego.sh` (uvicorn `:9010`)
- Nginx edge: path `/trafego/` (strip prefix) + `absolute_redirect off` (evita
  `http://host:8080`)
- Prefixo de URL: `REVY_TRAFEGO_URL_PREFIX=/trafego`

Bugs corrigidos nesse cutover: redirect `/trafego` para `http://host:8080/...`;
links Jinja `public_path('/.../{{ id }}')` literal (corrigidos com concatenação `~`);
schema do portal preso no Alembic `0008` com tabelas parciais; conversas de leads
inacessíveis (links quebrados + telefone na path).

Smoke validado: login bootstrap → `/trafego/app`; dropdown `loja1`/`moto-center`;
Config/Campanhas/ROI 200; diagnóstico de leads (proxy chatbot) + abrir conversa;
`GET /v1/lojas/{slug}/resultados` com `X-Service-Token`;
`GET /public/v1/lojas/{slug}/pixel`. Resultado 17/17 PASS.

## Fase 1 / 2 (desenho compartilhado — substituído)

Essas fases usavam o banco do Portal (`/data/portal/portal.db`); a Fase 3 substituiu esse
desenho com banco próprio. Mesma chave Fernet (`PORTAL_ENCRYPTION_KEY` ou
`REVY_TRAFEGO_ENCRYPTION_KEY`). Workers CAPI/spend ficavam desligados por padrão até o
cutover B5.
