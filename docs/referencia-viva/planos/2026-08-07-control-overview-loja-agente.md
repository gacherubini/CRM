# Control Visão Geral de negócio + filtro lojas ativas + Loja Desempenho do agente — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar (1) uma Visão Geral de negócio no Revy Control com KPIs de vendas/ticket/leads e desempenho por loja, (2) um filtro que mostra só lojas ativas no seletor e na Visão Geral, e (3) uma página de Desempenho do agente (bot) no Revy Loja alimentada por um endpoint agregado novo no Chatbot.

**Architecture:** Três produtos independentes integrados por HTTP. Control (`revy-trafego`) lê vendas de `vendas_projetadas` (banco local) e leads do Chatbot (client existente). O Chatbot (`chatbot-api`) ganha um endpoint agregado `/v1/atendimento/resumo` (SQL sobre `conversas`). A Loja (`portal-gestao`) consome esse endpoint numa página nova do shell. Sem import Python entre produtos.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, httpx, pytest. Gráficos em CSS puro (sem lib).

## Global Constraints

- Flags default OFF. Task 1 (Control Visão Geral) fica sob `REVY_CONTROL_DASHBOARD_ENABLED` (já existe). Task 3 (Loja Agente) fica sob `REVY_LOJA_ATENDIMENTO_ENABLED` (já existe). Task 2 (filtro) não cria flag.
- "Loja ativa" = **somente** `StoreStatus.ACTIVE` (`"ativa"`). Suspensa/encerrada/rascunho/em_configuracao contam como inativas.
- **Nunca inventar zero**: quando o Chatbot estiver indisponível, os campos de leads/atendimento viram `None` e a UI mostra "indisponível".
- Sem import Python entre produtos; integração só por HTTP/contrato.
- Copy da UI em português.
- Rodar testes a partir da pasta de cada produto: `.\.venv\Scripts\python.exe -m pytest -q` (Windows) ou `python -m pytest -q`.
- Nenhum segredo em log.

---

## File Structure

**Task 2 — filtro lojas ativas (Control):**
- Modify: `revy-trafego/app/web/control_ui.py` — novo helper `_selector_stores`; substituir os 4 pontos que montam `nav_stores`.
- Test: `revy-trafego/tests/test_control_selector_ativas.py` (novo).

**Task 1 — Visão Geral de negócio (Control):**
- Modify: `revy-trafego/app/control/dashboard.py` — dataclasses `StorePerformance`, `NetworkHighlights`, `NetworkOverview`; protocolo `_LeadsCountPort`; método `network_overview`.
- Modify: `revy-trafego/app/web/control_ui.py` — adapter `_ChatbotLeadsPort`; `dashboard_page` passa `network` ao template.
- Modify: `revy-trafego/app/templates/control/dashboard.html` — cards + "Desempenho por loja" + "Destaques" no topo.
- Test: `revy-trafego/tests/test_dashboard_network_overview.py` (novo) + `revy-trafego/tests/test_dashboard_business_ui.py` (novo).

**Task 3 — Desempenho do agente (Chatbot + Loja):**
- Modify: `chatbot-api/app/servico.py` — função `resumo_atendimento`.
- Modify: `chatbot-api/app/main.py` — endpoint `GET /v1/atendimento/resumo` + helper `_janela_mes`.
- Test: `chatbot-api/tests/test_resumo_atendimento.py` (novo).
- Modify: `portal-gestao/app/clients/chatbot.py` — método `resumo_atendimento`.
- Modify: `portal-gestao/app/loja/routes.py` — rota `GET /app/loja/agente`.
- Modify: `portal-gestao/app/loja/navigation.py` — NavItem "Agente" na seção Vendas.
- Create: `portal-gestao/app/templates/loja/agente.html`.
- Test: `portal-gestao/tests/test_loja_agente.py` (novo).

---

## Task 1: Control — seletor mostra só lojas ativas (Task 2 do produto)

**Files:**
- Modify: `revy-trafego/app/web/control_ui.py` (helper novo + 4 substituições)
- Test: `revy-trafego/tests/test_control_selector_ativas.py`

**Interfaces:**
- Produces: `_selector_stores(scoped) -> list` — recebe a lista de `AccessControl.scope()` (itens com `.store.status` e `.store.slug`); devolve só os ativos. Com RBAC ligado devolve os itens; senão devolve lista de slugs.

- [ ] **Step 1: Escrever o teste que falha**

Criar `revy-trafego/tests/test_control_selector_ativas.py`:

```python
from dataclasses import replace
from types import SimpleNamespace

from app.control.types import StoreStatus
from app.web import control_ui as control_ui_mod


def _item(slug, status):
    return SimpleNamespace(store=SimpleNamespace(slug=slug, status=status), role=None)


def _patch_rbac(monkeypatch, enabled):
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(control_ui_mod.settings, revy_control_rbac_enabled=enabled),
    )


def test_selector_rbac_lista_so_ativas(monkeypatch):
    _patch_rbac(monkeypatch, True)
    scoped = [
        _item("viva", StoreStatus.ACTIVE),
        _item("suspensa", StoreStatus.SUSPENDED),
        _item("rascunho", StoreStatus.DRAFT),
    ]
    result = control_ui_mod._selector_stores(scoped)
    assert [i.store.slug for i in result] == ["viva"]


def test_selector_sem_rbac_devolve_slugs_ativas(monkeypatch):
    _patch_rbac(monkeypatch, False)
    scoped = [
        _item("viva", StoreStatus.ACTIVE),
        _item("config", StoreStatus.CONFIGURING),
    ]
    result = control_ui_mod._selector_stores(scoped)
    assert result == ["viva"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_control_selector_ativas.py -q`
Expected: FAIL com `AttributeError: module 'app.web.control_ui' has no attribute '_selector_stores'`.

- [ ] **Step 3: Implementar o helper**

Em `revy-trafego/app/web/control_ui.py`, logo após `_dashboard_surface_enabled` (perto da linha 274), adicionar:

```python
def _selector_stores(scoped):
    """Lojas do seletor lateral: só ativas (Task 2 — esconde inativas do dia a dia).

    Com RBAC ligado, o template usa item.store.id/slug/name → devolvemos os itens.
    Sem RBAC, o seletor usa slugs → devolvemos slugs. A tela de gestão "Lojas"
    NÃO usa este helper (continua listando todas as lojas)."""
    ativas = [item for item in scoped if item.store.status is StoreStatus.ACTIVE]
    if settings.revy_control_rbac_enabled:
        return ativas
    return [item.store.slug for item in ativas]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_control_selector_ativas.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Ligar o helper nos 4 pontos**

Substituir o bloco repetido (aparece 4x):

```python
    nav_stores = (
        stores
        if settings.revy_control_rbac_enabled
        else [item.store.slug for item in stores]
    )
```

por:

```python
    nav_stores = _selector_stores(stores)
```

Locais: `dashboard_page` (~313-317), `list_control_accounts_page` (~381-385), `_render_stores_page` (~1665-1669), `_render_store_detail` (~1960-1964). Em `_render_stores_page`, o contexto `"stores": stores` (tabela de gestão) **permanece intacto** — só `nav_stores` muda.

- [ ] **Step 6: Escrever o teste de integração (gestão mostra todas; seletor só ativas)**

Adicionar em `revy-trafego/tests/test_control_selector_ativas.py`:

```python
from app.auth import hash_senha
from app.config import settings as app_settings
from app.db import SessionLocal
from app.models import Loja, GestorRevy
from app.web import control as control_mod


def _enable(monkeypatch):
    patched = replace(
        app_settings,
        revy_control_enabled=True,
        revy_control_dashboard_enabled=True,
        revy_control_rbac_enabled=False,
    )
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


def test_gestao_lista_todas_seletor_so_ativas(client, monkeypatch):
    _enable(monkeypatch)
    with SessionLocal() as db:
        db.add(Loja(nome="Loja Viva", slug="loja-viva", status="ativa"))
        db.add(Loja(nome="Loja Parada", slug="loja-parada", status="suspensa"))
        db.commit()
    client.post("/login", data={"email": "trafego@revy.local", "senha": "secret-teste"},
                follow_redirects=False)

    pagina = client.get("/app/control/lojas")

    assert pagina.status_code == 200
    # Gestão mostra as duas lojas (nomes na tabela)
    assert "Loja Viva" in pagina.text
    assert "Loja Parada" in pagina.text
    # Seletor lateral (base.html) só oferece a ativa como <option value="slug">
    assert 'value="loja-viva"' in pagina.text
    assert 'value="loja-parada"' not in pagina.text
```

> Nota: o login `trafego@revy.local` / `secret-teste` é o admin semeado pela fixture autouse do conftest. Se a senha do seed for outra no ambiente, ajustar aqui.

- [ ] **Step 7: Rodar a suíte do arquivo**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_control_selector_ativas.py -q`
Expected: PASS (3 testes).

- [ ] **Step 8: Commit**

```bash
git add revy-trafego/app/web/control_ui.py revy-trafego/tests/test_control_selector_ativas.py
git commit -m "feat(control): seletor de loja mostra só lojas ativas"
```

---

## Task 2: Control — read model `network_overview` (Task 1 do produto, domínio)

**Files:**
- Modify: `revy-trafego/app/control/dashboard.py`
- Test: `revy-trafego/tests/test_dashboard_network_overview.py`

**Interfaces:**
- Consumes: `StoreControl.list(actor) -> tuple[StoreView, ...]` (StoreView tem `id, name, slug, status`); modelo `VendaProjetada` (`loja_id`, `preco_venda`, `confirmada_em`, `id`).
- Produces:
  - `class _LeadsCountPort(Protocol): def count_for_store(self, slug: str) -> int | None: ...`
  - `NetworkOverview(lojas_ativas: int, lojas_total: int, vendas_mes: int, vendas_delta_pct: float | None, ticket_medio: Decimal | None, leads_rede: int | None, por_loja: tuple[StorePerformance, ...], destaques: NetworkHighlights)`
  - `StorePerformance(store_id: str, slug: str, name: str, vendas: int, leads: int | None, conversao: float | None)`
  - `NetworkHighlights(melhor_loja_nome: str | None, melhor_loja_vendas: int, ticket_medio: Decimal | None)`
  - `DashboardControl.network_overview(actor, *, leads_port: _LeadsCountPort | None = None) -> NetworkOverview`

- [ ] **Step 1: Escrever o teste que falha**

Criar `revy-trafego/tests/test_dashboard_network_overview.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

from app.control.dashboard import DashboardControl
from app.control.types import Actor
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VendaProjetada


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _venda(loja_id, slug, preco, quando):
    return VendaProjetada(
        id=f"v-{slug}-{preco}",
        loja_slug=slug,
        loja_id=loja_id,
        preco_venda=Decimal(preco),
        status="confirmada",
        criada_em=quando,
        confirmada_em=quando,
        atualizada_em=quando,
    )


class _FakeLeads:
    def __init__(self, mapa):
        self.mapa = mapa

    def count_for_store(self, slug):
        return self.mapa.get(slug)


def test_network_overview_conta_vendas_ticket_e_leads():
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        viva = Loja(nome="Viva", slug="viva", status="ativa")
        parada = Loja(nome="Parada", slug="parada", status="suspensa")
        db.add_all([viva, parada])
        db.flush()
        db.add(_venda(viva.id, "viva", "10000.00", agora))
        db.add(_venda(viva.id, "viva", "20000.00", agora))
        db.commit()
        viva_id = viva.id

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(), leads_port=_FakeLeads({"viva": 8})
    )

    assert overview.lojas_ativas == 1
    assert overview.lojas_total == 2
    assert overview.vendas_mes == 2
    assert overview.ticket_medio == Decimal("15000.00")
    assert overview.leads_rede == 8
    assert len(overview.por_loja) == 1  # só a loja ativa
    perf = overview.por_loja[0]
    assert perf.store_id == viva_id
    assert perf.vendas == 2
    assert perf.leads == 8
    assert round(perf.conversao, 3) == 0.25  # 2/8


def test_network_overview_degrada_leads_quando_none():
    with SessionLocal() as db:
        viva = Loja(nome="Viva", slug="viva", status="ativa")
        db.add(viva)
        db.commit()

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(), leads_port=_FakeLeads({})  # sem contagem → None
    )

    assert overview.leads_rede is None
    assert overview.por_loja[0].leads is None
    assert overview.por_loja[0].conversao is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_network_overview.py -q`
Expected: FAIL com `AttributeError: 'DashboardControl' object has no attribute 'network_overview'`.

- [ ] **Step 3: Implementar dataclasses + protocolo**

Em `revy-trafego/app/control/dashboard.py`, adicionar imports no topo (junto dos existentes):

```python
from datetime import datetime, timezone, timedelta  # datetime já está importado; garantir timezone/timedelta
from decimal import Decimal
from sqlalchemy import func
from app.models import VendaProjetada  # somar ao bloco de import de app.models
```

E as estruturas (perto dos outros `@dataclass`):

```python
@dataclass(frozen=True)
class StorePerformance:
    store_id: str
    slug: str
    name: str
    vendas: int
    leads: int | None
    conversao: float | None


@dataclass(frozen=True)
class NetworkHighlights:
    melhor_loja_nome: str | None
    melhor_loja_vendas: int
    ticket_medio: Decimal | None


@dataclass(frozen=True)
class NetworkOverview:
    lojas_ativas: int
    lojas_total: int
    vendas_mes: int
    vendas_delta_pct: float | None
    ticket_medio: Decimal | None
    leads_rede: int | None
    por_loja: tuple[StorePerformance, ...]
    destaques: NetworkHighlights


class _LeadsCountPort(Protocol):
    def count_for_store(self, slug: str) -> int | None: ...
```

- [ ] **Step 4: Implementar `network_overview`**

Adicionar como método de `DashboardControl`:

```python
    def network_overview(
        self, actor: Actor, *, leads_port: _LeadsCountPort | None = None
    ) -> NetworkOverview:
        """KPIs de negócio no escopo do ator. Vendas/ticket de vendas_projetadas;
        leads do Chatbot (port injetado). Só lojas ativas entram em por_loja."""
        stores = self._stores.list(actor)
        ativas = [s for s in stores if s.status is StoreStatus.ACTIVE]
        ativa_ids = [s.id for s in ativas]

        agora = datetime.now(timezone.utc)
        inicio_mes = datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)
        fim_mes = (
            datetime(agora.year + 1, 1, 1, tzinfo=timezone.utc)
            if agora.month == 12
            else datetime(agora.year, agora.month + 1, 1, tzinfo=timezone.utc)
        )
        inicio_mes_ant = (inicio_mes - timedelta(days=1)).replace(day=1)

        vendas_por_loja: dict[str, int] = {}
        vendas_mes = 0
        ticket_medio: Decimal | None = None
        vendas_mes_ant = 0
        if ativa_ids:
            with self._session_factory() as db:
                for loja_id, count in (
                    db.query(VendaProjetada.loja_id, func.count(VendaProjetada.id))
                    .filter(
                        VendaProjetada.loja_id.in_(ativa_ids),
                        VendaProjetada.confirmada_em >= inicio_mes,
                        VendaProjetada.confirmada_em < fim_mes,
                    )
                    .group_by(VendaProjetada.loja_id)
                    .all()
                ):
                    vendas_por_loja[loja_id] = count
                total_count, total_avg = (
                    db.query(
                        func.count(VendaProjetada.id),
                        func.avg(VendaProjetada.preco_venda),
                    )
                    .filter(
                        VendaProjetada.loja_id.in_(ativa_ids),
                        VendaProjetada.confirmada_em >= inicio_mes,
                        VendaProjetada.confirmada_em < fim_mes,
                    )
                    .one()
                )
                vendas_mes = int(total_count or 0)
                ticket_medio = (
                    Decimal(total_avg).quantize(Decimal("0.01"))
                    if total_avg is not None
                    else None
                )
                vendas_mes_ant = int(
                    db.query(func.count(VendaProjetada.id))
                    .filter(
                        VendaProjetada.loja_id.in_(ativa_ids),
                        VendaProjetada.confirmada_em >= inicio_mes_ant,
                        VendaProjetada.confirmada_em < inicio_mes,
                    )
                    .scalar()
                    or 0
                )

        delta_pct: float | None = None
        if vendas_mes_ant > 0:
            delta_pct = round((vendas_mes - vendas_mes_ant) / vendas_mes_ant * 100, 1)

        por_loja: list[StorePerformance] = []
        leads_total = 0
        algum_lead = False
        for store in ativas:
            vendas = vendas_por_loja.get(store.id, 0)
            leads = leads_port.count_for_store(store.slug) if leads_port else None
            if leads is not None:
                algum_lead = True
                leads_total += leads
            conversao = (
                (vendas / leads) if (leads is not None and leads > 0) else None
            )
            por_loja.append(
                StorePerformance(
                    store_id=store.id,
                    slug=store.slug,
                    name=store.name,
                    vendas=vendas,
                    leads=leads,
                    conversao=conversao,
                )
            )

        leads_rede = leads_total if algum_lead else None
        melhor = max(por_loja, key=lambda p: p.vendas, default=None)
        destaques = NetworkHighlights(
            melhor_loja_nome=melhor.name if melhor and melhor.vendas > 0 else None,
            melhor_loja_vendas=melhor.vendas if melhor else 0,
            ticket_medio=ticket_medio,
        )
        return NetworkOverview(
            lojas_ativas=len(ativas),
            lojas_total=len(stores),
            vendas_mes=vendas_mes,
            vendas_delta_pct=delta_pct,
            ticket_medio=ticket_medio,
            leads_rede=leads_rede,
            por_loja=tuple(por_loja),
            destaques=destaques,
        )
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_network_overview.py -q`
Expected: PASS (2 testes).

- [ ] **Step 6: Commit**

```bash
git add revy-trafego/app/control/dashboard.py revy-trafego/tests/test_dashboard_network_overview.py
git commit -m "feat(control): read model network_overview (vendas, ticket, leads)"
```

---

## Task 3: Control — ligar Visão Geral de negócio na UI (Task 1 do produto, HTTP+template)

**Files:**
- Modify: `revy-trafego/app/web/control_ui.py` (adapter `_ChatbotLeadsPort`; `dashboard_page` passa `network`)
- Modify: `revy-trafego/app/templates/control/dashboard.html`
- Test: `revy-trafego/tests/test_dashboard_business_ui.py`

**Interfaces:**
- Consumes: `DashboardControl.network_overview(actor, leads_port=...)`, `ChatbotClient(base_url, token, timeout).listar_leads()`, `settings.chatbot_url`, `settings.chatbot_token_para(slug)`.
- Produces: contexto de template com chave `network` (um `NetworkOverview`) e `network_ticket_brl` (str | None).

- [ ] **Step 1: Escrever o teste de UI que falha**

Criar `revy-trafego/tests/test_dashboard_business_ui.py`:

```python
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.config import settings as app_settings
from app.db import SessionLocal
from app.models import Loja, VendaProjetada
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod


def _enable(monkeypatch):
    patched = replace(
        app_settings,
        revy_control_enabled=True,
        revy_control_dashboard_enabled=True,
        revy_control_rbac_enabled=False,
    )
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


class _FakeLeadsPort:
    def count_for_store(self, slug):
        return 8


class _FakeLeadsIndisponivel:
    def count_for_store(self, slug):
        return None


def _seed_venda(monkeypatch, leads_port_cls):
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        viva = Loja(nome="Loja Viva", slug="loja-viva", status="ativa")
        db.add(viva)
        db.flush()
        db.add(
            VendaProjetada(
                id="v1", loja_slug="loja-viva", loja_id=viva.id,
                preco_venda=Decimal("30000.00"), status="confirmada",
                criada_em=agora, confirmada_em=agora, atualizada_em=agora,
            )
        )
        db.commit()
    monkeypatch.setattr(control_ui_mod, "_ChatbotLeadsPort", leads_port_cls)


def test_dashboard_mostra_kpis_de_negocio(client, monkeypatch):
    _enable(monkeypatch)
    _seed_venda(monkeypatch, _FakeLeadsPort)
    client.post("/login", data={"email": "trafego@revy.local", "senha": "secret-teste"},
                follow_redirects=False)

    r = client.get("/app/control/dashboard")

    assert r.status_code == 200
    assert "Vendas no mês" in r.text
    assert "Leads na rede" in r.text
    assert "Desempenho por loja" in r.text
    assert "Loja Viva" in r.text


def test_dashboard_leads_indisponivel_nao_inventa_zero(client, monkeypatch):
    _enable(monkeypatch)
    _seed_venda(monkeypatch, _FakeLeadsIndisponivel)
    client.post("/login", data={"email": "trafego@revy.local", "senha": "secret-teste"},
                follow_redirects=False)

    r = client.get("/app/control/dashboard")

    assert r.status_code == 200
    assert "indisponível" in r.text.lower()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_business_ui.py -q`
Expected: FAIL (o texto "Desempenho por loja" ainda não existe no template; `_ChatbotLeadsPort` ainda não existe).

- [ ] **Step 3: Adicionar o adapter e importar o client**

Em `revy-trafego/app/web/control_ui.py`, adicionar ao import de clients (perto do topo):

```python
from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel
```

E, perto de `_selector_stores`, o adapter:

```python
class _ChatbotLeadsPort:
    """Conta leads por loja via Chatbot (client por slug). None quando indisponível
    — nunca zero inventado."""

    def count_for_store(self, slug: str) -> int | None:
        try:
            client = ChatbotClient(
                settings.chatbot_url,
                settings.chatbot_token_para(slug),
                settings.request_timeout,
            )
            if not client.configurado:
                return None
            return len(client.listar_leads())
        except ChatbotIndisponivel:
            return None
```

- [ ] **Step 4: Ligar no `dashboard_page`**

Em `dashboard_page` (após `overview = DashboardControl(SessionLocal).overview(actor)`), adicionar:

```python
    network = DashboardControl(SessionLocal).network_overview(
        actor, leads_port=_ChatbotLeadsPort()
    )
    network_ticket_brl = (
        _format_brl(network.ticket_medio)
        if network.ticket_medio is not None
        else None
    )
```

E incluir no dicionário `context=`:

```python
            "network": network,
            "network_ticket_brl": network_ticket_brl,
```

- [ ] **Step 5: Renderizar o topo de negócio no template**

Em `revy-trafego/app/templates/control/dashboard.html`, logo após `</div>` do `<div class="page-heading">` (antes da `<section class="funil-summary" id="dashboard-counts">`), inserir:

```html
{% if network %}
<section class="funil-summary" aria-label="Indicadores da rede">
  <div class="funil-summary-card highlight">
    <span>Lojas ativas</span>
    <strong>{{ network.lojas_ativas }}</strong>
    <small>de {{ network.lojas_total }}</small>
  </div>
  <div class="funil-summary-card">
    <span>Vendas no mês</span>
    <strong>{{ network.vendas_mes }}</strong>
    <small>
      {% if network.vendas_delta_pct is not none %}
        {{ '▲' if network.vendas_delta_pct >= 0 else '▼' }} {{ network.vendas_delta_pct }}%
      {% else %}—{% endif %}
    </small>
  </div>
  <div class="funil-summary-card">
    <span>Ticket médio</span>
    <strong>{{ network_ticket_brl or '—' }}</strong>
    <small>no mês</small>
  </div>
  <div class="funil-summary-card">
    <span>Leads na rede</span>
    <strong>{% if network.leads_rede is not none %}{{ network.leads_rede }}{% else %}<span class="muted">indisponível</span>{% endif %}</strong>
    <small>lojas ativas</small>
  </div>
</section>

<section class="panel" id="dashboard-desempenho-loja">
  <div class="panel-heading">
    <h2>Desempenho por loja</h2>
    <p class="muted">Apenas lojas ativas. Metas chegam na próxima fase.</p>
  </div>
  {% if network.por_loja %}
  <div class="table-wrap">
    <table>
      <thead>
        <tr><th>Loja</th><th>Vendas</th><th>Leads</th><th>Conversão</th></tr>
      </thead>
      <tbody>
        {% for p in network.por_loja %}
        <tr>
          <td>{{ p.name }}</td>
          <td>{{ p.vendas }}</td>
          <td>{% if p.leads is not none %}{{ p.leads }}{% else %}<span class="muted">indisponível</span>{% endif %}</td>
          <td>{% if p.conversao is not none %}{{ (p.conversao * 100) | round(1) }}%{% else %}—{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <p class="muted">Nenhuma loja ativa no seu escopo.</p>
  {% endif %}
</section>

<section class="panel" id="dashboard-destaques">
  <div class="panel-heading"><h2>Destaques</h2></div>
  <div class="funil-summary">
    <div class="funil-summary-card">
      <span>Melhor loja</span>
      <strong>{{ network.destaques.melhor_loja_nome or '—' }}</strong>
      <small>{{ network.destaques.melhor_loja_vendas }} vendas</small>
    </div>
    <div class="funil-summary-card">
      <span>Ticket médio da rede</span>
      <strong>{{ network_ticket_brl or '—' }}</strong>
      <small>no mês</small>
    </div>
  </div>
</section>
{% endif %}
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_business_ui.py -q`
Expected: PASS (2 testes).

- [ ] **Step 7: Rodar a suíte do Control inteira**

Run: `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (sem regressões).

- [ ] **Step 8: Commit**

```bash
git add revy-trafego/app/web/control_ui.py revy-trafego/app/templates/control/dashboard.html revy-trafego/tests/test_dashboard_business_ui.py
git commit -m "feat(control): Visão Geral de negócio (KPIs + desempenho por loja)"
```

---

## Task 4: Chatbot — endpoint agregado `/v1/atendimento/resumo`

**Files:**
- Modify: `chatbot-api/app/servico.py`
- Modify: `chatbot-api/app/main.py`
- Test: `chatbot-api/tests/test_resumo_atendimento.py`

**Interfaces:**
- Consumes: modelo `Conversa` (`loja_id`, `status` em {`aberta`,`handoff`,`encerrada`}, `criada_em`), dependência `get_contexto` → `ctx.loja_id`, `get_db`.
- Produces:
  - `servico.resumo_atendimento(db, loja_id: str, desde: datetime, ate: datetime) -> dict` com chaves `atendimentos`, `transferidos`, `transferidos_pct`, `por_dia` (lista de `{"data": str, "atendimentos": int}`), `simulacoes` (`None`).
  - `GET /v1/atendimento/resumo?desde=&ate=` devolvendo esse dict.

- [ ] **Step 1: Escrever o teste que falha**

Criar `chatbot-api/tests/test_resumo_atendimento.py`:

```python
import uuid
from datetime import datetime, timezone

from app import models_db
from app.db import SessionLocal


def _conversa(loja_id, status, quando):
    return models_db.Conversa(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone="5511900000000",
        bot_ativo=(status != "handoff"),
        status=status,
        criada_em=quando,
        atualizada_em=quando,
    )


def test_resumo_conta_atendimentos_e_handoff(client, loja_a):
    loja_id = loja_a["loja_id"]
    dia = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add(_conversa(loja_id, "aberta", dia))
        db.add(_conversa(loja_id, "handoff", dia))
        db.add(_conversa(loja_id, "encerrada", dia))
        db.commit()

    r = client.get(
        "/v1/atendimento/resumo?desde=2026-08-01&ate=2026-09-01",
        headers=loja_a["headers"],
    )

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["atendimentos"] == 3
    assert corpo["transferidos"] == 1
    assert round(corpo["transferidos_pct"], 3) == round(1 / 3, 3)
    assert corpo["simulacoes"] is None
    assert {"data": "2026-08-05", "atendimentos": 3} in corpo["por_dia"]


def test_resumo_escopo_por_loja(client, loja_a, loja_b):
    dia = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add(_conversa(loja_a["loja_id"], "aberta", dia))
        db.add(_conversa(loja_b["loja_id"], "aberta", dia))
        db.commit()

    r = client.get(
        "/v1/atendimento/resumo?desde=2026-08-01&ate=2026-09-01",
        headers=loja_a["headers"],
    )

    assert r.json()["atendimentos"] == 1  # só a loja A
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api; .\.venv\Scripts\python.exe -m pytest tests/test_resumo_atendimento.py -q`
Expected: FAIL com 404 (rota inexistente).

- [ ] **Step 3: Implementar `servico.resumo_atendimento`**

Em `chatbot-api/app/servico.py`, adicionar `func` ao import do SQLAlchemy:

```python
from sqlalchemy import and_, or_, func
```

E a função (perto das outras funções de leitura de conversas):

```python
def resumo_atendimento(db, loja_id, desde, ate):
    """Agrega conversas da loja no intervalo [desde, ate). Sem inventar zeros:
    contagens reais; simulações reservado (None) enquanto o produto ajusta."""
    filtro = (
        Conversa.loja_id == loja_id,
        Conversa.criada_em >= desde,
        Conversa.criada_em < ate,
    )
    atendimentos = db.query(func.count(Conversa.id)).filter(*filtro).scalar() or 0
    transferidos = (
        db.query(func.count(Conversa.id))
        .filter(*filtro, Conversa.status == "handoff")
        .scalar()
        or 0
    )
    por_dia_rows = (
        db.query(func.date(Conversa.criada_em), func.count(Conversa.id))
        .filter(*filtro)
        .group_by(func.date(Conversa.criada_em))
        .order_by(func.date(Conversa.criada_em))
        .all()
    )
    por_dia = [
        {"data": str(dia), "atendimentos": int(qtd)} for dia, qtd in por_dia_rows
    ]
    pct = (transferidos / atendimentos) if atendimentos else None
    return {
        "atendimentos": int(atendimentos),
        "transferidos": int(transferidos),
        "transferidos_pct": pct,
        "por_dia": por_dia,
        "simulacoes": None,
    }
```

- [ ] **Step 4: Implementar o endpoint + helper de janela**

Em `chatbot-api/app/main.py`, perto do endpoint `/v1/funil/eventos` (linha ~811), adicionar:

```python
from datetime import datetime, timezone  # garantir import no topo do arquivo


def _janela_mes(desde: Optional[str], ate: Optional[str]) -> tuple[datetime, datetime]:
    """Converte ?desde/?ate (YYYY-MM-DD) em [inicio, fim). Sem parâmetros → mês corrente."""
    agora = datetime.now(timezone.utc)
    padrao_inicio = datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)
    padrao_fim = (
        datetime(agora.year + 1, 1, 1, tzinfo=timezone.utc)
        if agora.month == 12
        else datetime(agora.year, agora.month + 1, 1, tzinfo=timezone.utc)
    )
    try:
        inicio = (
            datetime.fromisoformat(desde).replace(tzinfo=timezone.utc)
            if desde
            else padrao_inicio
        )
    except ValueError:
        inicio = padrao_inicio
    try:
        fim = (
            datetime.fromisoformat(ate).replace(tzinfo=timezone.utc)
            if ate
            else padrao_fim
        )
    except ValueError:
        fim = padrao_fim
    return inicio, fim


@app.get("/v1/atendimento/resumo")
def resumo_atendimento(
    desde: Optional[str] = None,
    ate: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Resumo agregado do agente (bot) para a loja: atendimentos, handoff e série diária."""
    inicio, fim = _janela_mes(desde, ate)
    return servico.resumo_atendimento(db, ctx.loja_id, inicio, fim)
```

> Se `datetime`/`timezone` já estiverem importados no topo de `main.py`, não duplicar o import.

- [ ] **Step 5: Rodar e ver passar**

Run: `cd chatbot-api; .\.venv\Scripts\python.exe -m pytest tests/test_resumo_atendimento.py -q`
Expected: PASS (2 testes).

- [ ] **Step 6: Rodar a suíte do Chatbot inteira**

Run: `cd chatbot-api; .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (sem regressões).

- [ ] **Step 7: Commit**

```bash
git add chatbot-api/app/servico.py chatbot-api/app/main.py chatbot-api/tests/test_resumo_atendimento.py
git commit -m "feat(chatbot): endpoint /v1/atendimento/resumo (agregado do agente)"
```

---

## Task 5: Loja — página "Desempenho do agente" (Task 3 do produto)

**Files:**
- Modify: `portal-gestao/app/clients/chatbot.py`
- Modify: `portal-gestao/app/loja/navigation.py`
- Modify: `portal-gestao/app/loja/routes.py`
- Create: `portal-gestao/app/templates/loja/agente.html`
- Test: `portal-gestao/tests/test_loja_agente.py`

**Interfaces:**
- Consumes: `ChatbotClient.resumo_atendimento()` (novo), `get_chatbot_client`, `usuario_atual`, `contexto`, `templates`, `redirecionar_login`, `atendimento_habilitado`, `pode_usar_atendimento`.
- Produces:
  - `ChatbotClient.resumo_atendimento(desde=None, ate=None) -> dict`
  - rota `GET /app/loja/agente`
  - NavItem "Agente" (href `/app/loja/agente`) na seção Vendas.

- [ ] **Step 1: Adicionar método no client do Portal + teste**

Em `portal-gestao/app/clients/chatbot.py`, junto dos métodos de conversas, adicionar:

```python
    def resumo_atendimento(self, desde: str | None = None, ate: str | None = None) -> dict:
        params: dict[str, Any] = {}
        if desde:
            params["desde"] = desde
        if ate:
            params["ate"] = ate
        return self._request("GET", "/v1/atendimento/resumo", params=params)
```

- [ ] **Step 2: Escrever o teste da rota que falha**

Criar `portal-gestao/tests/test_loja_agente.py`:

```python
from __future__ import annotations

from conftest import login

from app.main import app, get_chatbot_client
from app.loja import routes as loja_routes  # noqa: F401  (garante registro das rotas)


class _FakeChatbot:
    def __init__(self, resumo=None, indisponivel=False):
        self._resumo = resumo
        self._indisponivel = indisponivel

    def resumo_atendimento(self, desde=None, ate=None):
        if self._indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel

            raise ChatbotIndisponivel("offline")
        return self._resumo


def _override(fake):
    app.dependency_overrides[get_chatbot_client] = lambda: fake


def teardown_function():
    app.dependency_overrides.pop(get_chatbot_client, None)


def test_agente_flag_off_404(client):
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 404


def test_agente_mostra_cards(client, atendimento_on):
    _override(
        _FakeChatbot(
            resumo={
                "atendimentos": 65,
                "transferidos": 38,
                "transferidos_pct": 0.58,
                "por_dia": [{"data": "2026-08-05", "atendimentos": 12}],
                "simulacoes": None,
            }
        )
    )
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "Agente de atendimento" in r.text
    assert "65" in r.text
    assert "Transferidos" in r.text
    assert "em construção" in r.text  # card de simulações placeholder


def test_agente_degrada_quando_chatbot_offline(client, atendimento_on):
    _override(_FakeChatbot(indisponivel=True))
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "indisponível" in r.text.lower()
```

> `atendimento_on` é a fixture que liga `revy_loja_atendimento_enabled` (definida em `tests/test_atendimento.py`); movê-la para `conftest.py` **ou** replicar a fixture no topo deste arquivo, copiando o corpo:
>
> ```python
> import pytest
> from dataclasses import replace
> from app.config import settings as portal_settings
>
> @pytest.fixture
> def atendimento_on(monkeypatch):
>     enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
>     monkeypatch.setattr("app.config.settings", enabled)
>     monkeypatch.setattr("app.main.settings", enabled)
>     monkeypatch.setattr("app.loja.routes.settings", enabled)
>     yield
> ```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_loja_agente.py -q`
Expected: FAIL com 404 em todas (rota inexistente).

- [ ] **Step 4: Criar o template**

Criar `portal-gestao/app/templates/loja/agente.html`:

```html
{% extends "base.html" %}
{% block title %}Agente de atendimento — Revy Loja{% endblock %}
{% block content %}
<div class="page-heading">
  <div>
    <span class="eyebrow">Atendimento</span>
    <h1>Agente de atendimento</h1>
    <p>Desempenho do bot automático no mês corrente.</p>
  </div>
</div>

{% if erro_resumo == 'indisponivel' or resumo is none %}
<section class="panel">
  <p class="muted">Métricas do agente indisponíveis no momento. Tente novamente em instantes.</p>
</section>
{% else %}
<section class="funil-summary" aria-label="Indicadores do agente">
  <div class="funil-summary-card highlight">
    <span>Atendimentos</span>
    <strong>{{ resumo.atendimentos }}</strong>
    <small>no mês</small>
  </div>
  <div class="funil-summary-card">
    <span>Transferidos</span>
    <strong>{{ resumo.transferidos }}</strong>
    <small>
      {% if resumo.transferidos_pct is not none %}{{ (resumo.transferidos_pct * 100) | round(0) | int }}% dos atendimentos{% else %}—{% endif %}
    </small>
  </div>
  <div class="funil-summary-card">
    <span>Simulações</span>
    <strong class="muted">em construção</strong>
    <small>em breve</small>
  </div>
</section>

<section class="panel" id="agente-por-dia">
  <div class="panel-heading"><h2>Atendimentos por dia</h2></div>
  {% if resumo.por_dia %}
  {% set maximo = resumo.por_dia | map(attribute='atendimentos') | max %}
  <div style="display:flex;align-items:flex-end;gap:6px;height:160px;padding:8px 4px;overflow-x:auto">
    {% for d in resumo.por_dia %}
    <div style="display:flex;flex-direction:column;align-items:center;gap:4px;min-width:28px">
      <div title="{{ d.atendimentos }}"
           style="width:20px;border-radius:4px 4px 0 0;background:var(--brand,#1f6feb);
                  height:{{ ((d.atendimentos / maximo) * 130) | round(0) | int if maximo else 0 }}px"></div>
      <small class="muted" style="font-size:10px">{{ d.data[8:10] }}</small>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <p class="muted">Sem atendimentos no período.</p>
  {% endif %}
</section>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Adicionar a rota**

Em `portal-gestao/app/loja/routes.py`, após a função `atendimento_lista` (perto da linha 227, antes da rota `/{workspace_id}`), adicionar:

```python
@router.get("/app/loja/agente", response_class=HTMLResponse)
def agente_desempenho(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not atendimento_habilitado():
        return _flag_off_response(request, usuario)
    if not pode_usar_atendimento(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Sem permissão para o Atendimento."),
            status_code=403,
        )
    resumo = None
    erro_resumo = None
    try:
        resumo = chatbot.resumo_atendimento()
    except ChatbotIndisponivel:
        erro_resumo = "indisponivel"
    return templates.TemplateResponse(
        "loja/agente.html",
        contexto(request, usuario, resumo=resumo, erro_resumo=erro_resumo),
    )
```

- [ ] **Step 6: Adicionar o item de nav "Agente"**

Em `portal-gestao/app/loja/navigation.py`, dentro da seção Vendas (após o `NavItem` "Atendimento", linha ~62), adicionar:

```python
                    NavItem(
                        label="Agente",
                        href="/app/loja/agente",
                        section="Vendas",
                        module=Module.VENDAS.value,
                        active_prefix="/app/loja/agente",
                    ),
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_loja_agente.py -q`
Expected: PASS (3 testes).

- [ ] **Step 8: Rodar a suíte do Portal inteira**

Run: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (sem regressões; conferir `tests/test_loja_navigation.py` — se ele fixa a contagem de itens da nav, atualizar a expectativa para incluir "Agente").

- [ ] **Step 9: Commit**

```bash
git add portal-gestao/app/clients/chatbot.py portal-gestao/app/loja/navigation.py portal-gestao/app/loja/routes.py portal-gestao/app/templates/loja/agente.html portal-gestao/tests/test_loja_agente.py
git commit -m "feat(loja): página Desempenho do agente (atendimentos, handoff, por dia)"
```

---

## Verificação final (após todas as tasks)

- [ ] `cd revy-trafego; .\.venv\Scripts\python.exe -m pytest -q` → verde
- [ ] `cd chatbot-api; .\.venv\Scripts\python.exe -m pytest -q` → verde
- [ ] `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q` → verde
- [ ] `git diff --check` e `git status --short` limpos (preservar mudanças alheias)

## Self-review (feito ao escrever o plano)

- **Cobertura do spec:** Task 2 (filtro) → Task 1 do plano; Task 1 (Visão Geral) → Tasks 2–3; Task 3 (agente) → Tasks 4–5. Metas fora de escopo (não há task) ✓. Degradação sem zero inventado coberta em testes (leads e chatbot offline) ✓.
- **Placeholders:** nenhum "TBD/implementar depois"; o card "em construção" de simulações é requisito explícito do dono, não placeholder de plano.
- **Consistência de tipos:** `network_overview(actor, leads_port=...)`, `_LeadsCountPort.count_for_store(slug) -> int | None`, `_ChatbotLeadsPort.count_for_store` casam. `resumo_atendimento(db, loja_id, desde, ate) -> dict` (servico) e `ChatbotClient.resumo_atendimento(desde, ate) -> dict` (client) casam com o endpoint.
