# Painel de status das integrações — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Checagem real ao vivo do estado das integrações por loja (Meta, Google, WhatsApp), exibida em badges 🟢/🔴/⚪ no Control e no Portal.

**Architecture:** Cada produto checa ao vivo o que dona e expõe um contrato de health; cache curto com invalidação em eventos. Feito em 4 fases; **este plano detalha a Fase 1** (backend de health no Control para Meta+Google) e esboça 2–4.

**Tech Stack:** FastAPI, SQLAlchemy, httpx, pytest — tudo em `revy-trafego` na Fase 1.

## Decisões do owner (2026-08-01) — vinculantes

1. **WhatsApp (multi-número):** o badge fica 🟢 **só se TODOS os números conectados**; se qualquer um caiu → 🔴 (detalhe de qual ao expandir). **Sem nenhum número cadastrado → ⚪ missing** (não vermelho).
2. **Atualização na tela:** carrega no open (do cache) + botão **"Testar agora"** (fura o cache). **Sem auto-poll** em background.
3. **Autonomia de execução:** implementar as 4 fases, testes verdes, review por task, e **mergear na `main`** conforme cada fase fica pronta. **NÃO deployar** nem subir o Fly (fica pro owner).
4. **UX/acesso:** badge é **só status (não clicável)**; visível **apenas a dono/gerente** (não vendedor). Sem link pra tela de config nesta versão.

## Global Constraints

- Rodar testes de `revy-trafego/` com `.venv/bin/python -m pytest -q`.
- **Nunca** retornar/logar tokens; só `status` + `message` amigável.
- Estados: `connected` / `error` (config presente, chamada falhou) / `missing` (não configurado). Grupo 🟢 só se todos os configurados ok; 🔴 se algum falha; ⚪ se nenhum configurado.
- Checagens externas com **timeout curto** (default 5s) e **mockáveis** (espelhar o padrão de porta injetável de `google_ads_http.py`, que tem caminho `fake-*`). Testes NUNCA batem em rede real.
- Cache TTL default **600s** (`INTEGRACOES_HEALTH_TTL_SEGUNDOS`); relógio injetável (não usar `datetime.now()` direto — receber um `now`/clock).
- Auth do endpoint = `gestor_atual(request, db)` (sessão de gestor), como os demais endpoints do Control.
- Falha pré-existente não relacionada: `tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`.

---

### Task 1: Cache TTL com relógio injetável + config

**Files:**
- Create: `revy-trafego/app/control/health_cache.py`
- Modify: `revy-trafego/app/config.py` (env `INTEGRACOES_HEALTH_TTL_SEGUNDOS`, `INTEGRACOES_HEALTH_TIMEOUT_SEG`)
- Test: `revy-trafego/tests/test_health_cache.py`

**Interfaces:**
- Produces: `class TTLCache` com `get(key) -> Any | None`, `set(key, value)`, `invalidate(key)`, `clear()`; construída com `ttl_seg: int` e `clock: Callable[[], float]` (default `time.monotonic`). Entradas expiram após `ttl_seg`.

- [ ] **Step 1: Failing test**
```python
# revy-trafego/tests/test_health_cache.py
from app.control.health_cache import TTLCache


def test_cache_hit_dentro_do_ttl_e_expira_depois():
    t = {"v": 1000.0}
    c = TTLCache(ttl_seg=600, clock=lambda: t["v"])
    c.set("k", "resultado")
    assert c.get("k") == "resultado"           # hit
    t["v"] = 1000.0 + 599
    assert c.get("k") == "resultado"           # ainda dentro do TTL
    t["v"] = 1000.0 + 601
    assert c.get("k") is None                    # expirou


def test_invalidate_e_clear():
    t = {"v": 0.0}
    c = TTLCache(ttl_seg=600, clock=lambda: t["v"])
    c.set("a", 1); c.set("b", 2)
    c.invalidate("a")
    assert c.get("a") is None and c.get("b") == 2
    c.clear()
    assert c.get("b") is None
```

- [ ] **Step 2: Run → fail** (`.venv/bin/python -m pytest -q tests/test_health_cache.py`) — ModuleNotFound.

- [ ] **Step 3: Implement**
```python
# revy-trafego/app/control/health_cache.py
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class TTLCache:
    def __init__(self, ttl_seg: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seg
        self._clock = clock
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        stamped, value = item
        if self._clock() - stamped > self._ttl:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        self._data[key] = (self._clock(), value)

    def invalidate(self, key: Any) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
```

- [ ] **Step 4: Add config** — em `revy-trafego/app/config.py`, junto dos demais `os.getenv`:
```python
    integracoes_health_ttl_seg: int = int(
        os.getenv("INTEGRACOES_HEALTH_TTL_SEGUNDOS", "600")
    )
    integracoes_health_timeout_seg: float = float(
        os.getenv("INTEGRACOES_HEALTH_TIMEOUT_SEG", "5")
    )
```
(Confirme o estilo da classe `Settings` do arquivo e siga-o; se for `@dataclass`/pydantic, adapte a sintaxe mantendo os mesmos nomes/defaults.)

- [ ] **Step 5: Run → pass**; **Step 6: Commit** `feat(control): TTLCache com relogio injetavel + config de health`.

---

### Task 2: Probe da Graph API (Meta) + check_meta

**Files:**
- Create: `revy-trafego/app/control/graph_probe.py`
- Create: `revy-trafego/app/control/integrations_health.py` (só `check_meta` + tipos nesta task; agregador vem na Task 4)
- Test: `revy-trafego/tests/test_integrations_health_meta.py`

**Interfaces:**
- Produces:
  - `class HealthStatus(str, Enum)` = `CONNECTED="connected"|ERROR="error"|MISSING="missing"`.
  - `@dataclass(frozen=True) ItemHealth(kind: str, status: HealthStatus, message: str | None)`.
  - `@dataclass(frozen=True) GroupHealth(status: HealthStatus, itens: tuple[ItemHealth, ...])`.
  - `class GraphProbe(Protocol): def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]: ...` (True=ok; str=motivo do erro). `HttpGraphProbe` (real, httpx, timeout) e `FakeGraphProbe` (testes).
  - `check_meta(db, store, probe: GraphProbe) -> GroupHealth` — usa `_pixel_config`/`_ads_config` de `integrations.py`, `pixel_configured`, e `app.cripto.decifrar` no `token_ciphertext`.

**Regras de `check_meta`:**
- Pixel: sem `pixel_id` e sem token → `ItemHealth("pixel", MISSING)`. Com config → `probe.validar_token(decifrar(token_ciphertext), pixel_id)`; ok → CONNECTED, senão ERROR(motivo).
- CAPI: compartilha o token do Pixel (Conversions API). Configurado = pixel_id + token presentes; mesmo resultado do probe → CONNECTED/ERROR; sem token → MISSING.
- Meta Ads: sem `ad_account_id`/token → MISSING; com → CONNECTED se `probe` do token ok (validar_token com pixel_id vazio aceitável), senão ERROR. (Se quiser precisão de ad account, deixar TODO explícito para Fase futura — nesta task, validar o token basta.)
- `GroupHealth.status`: CONNECTED se todos os itens não-MISSING são CONNECTED e há ≥1 não-MISSING; ERROR se algum item é ERROR; MISSING se todos MISSING.

- [ ] **Step 1: Failing test**
```python
# revy-trafego/tests/test_integrations_health_meta.py
from app.control.health_status import HealthStatus  # se optar por módulo separado; senão importe de integrations_health
from app.control.integrations_health import (
    GroupHealth, ItemHealth, check_meta,
)
from app.control.integrations import IntegrationsControl, UpsertPixel
from app.control.types import Actor, StoreRef
# ... use as fixtures/factories já existentes nos testes do Control para criar Loja + gestor admin.


class FakeGraphProbe:
    def __init__(self, ok=True, motivo=None):
        self.ok, self.motivo, self.chamadas = ok, motivo, 0
    def validar_token(self, token, pixel_id):
        self.chamadas += 1
        return (self.ok, None if self.ok else (self.motivo or "token inválido"))


def test_check_meta_missing_sem_config(db, loja):
    grupo = check_meta(db, loja, FakeGraphProbe())
    assert grupo.status is HealthStatus.MISSING


def test_check_meta_connected_com_pixel_e_token_valido(db, loja, actor_admin):
    IntegrationsControl(lambda: db).connect_pixel(  # use o método real de upsert do Pixel
        actor_admin, UpsertPixel(store=StoreRef(id=loja.id), pixel_id="123456789012345", token="tok-abc"))
    probe = FakeGraphProbe(ok=True)
    grupo = check_meta(db, loja, probe)
    assert grupo.status is HealthStatus.CONNECTED
    assert probe.chamadas >= 1  # bateu no probe (checagem real)


def test_check_meta_error_quando_token_invalido(db, loja, actor_admin):
    IntegrationsControl(lambda: db).connect_pixel(
        actor_admin, UpsertPixel(store=StoreRef(id=loja.id), pixel_id="123456789012345", token="tok-abc"))
    grupo = check_meta(db, loja, FakeGraphProbe(ok=False, motivo="OAuthException"))
    assert grupo.status is HealthStatus.ERROR
    assert any(i.status is HealthStatus.ERROR and i.message for i in grupo.itens)
```
> Nota ao implementador: confirme os nomes reais dos métodos de upsert em `IntegrationsControl` (ex.: `connect_pixel`/`upsert_pixel`) lendo `integrations.py` e ajuste o teste; use os helpers de criação de loja/gestor já existentes em `tests/` (ver `test_control_convite_ui.py`/conftest).

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `graph_probe.py` (`HttpGraphProbe` usando httpx `GET https://graph.facebook.com/v19.0/debug_token` ou `GET /{pixel_id}` com o token; timeout de `settings.integracoes_health_timeout_seg`; retorna `(False, motivo)` em status != 2xx ou exceção — nunca vaza o token) e `integrations_health.py` com os tipos + `check_meta` conforme as regras acima.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(control): probe Graph API + check_meta ao vivo`.

---

### Task 3: check_google ao vivo (reusa troca OAuth)

**Files:**
- Modify: `revy-trafego/app/control/integrations_health.py` (add `check_google`)
- Test: `revy-trafego/tests/test_integrations_health_google.py`

**Interfaces:**
- Consumes: `GoogleAdsConnection` (models), `app.cripto.decifrar`, e a porta de acesso do Google (`HttpGoogleAdsTokenExchanger._access_token(refresh_token)` OU a `GoogleAdsPorts` já injetável de `google_ads_http.py` — prefira uma **porta injetável** `def obter_access_token(refresh_token) -> str` para poder mockar).
- Produces: `check_google(db, store, exchanger) -> GroupHealth`.

**Regras:** sem `GoogleAdsConnection` ou sem `refresh_token_ciphertext` → `GroupHealth(MISSING, [ItemHealth("google_ads", MISSING)])`. Com → `obter_access_token(decifrar(refresh_token_ciphertext))`; sucesso (string não vazia) → CONNECTED; exceção/ვazio → ERROR(mensagem curta, sem token).

- [ ] **Step 1: Failing test**
```python
# revy-trafego/tests/test_integrations_health_google.py
from app.control.integrations_health import check_google, HealthStatus


class FakeExchanger:
    def __init__(self, ok=True):
        self.ok, self.chamadas = ok, 0
    def obter_access_token(self, refresh_token):
        self.chamadas += 1
        if not self.ok:
            raise RuntimeError("invalid_grant")
        return "access-xyz"


def test_check_google_missing_sem_conexao(db, loja):
    grupo = check_google(db, loja, FakeExchanger())
    assert grupo.status is HealthStatus.MISSING


def test_check_google_connected(db, loja, google_conn_factory):
    google_conn_factory(loja, refresh_token="rt-abc")  # cria GoogleAdsConnection com refresh cifrado
    probe = FakeExchanger(ok=True)
    grupo = check_google(db, loja, probe)
    assert grupo.status is HealthStatus.CONNECTED and probe.chamadas == 1


def test_check_google_error_quando_refresh_invalido(db, loja, google_conn_factory):
    google_conn_factory(loja, refresh_token="rt-ruim")
    grupo = check_google(db, loja, FakeExchanger(ok=False))
    assert grupo.status is HealthStatus.ERROR
```
> Nota: crie o `google_conn_factory` no teste inspecionando os campos reais de `GoogleAdsConnection` (loja_id, refresh_token_ciphertext=cifrar("rt..."), etc.).

- [ ] **Step 2–5:** run→fail; implement `check_google` + a porta `obter_access_token` (wrapper fino sobre `HttpGoogleAdsTokenExchanger`); run→pass; commit `feat(control): check_google ao vivo (troca refresh->access)`.

---

### Task 4: Agregador health_da_loja + cache

**Files:**
- Modify: `revy-trafego/app/control/integrations_health.py` (add `health_da_loja`, cache singleton, `invalidar`)
- Test: `revy-trafego/tests/test_integrations_health_agg.py`

**Interfaces:**
- Produces:
  - `health_da_loja(db, store, *, probe, exchanger, forcar=False, cache=None, clock=None) -> dict` — monta `{"meta":{...},"google":{...},"checked_at":..., "cache_ttl_seg":...}` (WhatsApp entra na Fase 2). Serializa `GroupHealth`/`ItemHealth` para dict (`status` como string).
  - Cache module-level `_CACHE: TTLCache` (ttl de `settings.integracoes_health_ttl_seg`); chave `(store.id,)`. `forcar=True` ignora e sobrescreve.
  - `invalidar(store_id: str) -> None` — `_CACHE.invalidate((store_id,))`.

**Regras de cache:** 1ª chamada checa (probe/exchanger chamados) e grava; 2ª dentro do TTL retorna do cache sem chamar probe; `forcar=True` re-checa; `invalidar(store_id)` força recheck na próxima.

- [ ] **Step 1: Failing test**
```python
# revy-trafego/tests/test_integrations_health_agg.py
from app.control.integrations_health import health_da_loja, invalidar
from app.control.health_cache import TTLCache


def test_agrega_meta_e_google(db, loja):
    out = health_da_loja(db, loja, probe=FakeGraphProbe(), exchanger=FakeExchanger())
    assert set(out.keys()) >= {"meta", "google", "checked_at", "cache_ttl_seg"}
    assert out["meta"]["status"] in {"connected", "error", "missing"}


def test_cache_evita_rechecagem(db, loja):
    t = {"v": 0.0}
    cache = TTLCache(ttl_seg=600, clock=lambda: t["v"])
    probe = FakeGraphProbe()
    health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), cache=cache, clock=lambda: t["v"])
    n1 = probe.chamadas
    health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), cache=cache, clock=lambda: t["v"])
    assert probe.chamadas == n1                      # 2ª veio do cache
    health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), cache=cache, clock=lambda: t["v"], forcar=True)
    assert probe.chamadas > n1                        # forçou recheck
```
(Import `FakeGraphProbe`/`FakeExchanger` das tasks anteriores ou redefina localmente.)

- [ ] **Step 2–5:** run→fail; implement; run→pass; commit `feat(control): agregador de health por loja + cache`.

---

### Task 5: Endpoint GET /control/v1/lojas/{id}/integracoes/health

**Files:**
- Modify: `revy-trafego/app/web/control_ui.py` (rota JSON + wiring do probe/exchanger reais e do cache singleton)
- Test: `revy-trafego/tests/test_integracoes_health_endpoint.py`

**Interfaces:**
- Produces: `GET /control/v1/lojas/{loja_id}/integracoes/health?forcar=0|1` → 200 JSON do agregador; 401/403 sem gestor; 404 loja inexistente. Usa `gestor_atual(request, db)`; instancia `HttpGraphProbe`/exchanger reais e o `_CACHE`.

- [ ] **Step 1: Failing test** (TestClient; logar como gestor via helper existente; criar loja; monkeypatch do probe/exchanger reais para não bater na rede — ex.: `monkeypatch.setattr('app.web.control_ui._build_probe', lambda: FakeGraphProbe())`). Asserts: 200; JSON tem `meta`/`google`; `?forcar=1` aceito; sem sessão → 401/redirect.
- [ ] **Step 2–5:** run→fail; implement (com `_build_probe()`/`_build_exchanger()` para permitir o monkeypatch dos testes); run→pass; commit `feat(control): endpoint de health das integracoes da loja`.

---

### Task 6: Invalidação de cache em connect/disconnect

**Files:**
- Modify: `revy-trafego/app/control/integrations.py` (chamar `integrations_health.invalidar(store_id)` nos `upsert_*`/`disconnect_*` do Meta)
- Modify: o ponto de connect/disconnect do Google (em `control_ui.py`/serviço de google-ads) → `invalidar(store_id)`
- Test: `revy-trafego/tests/test_health_invalidacao.py`

- [ ] **Step 1: Failing test** — após popular o cache para a loja, chamar o upsert/disconnect do Pixel e assertar que a próxima `health_da_loja` re-checou (probe chamado de novo). Idem para o Google connect/disconnect.
- [ ] **Step 2–5:** run→fail; adicionar as chamadas `invalidar(store_id)` (import tardio para evitar ciclo se necessário); run→pass; **rodar suite completa** (`.venv/bin/python -m pytest -q`, verde exceto a falha pré-existente do outbox); commit `feat(control): invalida cache de health ao conectar/desconectar`.

---

---

## Fase 2 — WhatsApp no agregador (revy-trafego-only)

**Achado:** o Control já tem `ChatbotClient` (`revy-trafego/app/clients/chatbot.py`) e resolução de token por loja (`settings.chatbot_token_para(loja_slug)`). O chatbot expõe `GET /v1/whatsapp/canais` (retorna canais com `estado` ∈ {conectado, pendente, desconectado, inativo} e `e164_or_label`/`ativo`). Então o Control fala **direto** com o chatbot por loja — sem tocar Portal nem chatbot. Regra de rollup (decisão do owner): 🟢 só se **todos** os canais operáveis estão `conectado`; 🔴 se algum não; ⚪ se nenhum canal operável (ou chatbot não configurado).

### Task 7: listar_canais_whatsapp no ChatbotClient + check_whatsapp

**Files:**
- Modify: `revy-trafego/app/clients/chatbot.py` (add `listar_canais_whatsapp`)
- Modify: `revy-trafego/app/control/integrations_health.py` (add `check_whatsapp` + `WhatsappPort`/`ChatbotWhatsappPort`)
- Test: `revy-trafego/tests/test_integrations_health_whatsapp.py`

**Interfaces:**
- `ChatbotClient.listar_canais_whatsapp() -> list[dict]` → `self._request("GET", "/v1/whatsapp/canais")` e retorna `list(dados.get("canais") or [])` (espelha o client do Portal).
- `class WhatsappPort(Protocol): def listar_canais(self, loja_slug: str) -> list[dict] | None: ...` — retorna `None` quando o chatbot **não está configurado** para a loja (→ MISSING), lança exceção quando a chamada **falha** (→ ERROR), senão a lista de canais.
- `class ChatbotWhatsappPort:` real — monta `ChatbotClient(settings.chatbot_url, settings.chatbot_token_para(loja_slug), settings.request_timeout)`; se `not client.configurado` → `None`; senão `client.listar_canais_whatsapp()`.
- `check_whatsapp(store, port: WhatsappPort) -> GroupHealth`.

**Regras de `check_whatsapp`:**
- `port.listar_canais(store.slug)` lança → `GroupHealth(ERROR, (ItemHealth("whatsapp", ERROR, "falha ao consultar WhatsApp"),))`.
- retorno `None` → `GroupHealth(MISSING, (ItemHealth("whatsapp", MISSING, None),))`.
- operáveis = canais com `ativo` truthy **e** `estado != "inativo"`. Sem operáveis → MISSING.
- por canal operável: `conectado` → `ItemHealth("whatsapp", CONNECTED, None)`; senão → `ItemHealth("whatsapp", ERROR, f"{label}: {estado}")` (label = `e164_or_label`).
- status do grupo via o `_group_status` já existente (any ERROR → ERROR; senão ≥1 non-missing → CONNECTED). Nunca logar/retornar segredo (labels são telefones — ok exibir label, é o número da loja; não é segredo de API).

- [ ] **Step 1: Failing test**
```python
# revy-trafego/tests/test_integrations_health_whatsapp.py
from app.control.integrations_health import HealthStatus, check_whatsapp


class FakeWppPort:
    def __init__(self, canais=None, indisponivel=False, erro=False):
        self.canais, self.indisponivel, self.erro = canais, indisponivel, erro
    def listar_canais(self, loja_slug):
        if self.erro:
            raise RuntimeError("timeout")
        return None if self.indisponivel else (self.canais or [])


class _Store:
    id = "loja-1"; slug = "loja-1"


def test_whatsapp_missing_sem_config():
    assert check_whatsapp(_Store(), FakeWppPort(indisponivel=True)).status is HealthStatus.MISSING

def test_whatsapp_missing_sem_canais_operaveis():
    canais = [{"e164_or_label": "x", "estado": "inativo", "ativo": False}]
    assert check_whatsapp(_Store(), FakeWppPort(canais)).status is HealthStatus.MISSING

def test_whatsapp_connected_todos_conectados():
    canais = [{"e164_or_label": "a", "estado": "conectado", "ativo": True},
              {"e164_or_label": "b", "estado": "conectado", "ativo": True}]
    assert check_whatsapp(_Store(), FakeWppPort(canais)).status is HealthStatus.CONNECTED

def test_whatsapp_error_se_algum_caido():
    canais = [{"e164_or_label": "a", "estado": "conectado", "ativo": True},
              {"e164_or_label": "b", "estado": "desconectado", "ativo": True}]
    g = check_whatsapp(_Store(), FakeWppPort(canais))
    assert g.status is HealthStatus.ERROR
    assert any(i.status is HealthStatus.ERROR for i in g.itens)

def test_whatsapp_error_quando_chamada_falha():
    assert check_whatsapp(_Store(), FakeWppPort(erro=True)).status is HealthStatus.ERROR
```

- [ ] **Step 2–5:** run→fail; implementar `listar_canais_whatsapp` + `WhatsappPort`/`ChatbotWhatsappPort` + `check_whatsapp`; run→pass; commit `feat(control): check_whatsapp ao vivo (canais do chatbot por loja)`.

### Task 8: WhatsApp no agregador + endpoint

**Files:**
- Modify: `revy-trafego/app/control/integrations_health.py` (`health_da_loja` inclui `whatsapp`)
- Modify: `revy-trafego/app/web/control_ui.py` (`_build_whatsapp_port` + passar ao `health_da_loja`)
- Test: `revy-trafego/tests/test_integrations_health_agg.py` (estender) e o endpoint (`tests/test_integracoes_health_endpoint.py`, estender)

**Interfaces:**
- `health_da_loja(db, store, *, probe, exchanger, whatsapp_port, forcar=False, cache=None, clock=None) -> dict` — adiciona `"whatsapp": <grupo serializado>` ao dict (junto de `meta`/`google`). Cache continua cobrindo o dict inteiro.
- `control_ui._build_whatsapp_port() -> ChatbotWhatsappPort` (monkeypatchável nos testes); o endpoint passa `whatsapp_port=_build_whatsapp_port()`.

- [ ] **Step 1: Failing test** — estender `test_integrations_health_agg.py`: `health_da_loja(..., whatsapp_port=FakeWppPort([...conectado...]))` retorna dict com chave `"whatsapp"` cujo `status=="connected"`. No endpoint, monkeypatch `_build_whatsapp_port` p/ um fake e assertar que o JSON tem `whatsapp`.
- [ ] **Step 2–5:** run→fail; implementar; run→pass; **suite completa** (verde exceto o outbox pré-existente); commit `feat(control): WhatsApp no agregador de health + endpoint`.

> Nota: o cache do WhatsApp segue o mesmo TTL (10min). O Control **não** invalida em connect/disconnect de WhatsApp (essa ação é no Portal/chatbot) — staleness de até 10min é aceita (decisão do owner) + "Testar agora".

---

## Fase 3 — Badge UI no Control (aba Integrações do detalhe da loja)

**Onde:** `revy-trafego/app/templates/control/loja_detail.html`, no topo do painel `#panel-integracoes` (a aba "Integrações" já existe). **Visual:** aprovado no mockup (3 badges Meta·Google·WhatsApp, 🟢/🔴/⚪, expandir sub-itens, "Testar agora"), cara de marca via tokens do `app.css`. **Dados:** JS busca `GET /control/v1/lojas/{id}/integracoes/health` no load e no "Testar agora" (`?forcar=1`); a página não bloqueia. Só status (não clicável pra corrigir), dono/gerente (a aba já é do gestor).

### Task 9: Container + CSS do painel de saúde

**Files:**
- Modify: `revy-trafego/app/templates/control/loja_detail.html` (container `#integracoes-health` no topo de `#panel-integracoes`, com `data-loja-id`)
- Modify: `revy-trafego/app/static/css/app.css` (estilos `.integ-*` usando os tokens existentes — `--green/--red/--ink-muted`, `--surface`, `--line`, `--radius`; estados ok/err/off; pill+dot; sub-itens; chevron; spinner do botão)
- Test: `revy-trafego/tests/test_control_integracoes_health_ui.py`

**Interfaces:** o container tem `id="integracoes-health"` e `data-loja-id="{{ store.id }}"`; um `<button data-integ-testar>` e um alvo `<div data-integ-corpo>` com um estado inicial "Carregando…". Nenhum dado sensível no HTML (o JS busca via endpoint autenticado).

- [ ] **Step 1: Failing test** — TestClient logado como gestor abre `/app/control/lojas/{id}` (ou a aba) e assert: o HTML contém `id="integracoes-health"` e `data-loja-id="<id>"` e o botão "Testar agora". Usar o helper de login de gestor dos testes existentes.
- [ ] **Step 2–5:** run→fail; adicionar o container no template + os estilos `.integ-*` no `app.css` (seguir o mockup: `.integ-card`, `.integ-row`, `.integ-pill.ok/.err/.off`, `.integ-dot`, `.integ-sub`, chevron, spinner); run→pass; commit `feat(control): container + estilos do painel de status das integracoes`.

### Task 10: JS que consome o endpoint e renderiza os badges

**Files:**
- Create: `revy-trafego/app/static/js/integracoes_health.js`
- Modify: `revy-trafego/app/templates/control/loja_detail.html` (incluir o `<script src>` e chamar init com o `data-loja-id`)
- Test: `revy-trafego/tests/test_control_integracoes_health_ui.py` (estender: assert que o `<script ... integracoes_health.js>` está incluído; e um teste de render do endpoint→shape que o JS espera, garantindo o contrato)

**Comportamento do JS (vanilla, sem dependência):**
- No load: `fetch("/control/v1/lojas/"+lojaId+"/integracoes/health")` → renderiza os 3 grupos (rótulos PT: Meta/Google/WhatsApp; sub-itens por `kind`). Mapear `status`→classe (`connected`→ok, `error`→err, `missing`→off) e rótulo ("Conectado"/"Com erro"/"Não configurado"). Mensagem do item quando houver. Expandir/colapsar por grupo.
- "Testar agora": refaz o fetch com `?forcar=1`, mostra "Verificando…" no botão, atualiza "Verificado agora".
- Erro de fetch (rede/500): mostra um estado neutro "Não foi possível verificar agora — tente de novo", sem quebrar a página. Nunca renderiza token (o endpoint não manda).
- Rótulos e cores só via classes CSS da Task 9. `Cache-Control` do fetch: default (o cache é no servidor).

- [ ] **Step 1: Failing test** — assert o `<script>` incluído; (o render em si é client-side, difícil de unit-testar sem browser — cobrir o **contrato** do endpoint com um teste que valida as chaves/kinds que o JS consome: `meta/google/whatsapp`, cada `itens[].kind/status/message`).
- [ ] **Step 2–5:** run→fail; implementar o JS + inclusão no template; rodar suite; commit `feat(control): painel de status das integracoes (render via endpoint + testar agora)`.

> Nota: render client-side (JS-required) é aceitável numa tela de admin. O visual final deve ser conferido pelo owner (review visual) — o mockup aprovado é a referência.

## Fase 4 — Badge UI no shell da Revy Loja (Portal) — esboço

Item **"Integrações"** em Ajustes (`app/loja/navigation.py`, dono/gerente) → página no shell (`portal-gestao/app/templates/loja/integracoes.html`, estende `base.html`) reusando o mesmo componente. O Portal consome o endpoint do Control por HTTP (`clients/revy_trafego.py`) OU embute o mesmo JS apontando para o Control. Detalhar após a Fase 3, com review visual do owner.

## Fases seguintes (esboço — detalhar com review do owner)

- **Fase 3 — Badge UI no Control** (detalhe da loja): componente de 3 badges com expandir, cores por estado, "Testar agora" (fetch `?forcar=1`), poll leve opcional. Seguir os templates/estilos do Control. **Review visual do owner.**
- **Fase 4 — Badge UI no Portal/Loja shell:** consome o agregador do Control por HTTP (`clients/revy_trafego.py`) + WhatsApp local; badge no topo/lado do shell. **Review visual do owner.**

## Self-review (cobertura da Fase 1 vs spec)

- Checagem live Meta (Pixel/CAPI/Ads) via probe injetável: Task 2. ✓
- Checagem live Google (refresh→access): Task 3. ✓
- Cache 10min + relógio injetável + forçar: Tasks 1, 4. ✓
- Endpoint agregado + auth: Task 5. ✓
- Invalidação em eventos: Task 6. ✓
- Nunca vazar token; timeouts; mocks nos testes: Global Constraints + tasks. ✓
- WhatsApp + UIs: fora da Fase 1 (fases 2–4). ✓
