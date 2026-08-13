# Revy Control (diretório `revy-trafego`)

Cockpit multi-loja da equipe Revy: Pixel, CAPI, gasto de Ads, campanhas, ROI, prontidão,
auditoria e diagnóstico de leads. Banco e Alembic próprios.

O diretório, o processo e o prefixo público (`/trafego`) mantêm o nome `revy-trafego`; a UI
e o produto se chamam **Revy Control**. A **Revy Loja** (`portal-gestao`) mostra resultados
para o lojista; configuração técnica e operação multi-loja ficam aqui.

## Armadilhas — leia antes de mexer

- **Nunca casar lead ↔ `ctwa_auditoria` por telefone mascarado.** A máscara são os 4
  dígitos finais e a colisão é real: em 08/08 casou o lead de uma venda com o anúncio de
  outro cliente. Atribuição saída daí é receita inventada.
- **Nunca ligar o worker CAPI nos dois processos** sobre a mesma outbox. O Revy é o dono
  único da outbox CAPI e do sync de spend; o Portal roda com `PORTAL_*_ENABLED=0`.
- **`vendas_projetadas.campanha_id` fica `NULL` de propósito.** O vínculo venda↔campanha
  existe só no cálculo (`herdar_campanhas_de_leads`), e é isso que faz a atribuição valer
  retroativamente. Não "conserte" com backfill.
- **A linha de venda da campanha é o relatório da Revy, não a atribuição da Meta.** A
  compra só chega ao Gerenciador de Anúncios pelo Purchase CAPI, que exige `ctwa_clid` no
  lead. Divergência entre os dois números é esperada.
- **Não aceite `campanha_id` vindo do Portal.** `Campanha.id` aqui é local; gravar o UUID
  de fora desliga o casamento por UTM e a herança, e a venda some do ROI sem erro visível.
- **Não hardcode versão da Graph API.** Fonte única: `app/meta_graph_config.py`
  (`GRAPH_BASE`/`GRAPH_VERSION`, override por `META_GRAPH_API_VERSION`).
- **`app.main` e `app.web.control_ui` têm instâncias Jinja separadas.** Global novo precisa
  ser registrado nas duas (`rotulos.registrar_globals(env)`), senão um lado não enxerga.
- Antes de mudar as telas do Control, leia
  [`docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md`](../docs/referencia-viva/2026-08-07-triagem-revisao-ux-loja-control.md):
  parte do que "parece faltando" foi **recusado pelo dono**.
- O `app.css` **não** pode reabrir `:root` para declarar token de marca: ele carrega depois
  do `revy-tokens.css` e a redeclaração anula a fonte única.
  `shared/brand/tests/test_app_css.py` falha se acontecer.

## Onde editar

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | Bootstrap, API `/v1`, `/public/v1`, detalhe de campanha |
| `app/web/control_ui.py` | Telas `/app/control` |
| `app/roi_calc.py` | ROI, `venda_casa_campanha`, `herdar_campanhas_de_leads` |
| `app/vendas_projection.py` | Materializa o outbox do Portal em `vendas_projetadas` |
| `app/meta_ads_spend.py` | Sync de gasto + `erro_api_sanitizado` (traduz o code da Meta) |
| `app/meta_ad_resolver_job.py` | Worker que resolve `ad_id → campaign_id` pelo Graph |
| `app/control/permissions.py` | Isolamento `control:*` × `store:*` |
| `app/rotulos.py` | Mapa único de rótulos dos enums |
| `app/readiness.py` | Prontidão da loja (`REQUIRED_CODES` separa bloqueio de alerta) |
| `app/control/portfolio.py` | Catálogo de módulos contratáveis (inclui `copiloto`) |

## Rodar e testar

```bash
cd revy-trafego
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export REVY_TRAFEGO_DATABASE_URL="sqlite:///./revy_trafego.db"
export REVY_TRAFEGO_ENCRYPTION_KEY='gere-uma-chave-fernet'
export REVY_TRAFEGO_BOOTSTRAP_EMAIL=trafego@revy.local
export REVY_TRAFEGO_BOOTSTRAP_SENHA='troque-isto'
export REVY_TRAFEGO_URL_PREFIX=      # vazio em local puro (sem nginx /trafego)
export CHATBOT_API_URL=http://127.0.0.1:8001
alembic upgrade head && uvicorn app.main:app --reload --port 9010

pytest -q     # não há .venv própria no repo: use a do portal-gestao se preciso
```

Head do Alembic: confira com `alembic heads` / `ls alembic/versions/` — não confie em
número anotado em doc.

Login: com `gestores_revy` vazia o bootstrap cria o primeiro admin e projeta sua `Pessoa` +
`AcessoControl`. A autenticação prefere `AcessoControl` + `Pessoa`; `GestorRevy` é só
fallback de compatibilidade.

## API

| Rota | Nota |
|---|---|
| `GET /health/live` · `/health/ready` | Ready consulta `vendas_projetadas` |
| `GET /v1/lojas/{slug}/resultados?periodo=7d\|mes` | ROI — header `X-Service-Token` |
| `POST /v1/lojas/{slug}/eventos/venda-confirmada` | CAPI, idempotente |
| `POST /v1/lojas/{slug}/eventos/venda-atualizada` | Projeção/cancelamento idempotente |
| `GET /public/v1/lojas/{slug}/pixel` | Público, sem auth |
| `/control/v1/*` · `/app/control/*` | Só com `REVY_CONTROL_ENABLED=1` (senão 404) |
| `POST /internal/jobs/*` | `meta-spend-sync`, `google-conversions-outbox`, `google-ads-metrics-sync` — header `X-Job-Token` |

Pelo edge do Fly, prefixe `/trafego`. No bundle, portal/catálogo chamam
`http://127.0.0.1:9010` **sem** prefixo.

## Flags e env

Defaults de código são **OFF**; em prod `app2037` o piloto liga por secrets.

| Env | Default | Efeito |
|---|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | `sqlite:///./revy_trafego.db` | Banco exclusivo |
| `REVY_TRAFEGO_ENCRYPTION_KEY` | = `PORTAL_ENCRYPTION_KEY` | Fernet dos tokens CAPI/Ads |
| `REVY_TRAFEGO_SESSION_SECRET` / `_SECURE_COOKIE` | dev / `0` | Cookie de sessão (`1` no Fly) |
| `REVY_TRAFEGO_URL_PREFIX` | vazio | `/trafego` no Fly |
| `REVY_TRAFEGO_SERVICE_TOKEN` | vazio | `X-Service-Token` nas APIs `/v1/*` |
| `REVY_TRAFEGO_JOB_SECRET` | vazio | `X-Job-Token` em `/internal/jobs/*` |
| `REVY_TRAFEGO_LOJAS` | vazio | Lista `loja1,moto-center` para o dropdown |
| `REVY_TRAFEGO_BOOTSTRAP_EMAIL` / `_SENHA` / `_NOME` | — | 1º gestor se a tabela estiver vazia |
| `CHATBOT_API_URL` + `REVY_TRAFEGO_CHATBOT_TOKENS_JSON` | — | Diagnóstico de leads; JSON `loja_slug → token` (recomendado em multi-loja) |
| `REVY_TRAFEGO_CAPI_WORKER` | `0` | Retry da outbox CAPI |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | `0` | Job de spend 24h |
| `META_GRAPH_API_VERSION` | `v26.0` | Versão compartilhada da Graph/Marketing API |
| `REVY_CONTROL_ENABLED` | `0` | Liga `/control/v1` e `/app/control` |
| `REVY_CONTROL_RBAC_ENABLED` | `0` | Escopo de lojas por vínculo; só após migration/backfill |
| `REVY_CONTROL_DASHBOARD_ENABLED` | `0` | Dashboard e painéis operacionais |
| `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED` | `0` | Worker da outbox de provisionamento |
| `MULTI_WHATSAPP_ENABLED` | `0` | Proxy de canais WA + prontidão conta canais |
| `GOOGLE_ADS_SYNC_ENABLED` | `0` | OAuth/contas/métricas + worker de métricas |
| `GOOGLE_CONVERSIONS_ENABLED` | `0` | Bindings/outbox, hook venda→conversão, worker |
| `GOOGLE_ADS_OAUTH_*` · `GOOGLE_ADS_DEVELOPER_TOKEN` | vazio | Sem eles a UI não oferece conexão |

Workers Google têm override próprio (`*_WORKER_ENABLED`, `*_INTERVAL_SECONDS`,
`*_INITIAL_DELAY_SECONDS`, `*_MAX_ATTEMPTS`) — ver `app/config.py`.

Do lado do Portal: `REVY_TRAFEGO_URL`, `REVY_TRAFEGO_SERVICE_TOKEN`,
`PORTAL_REVY_TRAFEGO_RESULTADOS`, `PORTAL_REVY_TRAFEGO_VENDA_EVENTS`,
`PORTAL_REVY_TRAFEGO_TIMEOUT` (4s), `PORTAL_TRAFEGO_UI_LEGACY` (rollback da UI do dono).
No Catálogo, `REVY_TRAFEGO_PUBLIC_URL` tem prioridade sobre `PORTAL_PUBLIC_URL`.

## Pessoas, cargos e provisionamento

`/app/control/lojas` lista, cria e administra Lojas. No detalhe, o Admin busca ou cadastra a
pessoa por e-mail, atribui vários cargos e revoga cada um pelo `cargo_id`. A Loja só vira
`pronta` com ao menos um Dono ativo **e** acesso ativável (`AcessoControl` em `pendente` ou
`ativo`); o último Dono ativo fica protegido nos estados operacionais.

O snapshot de provisionamento enfileira para chatbot, estoque, portal, motor e catálogo
(`control_provisioning_outbox`). Tokens por destino: Chatbot/Estoque/Motor por Bearer;
Portal/Catálogo por `X-Service-Token`.

**Copiloto de Vendas** é módulo contratável (`codigo=copiloto`, migration `0018`).
Ligar no Control **não** liga o chat: a Loja ainda exige `REVY_LOJA_COPILOTO_ENABLED`
e o entitlement projetado. Log de perguntas-lacuna (F5) ainda não existe neste produto.

## Google Ads — passo manual de ops obrigatório

A rota HTML é `GET /app/control/google-ads/oauth/callback`. Antes do rollout:

1. registre essa URL como redirect autorizado no Google Cloud Console (no lab, com o
   prefixo do edge: `https://app2037.fly.dev/trafego/app/control/google-ads/oauth/callback`);
2. aponte o secret `GOOGLE_ADS_OAUTH_REDIRECT_URI` para a **mesma** URL.

Divergência entre os dois dá `redirect_uri_mismatch` no Google **sem pista no log**. O
endpoint JSON legado `/control/v1/google-ads/oauth/callback` existe só por compatibilidade;
quem apontar para ele volta do Google em JSON cru.

## Deploy

```bash
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

Artefatos em `deploy/fly/3vm/`: `Dockerfile.app`, `supervisord.conf`,
`run-revy-trafego.sh`, `nginx-edge.conf`, `fly.app.toml`, `env.example`.

O entrypoint roda os Alembics de Portal e Revy em modo fail-fast antes do supervisord.
Bancos no volume: `/data/portal/portal.db` e `/data/revy-trafego/revy_trafego.db`.

---

Histórico (atribuição no ROI, incidente Meta 08/06, cutover de workers, smokes):
[`docs/nao-plano/historico/revy-control.md`](../docs/nao-plano/historico/revy-control.md).
