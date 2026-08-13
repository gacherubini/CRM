# Painel de status das integrações (Meta · Google · WhatsApp)

- Data: 2026-08-01
- Produtos: Revy Control (`revy-trafego`), Portal (`portal-gestao`), Chatbot (`chatbot-api`)
- Status: design aprovado (brainstorming); execução autônoma autorizada pelo owner

## Objetivo

Mostrar, por loja, se as integrações externas estão **de fato conectadas e funcionando** — com checagem real ao vivo — em badges bonitos: 🟢 conectado / 🔴 com erro / ⚪ não configurado. Aparece tanto no Control (admin/gestor) quanto no shell da Revy Loja (lojista).

## Decisões do brainstorming (fixadas)

- **Profundidade:** checagem **real ao vivo** — bate no serviço, não só "config presente".
- **Onde:** nos dois — Control (detalhe da loja) e shell da Revy Loja (Portal).
- **Granularidade:** **3 badges** — Meta · Google · WhatsApp — com **expandir** para sub-itens reais (Meta → Pixel/CAPI/Meta Ads; Google → Google Ads; WhatsApp → instância(s)).
- **Estados (3):** `connected` (🟢), `error` (🔴, config presente mas a chamada falhou), `missing` (⚪, nunca configurado). Um grupo é 🟢 só se todos os sub-itens configurados estão ok; 🔴 se algum quebrou; ⚪ se nenhum configurado.
- **Cache:** TTL **10 min** (configurável por env), com **invalidação em eventos** (connect/disconnect/reconnect zeram o cache daquela integração na hora). Botão **"Testar agora"** fura o cache.

## Contexto do código (reuso)

- **Meta (Control):** `revy-trafego/app/control/integrations.py` — `IntegrationsControl`, `IntegrationKind {PIXEL,CAPI,META_ADS}`, `IntegrationStatus {CONNECTED,MISSING,ERROR}`, `IntegrationView(kind,status,...,health_message)`, `_pixel_view/_capi_view/_ads_view` (hoje derivam status de **config presente + último sync**, não live). Configs em `MetaPixelConfig`/`MetaAdsConfig` (token cifrado via `app.cripto.cifrar`). `upsert_*`/`disconnect_*` são os pontos de invalidação de cache.
- **Google (Control):** `revy-trafego/app/models.py::GoogleAdsConnection` (`refresh_token_ciphertext`); `revy-trafego/app/control/google_ads_http.py` — troca OAuth em `GOOGLE_OAUTH_TOKEN_URL` (`https://oauth2.googleapis.com/token`), com caminho de mock (`fake-refresh-token`) para testes. Uma checagem live = trocar o refresh token por access token; sucesso = conectado.
- **WhatsApp (Chatbot/Portal):** `chatbot-api/app/whatsapp_provider.py::status(canal) -> StatusResult` usa `GET /instance/connectionState/{inst}` e `_traduzir_connection_state` (open/connecting/close → canônico). Endpoint `chatbot-api/app/main.py::status_canal_whatsapp` (~1081). O Portal já consome via `portal-gestao/app/clients/chatbot.py::listar_canais_whatsapp()` / `obter_status_canal_whatsapp(canal_id)`.
- **Clients cross-app existentes:** `revy-trafego/app/clients/portal.py` (Control→Portal) e `portal-gestao/app/clients/revy_trafego.py` (Portal→Control) — reusáveis para a agregação cruzada.

## Arquitetura

Cada produto **checa ao vivo o que ele dona** e expõe um contrato de health; o painel de cada app agrega o local + uma chamada HTTP ao outro.

| Integração | Dono | Checagem live |
|---|---|---|
| Meta (Pixel/CAPI/Meta Ads) | Control | Graph API: valida token (debug_token) e acesso ao Pixel/ad account |
| Google (Ads) | Control | OAuth: troca refresh token → access token |
| WhatsApp (instância) | Chatbot (via Portal) | `connectionState` == `open` |

- **Contrato de health (JSON) por loja:**
  ```json
  {
    "meta":    {"status":"connected|error|missing", "itens":[{"kind":"pixel","status":...,"message":...}, ...]},
    "google":  {"status":..., "itens":[{"kind":"google_ads", ...}]},
    "whatsapp":{"status":..., "itens":[{"kind":"whatsapp","label":"loja1","message":...}]},
    "checked_at":"<iso>", "cache_ttl_seg":600
  }
  ```
- **Cache:** in-memory por processo (o `app2037` roda 1 máquina), chave `(loja_id, grupo)`, valor `(resultado, checado_em)`. TTL configurável (`INTEGRACOES_HEALTH_TTL_SEGUNDOS`, default 600). Invalidação explícita ao conectar/desconectar. `?forcar=1` (ou POST "testar") ignora o cache. Relógio injetável para testes (não usar `datetime.now()` direto — usar o `agora()` do produto, mockável).
- **Timeouts:** cada chamada externa com timeout curto (ex.: 5s); checagens do grupo em paralelo; falha/timeout de uma chamada → aquele sub-item vira `error` com mensagem, sem derrubar o resto.
- **Segurança:** nunca retornar/logar tokens; só status + mensagem amigável. Endpoints exigem a mesma auth já usada (sessão de gestor no Control; sessão de loja no Portal; service token entre serviços).

## Fases (cada uma: spec-part → plano → execução; entrega algo testável)

- **Fase 1 — Health backend no Control (Meta + Google).** Camada de checagem live + cache + endpoint agregado `GET /control/v1/lojas/{id}/integracoes/health` retornando `meta` e `google` (WhatsApp entra na Fase 2). Sem UI. Totalmente contido no `revy-trafego`, testável com mocks das APIs. **← executar primeiro.**
- **Fase 2 — WhatsApp no contrato.** Expor status de WhatsApp por loja (chatbot/Portal) de forma consumível e ligá-lo ao agregador do Control como 3º badge (Control→Portal via client).
- **Fase 3 — Badge UI no Control** (detalhe da loja): consome o agregador; 3 badges com expandir, estados coloridos, "Testar agora". Precisa de review visual do owner.
- **Fase 4 — Badge UI no shell da Revy Loja (Portal):** consome o agregador do Control por HTTP + WhatsApp local. Review visual do owner.

## Fase 1 — detalhe (o que será construído agora)

Arquivos (todos em `revy-trafego`):
- `app/control/integrations_health.py` (novo): domínio de checagem live.
  - `class HealthStatus(str, Enum)` = `CONNECTED|ERROR|MISSING` (reusa a semântica de `IntegrationStatus`).
  - `@dataclass ItemHealth(kind, status, message)` e `@dataclass GroupHealth(status, itens)`.
  - `check_meta(db, store, *, forcar=False) -> GroupHealth` — para Pixel/CAPI/Meta Ads: se config ausente → `missing`; se presente → chama a Graph API (via um client injetável) para validar token/acesso; ok → `connected`, falha → `error(mensagem)`.
  - `check_google(db, store, *, forcar=False) -> GroupHealth` — sem `GoogleAdsConnection`/refresh → `missing`; com → troca refresh→access (reusa `google_ads_http`), ok → `connected`, falha → `error`.
  - `health_da_loja(db, store, *, forcar=False) -> dict` — monta o contrato, aplicando cache.
  - Cache in-memory com TTL de `settings` e `invalidar(loja_id, grupo)`.
- `app/control/graph_probe.py` (novo, pequeno): client HTTP que valida token Meta na Graph API (`GET /debug_token` ou acesso ao Pixel), com caminho de mock para testes (espelha o padrão de `google_ads_http.py`).
- `app/web/control_ui.py` (ou router de control): endpoint `GET /control/v1/lojas/{id}/integracoes/health` (JSON) + `?forcar=1`.
- Hooks de invalidação: em `IntegrationsControl.upsert_*/disconnect_*` e no upsert/disconnect do Google, chamar `integrations_health.invalidar(loja_id, grupo)`.
- Config: `INTEGRACOES_HEALTH_TTL_SEGUNDOS` (default 600), `INTEGRACOES_HEALTH_TIMEOUT_SEG` (default 5) em `app/config.py`.

Testes (Fase 1):
- `check_meta`: missing (sem config); connected (Graph mock 200); error (Graph mock 401/timeout). Idem CAPI/Ads.
- `check_google`: missing; connected (refresh mock ok); error (refresh mock falha).
- Agregação de grupo: 🟢 só se todos configurados ok; 🔴 se um falha; ⚪ se nenhum configurado.
- Cache: 2ª chamada dentro do TTL não re-checa (client externo chamado 1x); `forcar=True` re-checa; `invalidar()` força recheck; TTL expira → recheca (relógio mockado).
- Endpoint: 200 com o JSON; auth exigida; `?forcar=1` fura cache.

## Fora de escopo (v1)

- Alertas/notificação proativa quando cai (só exibição sob demanda).
- Histórico de uptime.
- Checagem de bancos (Motor) — só Meta/Google/WhatsApp.
- Nada de tokens no response/log.

## Verificação

- `revy-trafego`: `.venv/bin/python -m pytest -q` verde (fora `test_control_provisioning_outbox.py::...` pré-existente).
- Cross-app (fases 2+): contratos HTTP testados nos dois lados.
- Deploy + verificação ao vivo: **somente com o owner presente** (precisa subir o lab e ter credenciais reais); não deployar autônomo.
