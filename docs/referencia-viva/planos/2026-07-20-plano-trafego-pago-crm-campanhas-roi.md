# Plano — Tráfego pago no CRM (Campanhas, Atribuição e ROI)

> **FRONTEIRA FUTURA:** este documento descreve o MVP entregue no Portal. Para novo
> desenvolvimento, Registros de Campanha, integrações e ROI técnico pertencem ao
> [Revy Control](2026-07-29-plano-revy-control.md); a Loja recebe resumo comercial.

> **Status 2026-07-20: DONE (MVP entregue em `main`, commit `8e7ec5f`).**
> Não reimplementar T1–T9. Este doc vira **referência de desenho** + residual abaixo.
> **Não** executar os checkboxes `- [ ]` — ficam só como histórico do plano original.

**Status:** **DONE (MVP)** — eixo **C · CRM dono**
**Entregou:** `#3B` Task 5 + **E8** (ROI); complementa **E10** (já feito); **não** implementou E9.
**Código:** Portal `campanhas` + `roi_calc` + `/app/campanhas` + `/app/trafego/roi`; Chatbot first/last + fbclid/gclid; Catálogo ViewContent + propaga click ids. Guia loja: `docs/nao-plano/tutoriais/trafego-pago-loja.md`.
**Residual (não bloqueia DONE):** match CAPI com phone/fbclid mais completo; reconciliação E2E Ads; import CSV de gastos em volume.

**Substitui / detalha:** `#3B` Task 5 + **E8** (ROI); complementa **E10** (já feito); **não** implementa E9 (redes/social suite) nem criação de anúncios na Meta/Google.
**Depende de:** Portal com vendas confirmadas (feito), leads com UTM via catálogo→chatbot (feito), E10 Pixel/CAPI (feito).

**Goal:** O dono/gerente cadastra campanhas de tráfego pago com custo e UTM, o CRM amarra leads/vendas a essas campanhas (first/last touch explícitos) e o dashboard responde “quanto gastei → quantos leads → quantas vendas → ROAS / CPL / CPA” sem abrir o Ads Manager.

**Architecture:** Portal é dono de `campanhas`, gastos e relatório ROI. Chatbot continua dono de leads/UTMs/cliques (enriquece first/last touch + click ids). Catálogo só propaga query params e eventos de browser. Matching é **declarado** por UTM (e opcionalmente por `campanha_id` manual), nunca “magia” de API da Meta no MVP. Integração entre produtos só HTTP.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, Jinja2 (Portal), pytest, httpx; Catálogo templates + Pixel browser existente; Chatbot leads/atribuição catálogo existentes.

---

## Global Constraints

- **Multi-loja:** todo registro de campanha/gasto/venda filtrado por `loja_slug` (Portal) ou `loja_id` (Chatbot). Nunca cruzar lojas.
- **RBAC:** dono/gerente criam campanhas, lançam custo e veem ROI; vendedor **vê** origem/campanha no lead e no dashboard dele, **não** edita token CAPI nem custo de mídia.
- **Sem Ad Manager embutido:** não criar/pausar anúncios na Meta/Google. Custo é **digitado ou CSV simples**.
- **Atribuição honesta:** exibir `first_touch` e `last_touch` com rótulos; **não** prometer causalidade multi-touch.
- **UTM match key primária:** `utm_campaign` (casefold, strip) + `loja`. `utm_source`/`utm_medium` são auxiliares de exibição e filtro, não obrigatórios no match se `utm_campaign` bater com campanha cadastrada.
- **Lead sem UTM:** conta em “sem campanha / orgânico / desconhecido” — nunca inventar campanha.
- **Venda sem lead:** ROI de campanha só conta vendas com `lead_ref` resolvível **ou** `campanha_id_*` snapshot na venda.
- **Money:** `Decimal` + quantize centavos (mesmo padrão de `financeiro_calc.py`); nunca float em agregações.
- **Segredos:** token CAPI continua só em E10; este plano não grava token de Ads.
- **E9 fora:** zero social planner / publicar post / gerir criativo.
- **TDD:** cada task começa com teste que falha; commit pequeno ao final da task.
- **Contratos HTTP versionados:** Chatbot expõe campos novos em JSON de lead sem quebrar clientes; Portal consome e não lê Postgres do Chatbot.
- **Idioma UI:** português BR, labels claros (CPL, CPA, ROAS com tooltip de uma linha).
- **Não misturar** disparo WA em massa (E11) neste plano — campanha aqui é **entidade de marketing/métrica**.

---

## Contexto do que já existe (não reimplementar)

| Peça | Onde | Estado |
|---|---|---|
| Lead com `origem`, `canal`, `utm_*` | `chatbot-api/app/models_db.py` `Lead` | Feito |
| Atribuição catálogo → lead | `chatbot-api` + outbox catálogo | Feito |
| Pixel PageView + Lead + ViewContent + `event_id` | `catalogo-publico` | Feito |
| CAPI Purchase na venda | `portal-gestao/app/meta_capi.py` + `/app/trafego` | Feito (MVP) |
| Filtro funil por `origem` / campanha | `portal-gestao/app/financeiro_calc.py` | Feito |
| Exibe `utm_campaign` no card do vendedor | `templates/vendedor/dashboard.html` | Feito |
| Tabela `campanhas` + gastos | Portal models + migration `0006` | **Feito** |
| First/last touch separados | Chatbot migration `0006` | **Feito** |
| `fbclid` / `gclid` | Chatbot + catálogo CTA | **Feito** |
| Dashboard ROI (CPL/CPA/ROAS) | `/app/trafego/roi` + `roi_calc.py` | **Feito** |

---

## Glossário (para implementador e dono)

| Termo | Definição no produto |
|---|---|
| **Campanha** | Registro no Portal: nome, canal, UTM, período, custo. Espelha mentalmente uma campanha do Ads, mas **não** sincroniza API. |
| **First touch** | Primeira origem/UTM gravada no lead (não sobrescrever). |
| **Last touch** | Última origem/UTM observada (ex.: novo clique no catálogo). |
| **CPL** | `gasto_no_período / leads_atribuídos` (se leads=0 → “—”). |
| **CPA** | `gasto_no_período / vendas_confirmadas_atribuídas`. |
| **ROAS** | `faturamento_vendas_atribuídas / gasto_no_período` (gasto=0 → “—”). |
| **Match** | Lead entra na campanha se `utm_campaign` (first ou last, conforme modo) casefold-igual ao da campanha **da mesma loja**, ou se `campanha_id` manual. |

---

## Mapa de arquivos

### Portal (`portal-gestao/`)

| Arquivo | Responsabilidade |
|---|---|
| `app/models.py` | Models `Campanha`, `CampanhaGasto` (opcional fase 1 unificada), campos snapshot em `Venda` |
| `alembic/versions/0006_campanhas_roi.py` | Migration |
| `app/campanhas.py` | CRUD helpers, match UTM, validação |
| `app/roi_calc.py` | Agregações CPL/CPA/ROAS (puro, testável) |
| `app/main.py` | Rotas `/app/campanhas`, `/app/trafego/roi`, filtros |
| `app/financeiro_calc.py` | Filtro lead por campanha / utm_campaign |
| `app/relatorios.py` | CSV ROI opcional |
| `app/clients/chatbot.py` | (sem mudança obrigatória se lead JSON já vier completo) |
| `app/templates/campanhas/*.html` | Lista, form, detalhe |
| `app/templates/trafego/roi.html` | Dashboard ROI |
| `app/templates/trafego/form.html` | Link “Ver ROI / Campanhas” |
| `app/templates/base.html` | Nav: Campanhas sob Tráfego |
| `app/templates/leads/detalhe.html` | Bloco origem first/last |
| `app/templates/financeiro/dashboard.html` | Filtro campanha |
| `tests/test_campanhas.py` | CRUD + match + RBAC |
| `tests/test_roi.py` | Métricas |
| `tests/conftest.py` | Fixtures leads com UTM |

### Chatbot (`chatbot-api/`)

| Arquivo | Responsabilidade |
|---|---|
| `app/models_db.py` | first/last UTM, `fbclid`, `gclid`, `click_id` |
| `alembic/versions/0006_lead_touch_click_ids.py` | Migration (número real = head+1) |
| `app/servico.py` ou módulo de atribuição catálogo | First-write first_*, update last_* |
| `app/main.py` | Serialização lead API |
| `tests/test_catalog_attribution.py` | First/last + click ids |

### Catálogo (`catalogo-publico/`)

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` / templates | Propagar `fbclid`, `gclid`, UTMs no CTA e outbox |
| `app/contracts.py` / events | Campos no evento de interesse |
| `tests/test_pages.py` | Query string preservada |

### Docs

| Arquivo | Responsabilidade |
|---|---|
| `docs/nao-plano/historico/README.md` | Entrada no índice |
| `docs/referencia-viva/contexto-compacto.md` | Checkpoint eixo C |
| `docs/nao-plano/tutoriais/trafego-pago-loja.md` | Guia operacional do dono (UTM + custo + Pixel) |
| `docs/plans/2026-07-11-plano3b-….md` | Marcar Task 5 como detalhada por este plano |
| `docs/plans/2026-07-11-plano6-….md` | Marcar E8 detalhada por este plano |

---

## Modelo de dados (alvo)

### Portal — `campanhas`

```text
id                str UUID PK
loja_slug         str index
nome              str(160)          # "Seminovos Meta Julho"
canal             str(32)           # meta | google | indicacao | organico | outro
status            str(20)           # ativa | pausada | encerrada
utm_source        str(120) null
utm_medium        str(120) null
utm_campaign      str(120) NOT NULL # chave de match (obrigatória se canal pago)
utm_content       str(120) null     # opcional, match secundário se preenchido nos dois lados
utm_term          str(120) null
periodo_inicio    date null
periodo_fim       date null
notas             str(500) null
criada_em         datetime
atualizada_em     datetime
criada_por_email  str(320)
```

Índice único parcial lógico: **`(loja_slug, lower(utm_campaign))` único entre status != encerrada** — ou único absoluto e forçar rename. **Decisão MVP:** unique `(loja_slug, utm_campaign_norm)` onde `utm_campaign_norm` é coluna gerada/persistida lower(strip).

### Portal — `campanha_gastos`

Permite vários lançamentos (semanal) sem reescrever histórico.

```text
id             str UUID PK
campanha_id    FK campanhas.id
loja_slug      str index          # denormalizado p/ tenancy
valor          Numeric(12,2)      # >= 0
referencia     date               # dia de referência do gasto (ou 1º dia da semana)
nota           str(240) null      # "semana 1 Ads Manager"
criada_em      datetime
criada_por     str(320)
```

**Gasto no período do relatório** = soma de `campanha_gastos` com `referencia` em `[d_inicio, d_fim]`.
Se a campanha não tiver gastos no range, gasto = 0 (mostrar aviso “sem custo lançado”).

### Portal — `vendas` (colunas novas, nullable)

```text
campanha_id_first  str(36) null  # snapshot no confirmar
campanha_id_last   str(36) null
utm_campaign_first str(120) null # fallback se campanha apagada
utm_campaign_last  str(120) null
```

Preenchidas **somente ao confirmar venda**, a partir do lead do Chatbot + match de campanhas da loja. Não recalcular em massa sem job explícito (YAGNI).

### Chatbot — `leads` (colunas novas)

```text
# First touch (gravar só se null)
utm_source_first, utm_medium_first, utm_campaign_first, utm_content_first, utm_term_first
origem_first, canal_first

# Last touch (sempre atualizar em nova atribuição de catálogo)
utm_source_last, ... (espelho)
origem_last, canal_last

# Click ids (último visto; first opcional se null)
fbclid  str(255) null
gclid   str(255) null

# Manter utm_* atuais como ALIAS de last touch na API (compat) OU
# documentar migração: utm_* = first (legado) e popular first_* = utm_* na migration.
```

**Decisão de migração (obrigatória na Task 2):**

1. Migration cria `*_first` e `*_last`.
2. Backfill: `*_first = utm_*` e `*_last = utm_*` onde `utm_*` not null.
3. API de lead passa a devolver **ambos** + `utm_*` espelhando **last** (compat com Portal que já lê `utm_campaign`).
4. Código de atribuição: se first vazio → preenche first; **sempre** atualiza last.

---

## Regras de matching (canônicas)

```python
def normalizar_utm(valor: str | None) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip().casefold()
    return s or None

def lead_casa_campanha(lead: dict, campanha, *, modo: str) -> bool:
    """modo: 'first' | 'last'."""
    assert modo in ("first", "last")
    if modo == "first":
        camp_key = normalizar_utm(lead.get("utm_campaign_first") or lead.get("utm_campaign"))
        content_key = normalizar_utm(lead.get("utm_content_first") or lead.get("utm_content"))
    else:
        camp_key = normalizar_utm(lead.get("utm_campaign_last") or lead.get("utm_campaign"))
        content_key = normalizar_utm(lead.get("utm_content_last") or lead.get("utm_content"))
    if not camp_key:
        return False
    if camp_key != normalizar_utm(campanha.utm_campaign):
        return False
    # Match secundário só se a campanha definiu utm_content
    if campanha.utm_content:
        if content_key != normalizar_utm(campanha.utm_content):
            return False
    return True
```

Período do relatório filtra leads por `criada_em` (ou `atribuida_em` se presente) e vendas por data de confirmação/`criada_em` já usada em `calcular_metricas_vendas` — **manter a mesma regra de data de vendas do financeiro** para não divergir números.

---

## UX — navegação

- Menu Portal (dono/gerente): **Tráfego** continua Pixel; ao lado ou subnav:
  - Config Pixel (existente `/app/trafego`)
  - **Campanhas** `/app/campanhas`
  - **ROI** `/app/trafego/roi`
- Vendedor: sem menu Campanhas/ROI; no detalhe do lead vê “Campanha: seminovos-julho (Meta)”.

---

## Fora de escopo (explícito)

- OAuth Meta Marketing API / Google Ads API
- Import automático diário de gasto
- Criação de anúncio, criativo, público
- TikTok / LinkedIn
- Multi-touch fractional attribution
- Lead scoring por anúncio
- E11/E12 envio
- Alterar algoritmo CAPI Purchase (já existe)

---

## Ordem das tasks

```text
T1 Modelo campanhas + gastos (Portal)
T2 CRUD campanhas UI + RBAC
T3 First/last touch + click ids (Chatbot)
T4 Propagar click ids/UTM no Catálogo
T5 Snapshot campanha na confirmação de venda
T6 roi_calc + dashboard ROI
T7 Filtros financeiro/leads por campanha + CSV
T8 Eventos Pixel extras (ViewContent) — opcional polish
T9 Guia loja + docs de índice
```

Cada task entrega software testável sozinha.

---

### Task 1: Modelo `Campanha` + `CampanhaGasto` + migration

**Files:**
- Create: `portal-gestao/alembic/versions/0006_campanhas_roi.py`
- Modify: `portal-gestao/app/models.py`
- Create: `portal-gestao/app/campanhas.py` (funções puras de normalização + validação)
- Test: `portal-gestao/tests/test_campanhas_model.py`

**Interfaces:**
- Produces: models `Campanha`, `CampanhaGasto`; `normalizar_utm(str|None) -> str|None`; `validar_campanha_payload(dict) -> list[str]` (erros)

- [ ] **Step 1: Write the failing test**

```python
# portal-gestao/tests/test_campanhas_model.py
from decimal import Decimal
from datetime import date

from app.campanhas import normalizar_utm, validar_campanha_payload
from app.models import Campanha, CampanhaGasto, novo_id


def test_normalizar_utm_strip_casefold():
    assert normalizar_utm("  Seminovos-Julho ") == "seminovos-julho"
    assert normalizar_utm("") is None
    assert normalizar_utm(None) is None


def test_validar_exige_utm_campaign_para_meta():
    erros = validar_campanha_payload({
        "nome": "Meta jul",
        "canal": "meta",
        "utm_campaign": "",
    })
    assert any("utm_campaign" in e for e in erros)


def test_persistir_campanha_e_gasto(db_session):
    # usar SessionLocal do conftest se existir fixture; senão criar inline
    c = Campanha(
        id=novo_id(),
        loja_slug="loja-teste",
        nome="Seminovos Meta",
        canal="meta",
        status="ativa",
        utm_campaign="seminovos-julho",
        utm_campaign_norm="seminovos-julho",
        criada_por_email="dono@loja.test",
    )
    db_session.add(c)
    db_session.add(CampanhaGasto(
        id=novo_id(),
        campanha_id=c.id,
        loja_slug="loja-teste",
        valor=Decimal("500.00"),
        referencia=date(2026, 7, 1),
        criada_por="dono@loja.test",
    ))
    db_session.commit()
    assert db_session.query(Campanha).count() == 1
    assert db_session.query(CampanhaGasto).one().valor == Decimal("500.00")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd portal-gestao
.\.venv\Scripts\python.exe -m pytest tests/test_campanhas_model.py -v
```

Expected: FAIL (module/models missing)

- [ ] **Step 3: Implement models + helpers**

Em `models.py`, adicionar:

```python
class Campanha(Base):
    __tablename__ = "campanhas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    nome: Mapped[str] = mapped_column(String(160))
    canal: Mapped[str] = mapped_column(String(32), default="meta")
    status: Mapped[str] = mapped_column(String(20), default="ativa", index=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str] = mapped_column(String(120))
    utm_campaign_norm: Mapped[str] = mapped_column(String(120), index=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    periodo_inicio: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    periodo_fim: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notas: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por_email: Mapped[str] = mapped_column(String(320))

    gastos: Mapped[list["CampanhaGasto"]] = relationship(
        back_populates="campanha", cascade="all, delete-orphan"
    )


class CampanhaGasto(Base):
    __tablename__ = "campanha_gastos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    campanha_id: Mapped[str] = mapped_column(ForeignKey("campanhas.id"), index=True)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    referencia: Mapped[date] = mapped_column(Date, index=True)
    nota: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por: Mapped[str] = mapped_column(String(320))

    campanha: Mapped["Campanha"] = relationship(back_populates="gastos")
```

Em `campanhas.py`:

```python
from __future__ import annotations

CANAIS = frozenset({"meta", "google", "indicacao", "organico", "outro"})
STATUS = frozenset({"ativa", "pausada", "encerrada"})
CANAIS_PAGOS = frozenset({"meta", "google"})


def normalizar_utm(valor: str | None) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip().casefold()
    return s or None


def validar_campanha_payload(dados: dict) -> list[str]:
    erros: list[str] = []
    nome = (dados.get("nome") or "").strip()
    if not nome:
        erros.append("nome é obrigatório")
    canal = (dados.get("canal") or "").strip().casefold()
    if canal not in CANAIS:
        erros.append("canal inválido")
    status = (dados.get("status") or "ativa").strip().casefold()
    if status not in STATUS:
        erros.append("status inválido")
    utm_c = normalizar_utm(dados.get("utm_campaign"))
    if canal in CANAIS_PAGOS and not utm_c:
        erros.append("utm_campaign é obrigatório para canal pago (meta/google)")
    if not utm_c and canal not in {"organico", "indicacao"}:
        # organico/indicacao podem não ter UTM
        if canal not in CANAIS:
            pass
        elif canal not in {"organico", "indicacao"}:
            erros.append("utm_campaign é obrigatório")
    # organico/indicacao: utm opcional
    if canal in CANAIS_PAGOS and not utm_c:
        pass  # já coberto
    return erros
```

Ajuste fino: para `organico`/`indicacao`, `utm_campaign` pode ser gerado como `organico` / `indicacao-{slug}` se vazio — **preferir exigir utm_campaign sempre** para match simples, inclusive orgânico (`utm_campaign=organico`). **Decisão final MVP:** `utm_campaign` **sempre obrigatório** (simplifica unique + match).

Atualizar `validar_campanha_payload` para: **sempre** exigir `utm_campaign` não vazio.

Migration Alembic: criar tabelas + UniqueConstraint `uq_campanha_loja_utm_norm` em `(loja_slug, utm_campaign_norm)`.

- [ ] **Step 4: Run tests**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_campanhas_model.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/models.py portal-gestao/app/campanhas.py portal-gestao/alembic/versions/0006_campanhas_roi.py portal-gestao/tests/test_campanhas_model.py
git commit -m "feat(portal): modelo campanhas e gastos para ROI de tráfego"
```

---

### Task 2: CRUD Campanhas + lançar gasto (UI + rotas)

**Files:**
- Modify: `portal-gestao/app/main.py`
- Create: `portal-gestao/app/templates/campanhas/lista.html`
- Create: `portal-gestao/app/templates/campanhas/form.html`
- Create: `portal-gestao/app/templates/campanhas/detalhe.html`
- Modify: `portal-gestao/app/templates/base.html` (nav)
- Test: `portal-gestao/tests/test_campanhas.py`

**Interfaces:**
- Consumes: `Campanha`, `CampanhaGasto`, `validar_campanha_payload`, `normalizar_utm`
- Produces: rotas
  - `GET /app/campanhas`
  - `GET|POST /app/campanhas/nova`
  - `GET|POST /app/campanhas/{id}`
  - `POST /app/campanhas/{id}/gastos`
  - `POST /app/campanhas/{id}/status` (ativa|pausada|encerrada)

- [ ] **Step 1: Failing tests**

```python
# portal-gestao/tests/test_campanhas.py
def test_vendedor_nao_acessa_campanhas(client):
    # login como vendedor (mesmo padrão de test_trafego / test_funil)
    r = client.get("/app/campanhas", follow_redirects=False)
    assert r.status_code in (302, 403)


def test_dono_cria_campanha_e_lista(client_dono):
    r = client_dono.post("/app/campanhas/nova", data={
        "csrf": "x",
        "nome": "Seminovos Meta",
        "canal": "meta",
        "utm_source": "instagram",
        "utm_medium": "paid",
        "utm_campaign": "seminovos-julho",
        "status": "ativa",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    lista = client_dono.get("/app/campanhas")
    assert lista.status_code == 200
    assert "Seminovos Meta" in lista.text
    assert "seminovos-julho" in lista.text


def test_utm_campaign_duplicado_mesma_loja_rejeita(client_dono):
    payload = {
        "csrf": "x", "nome": "A", "canal": "meta",
        "utm_campaign": "dup-1", "status": "ativa",
    }
    assert client_dono.post("/app/campanhas/nova", data=payload).status_code in (200, 302, 303)
    r2 = client_dono.post("/app/campanhas/nova", data={**payload, "nome": "B"})
    assert r2.status_code == 200  # form com erro
    assert "já existe" in r2.text.casefold() or "utm" in r2.text.casefold()


def test_lancar_gasto(client_dono, campanha_id):
    r = client_dono.post(f"/app/campanhas/{campanha_id}/gastos", data={
        "csrf": "x",
        "valor": "350,50",  # aceitar BR
        "referencia": "2026-07-10",
        "nota": "semana 2",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "350" in r.text
```

Reutilizar helpers de login dos testes existentes (`test_trafego.py`, `test_funil.py`). Se não houver `client_dono`, copiar padrão de cookie de sessão.

- [ ] **Step 2: Run — expect FAIL**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_campanhas.py -v
```

- [ ] **Step 3: Implement routes**

Padrão igual a `/app/metas` e `/app/trafego`:

- Decorator/papel: só `dono` e `gerente` (mesmo helper que protege tráfego).
- Parse valor BR: reutilizar função existente de dinheiro se houver (`dinheiro` em main/financeiro); senão:

```python
def parse_brl(texto: str) -> Decimal | None:
    t = (texto or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        v = Decimal(t)
    except Exception:
        return None
    if v < 0:
        return None
    return v.quantize(Decimal("0.01"))
```

- Ao salvar: `utm_campaign_norm = normalizar_utm(utm_campaign)`.
- Detalhe mostra tabela de gastos + total.

Templates: copiar estrutura visual de `metas/lista.html` + `form.html` (eyebrow, panel, form-grid).

Nav em `base.html` (bloco dono/gerente): link **Campanhas** → `/app/campanhas`.

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(portal): CRUD de campanhas e lançamento de custos de mídia"
```

---

### Task 3: First/last touch + click ids no Chatbot

**Files:**
- Modify: `chatbot-api/app/models_db.py`
- Create: `chatbot-api/alembic/versions/0006_lead_attribution_touch.py` (ajustar número se head ≠ 0005)
- Modify: módulo que aplica atribuição de catálogo (grep `utm_campaign` / `atribuida_em` em `app/`)
- Modify: serialização do lead em `app/main.py` ou `servico.py`
- Test: `chatbot-api/tests/test_catalog_attribution.py` (estender)

**Interfaces:**
- Produces: lead JSON com:

```json
{
  "utm_campaign": "feirao",
  "utm_campaign_first": "feirao",
  "utm_campaign_last": "feirao-2",
  "utm_source_first": "instagram",
  "utm_source_last": "google",
  "fbclid": "...",
  "gclid": null,
  "origem_first": "catalogo_publico",
  "origem_last": "catalogo_publico"
}
```

`utm_*` legados = **last touch** (compat Portal atual).

- [ ] **Step 1: Failing tests**

```python
def test_primeira_atribuicao_preenche_first_e_last(client, loja_a):
    # post interesse/atribuição existente no teste
    ...
    lead = ...
    assert lead["utm_campaign_first"] == "feirao"
    assert lead["utm_campaign_last"] == "feirao"
    assert lead["utm_campaign"] == "feirao"  # alias last


def test_segunda_atribuicao_preserva_first_atualiza_last(client, loja_a):
    # 1ª: utm_campaign=feirao
    # 2ª: utm_campaign=feirao-blackfriday (mesmo telefone / fluxo de correlação)
    lead = ...
    assert lead["utm_campaign_first"] == "feirao"
    assert lead["utm_campaign_last"] == "feirao-blackfriday"
    assert lead["utm_campaign"] == "feirao-blackfriday"


def test_fbclid_gravado(client, loja_a):
    ...
    assert lead["fbclid"] == "IwAR0test"
```

- [ ] **Step 2: Run FAIL**

```bash
cd chatbot-api
.\.venv\Scripts\python.exe -m pytest tests/test_catalog_attribution.py -v
```

- [ ] **Step 3: Migration + lógica**

```python
def aplicar_touch_utm(lead: Lead, dados: dict) -> None:
    """dados: utm_*, origem, canal, fbclid, gclid."""
    def _set_first(attr_base: str, valor: str | None):
        if not valor:
            return
        first_attr = f"{attr_base}_first" if attr_base != "origem" and attr_base != "canal" else f"{attr_base}_first"
        # mapear nomes
        ...

    # Pseudológica clara:
    # for field in utm_source, utm_medium, utm_campaign, utm_content, utm_term, origem, canal:
    #   val = clean(dados.get(field))
    #   if val:
    #     if getattr(lead, f"{field}_first") is None: setattr first
    #     setattr last
    #     setattr lead.utm_* legado = last (para utm_*)
    # fbclid/gclid: se val: set last; if first null set (opcional só last no MVP)
```

Implementação real: preferir função única em `servico.py` ou onde já grava atribuição hoje — **não** duplicar em n8n.

Backfill SQL na migration:

```sql
UPDATE leads SET
  utm_campaign_first = utm_campaign,
  utm_campaign_last = utm_campaign,
  ...
WHERE utm_campaign IS NOT NULL;
```

- [ ] **Step 4: PASS + commit**

```bash
git commit -m "feat(chatbot): first/last touch e click ids nos leads"
```

---

### Task 4: Catálogo propaga `fbclid` / `gclid` + UTMs

**Files:**
- Modify: `catalogo-publico/app/main.py` (tracking dict no detalhe e interesse)
- Modify: `catalogo-publico/app/contracts.py` / `events.py` se o payload outbox for tipado
- Modify: templates CTA WhatsApp se montarem query string manualmente
- Test: `catalogo-publico/tests/test_pages.py`

- [ ] **Step 1: Test**

```python
def test_detalhe_propaga_fbclid_no_cta(client, monkeypatch):
    r = client.get(
        "/l/moto-center/veiculos/vehicle-1"
        "?utm_source=meta&utm_campaign=ofertas&fbclid=IwAR0abc"
    )
    assert r.status_code == 200
    assert "fbclid=IwAR0abc" in r.text
    assert "utm_campaign=ofertas" in r.text


def test_interesse_inclui_fbclid_no_evento(client, ...):
    # se houver captura do outbox/evento
    ...
```

- [ ] **Step 2–4:** Estender lista de keys tracking:

```python
TRACKING_KEYS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid",
)
```

Limpar com o mesmo `clean_tracking` (tamanho máx. ~255 para click ids). Encaminhar no outbox para o Chatbot (contrato de atribuição já existente — estender campos opcionais).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(catalogo): propaga fbclid/gclid e UTMs no funil de interesse"
```

**Nota:** Chatbot endpoint de atribuição deve aceitar os novos campos opcionais (Task 3) — se o payload for rígido, alargar schema na mesma task ou na 3.

---

### Task 5: Snapshot de campanha ao confirmar venda

**Files:**
- Modify: `portal-gestao/app/models.py` (`Venda` +4 colunas)
- Modify: migration `0006` ou `0007_venda_campanha_snapshot.py`
- Modify: `portal-gestao/app/main.py` (handler confirmar venda)
- Modify: `portal-gestao/app/campanhas.py` — `resolver_campanhas_do_lead(db, loja, lead) -> tuple[Campanha|None, Campanha|None]`
- Test: `portal-gestao/tests/test_venda_campanha_snapshot.py`

**Interfaces:**
- Consumes: lead dict do Chatbot; campanhas da loja
- Produces: `venda.campanha_id_first/last`, `utm_campaign_first/last` no confirm

- [ ] **Step 1: Test**

```python
def test_confirmar_venda_grava_snapshot_first_last(client_dono, db, chatbot_fake):
    # campanha utm_campaign=seminovos-julho
    # lead l1 já no ChatbotFake com utm
    # cria venda com lead_ref=l1, confirma
    venda = db.query(Venda).filter(Venda.status == "confirmada").one()
    assert venda.utm_campaign_first == "seminovos-julho" or venda.utm_campaign_last
    assert venda.campanha_id_last is not None
```

- [ ] **Step 2: Implement**

No fluxo de confirmação (onde já chama CAPI Purchase):

```python
lead = chatbot.obter_lead(venda.lead_ref) if venda.lead_ref else None
if lead:
    first_c, last_c = resolver_campanhas_do_lead(db, usuario.loja_slug, lead)
    venda.campanha_id_first = first_c.id if first_c else None
    venda.campanha_id_last = last_c.id if last_c else None
    venda.utm_campaign_first = (
        lead.get("utm_campaign_first") or lead.get("utm_campaign")
    )
    venda.utm_campaign_last = (
        lead.get("utm_campaign_last") or lead.get("utm_campaign")
    )
```

`resolver_campanhas_do_lead`: carrega campanhas `status in (ativa, pausada, encerrada)` da loja e aplica `lead_casa_campanha` first/last.

- [ ] **Step 3–5:** PASS + commit

```bash
git commit -m "feat(portal): snapshot de campanha na confirmação da venda"
```

---

### Task 6: `roi_calc` + dashboard `/app/trafego/roi`

**Files:**
- Create: `portal-gestao/app/roi_calc.py`
- Create: `portal-gestao/app/templates/trafego/roi.html`
- Modify: `portal-gestao/app/main.py`
- Modify: `portal-gestao/app/templates/trafego/form.html` (link ROI)
- Test: `portal-gestao/tests/test_roi.py`

**Interfaces:**
- Produces:

```python
@dataclass
class LinhaRoiCampanha:
    campanha_id: str
    nome: str
    canal: str
    utm_campaign: str
    gasto: Decimal
    leads: int
    vendas: int
    faturamento: Decimal
    lucro_bruto: Decimal | None  # None se incompleto
    cpl: Decimal | None
    cpa: Decimal | None
    roas: Decimal | None

def calcular_roi_loja(
    *,
    campanhas: list[Campanha],
    gastos: list[CampanhaGasto],  # já filtrados por loja
    leads: list[dict],
    vendas_confirmadas: list[Venda],
    d_inicio: date,
    d_fim: date,
    modo_atribuicao: str = "last",  # 'first' | 'last'
) -> list[LinhaRoiCampanha]:
    ...
```

Regras:
- Lead no período: `d_inicio <= date(criada_em) <= d_fim` e `lead_casa_campanha(..., modo=modo_atribuicao)`.
- Venda no período: mesma regra de `calcular_metricas_vendas` + match por `campanha_id_*` snapshot se preenchido; senão por UTM do lead resolvido (se lead_ref disponível no cálculo).
- Preferir **snapshot na venda** para contagem de vendas (estável).
- Linha extra **“Sem campanha”**: leads/vendas do período sem match (gasto 0).

UI:
- Filtro período (reutilizar `periodo_padrao` do financeiro)
- Toggle first/last touch (query `?touch=first|last`, default `last`)
- Tabela + totais
- Tooltips: “CPL = gasto ÷ leads”, “ROAS = faturamento ÷ gasto”
- Empty states: “Cadastre uma campanha”, “Lance o custo da semana”

- [ ] **Step 1: Unit tests puros (sem HTTP)**

```python
def test_cpl_cpa_roas_basico():
    # 1 campanha, gasto 1000, 10 leads, 2 vendas 5000 cada
    linhas = calcular_roi_loja(...)
    assert linhas[0].cpl == Decimal("100.00")
    assert linhas[0].cpa == Decimal("500.00")
    assert linhas[0].roas == Decimal("10.00")


def test_gasto_zero_metricas_none():
    ...
    assert linha.cpl is None
    assert linha.roas is None


def test_first_vs_last_separa_leads():
    # lead first=A last=B → conta em A no modo first e em B no modo last
    ...
```

- [ ] **Step 2–4:** Implement + rota GET + template

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_roi.py tests/test_campanhas.py -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(portal): dashboard ROI de campanhas (CPL, CPA, ROAS)"
```

---

### Task 7: Filtros por campanha no financeiro/leads + CSV

**Files:**
- Modify: `portal-gestao/app/financeiro_calc.py` — `lead_corresponde_campanha`
- Modify: `portal-gestao/app/main.py` — query param `campanha_id` / `utm_campaign`
- Modify: `portal-gestao/app/templates/financeiro/dashboard.html`
- Modify: `portal-gestao/app/templates/leads/lista.html` e `detalhe.html`
- Modify: `portal-gestao/app/relatorios.py` — export ROI CSV
- Test: estender `tests/test_funil.py` + `tests/test_roi.py`

- [ ] **Step 1: Tests**

```python
def test_financeiro_filtra_utm_campaign(client_dono, chatbot_fake):
    r = client_dono.get("/app/financeiro", params={"utm_campaign": "seminovos-julho"})
    assert r.status_code == 200
    assert "Maria" in r.text or "seminovos" in r.text.casefold()


def test_csv_roi_headers(client_dono):
    r = client_dono.get("/app/relatorios/roi.csv", params={"inicio": "2026-07-01", "fim": "2026-07-31"})
    assert r.status_code == 200
    assert "campanha" in r.text.casefold()
    assert "roas" in r.text.casefold()
```

- [ ] **Step 2–4:** Implement filtros sem quebrar `origem` existente (AND lógico: origem e campanha).

Detalhe do lead: bloco

```html
<section>
  <h3>Origem / tráfego</h3>
  <p>First: {{ lead.utm_source_first }} / {{ lead.utm_campaign_first }}</p>
  <p>Last: {{ lead.utm_source_last }} / {{ lead.utm_campaign_last }}</p>
  <p>fbclid: {{ lead.fbclid or '—' }}</p>
</section>
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(portal): filtros e CSV de ROI por campanha"
```

---

### Task 8 (polish): Pixel `ViewContent` no detalhe do veículo

**Files:**
- Modify: templates catálogo detalhe
- Modify: toggles opcionais em `MetaPixelConfig` **ou** só documentar sempre-on se `enviar_page_view`
- Test: `catalogo-publico/tests/test_pages.py`

**Escopo mínimo:** no detalhe do veículo, se pixel on:

```javascript
fbq('track', 'ViewContent', {
  content_ids: ['{{ veiculo.id }}'],
  content_type: 'product',
  value: {{ veiculo.preco or 0 }},
  currency: 'BRL'
});
```

Não bloquear se preço ausente (`value` omitido).

- [ ] Tests + commit

```bash
git commit -m "feat(catalogo): evento ViewContent no detalhe para otimização de ads"
```

**Fora desta task:** InitiateCheckout na simulação (pode ser follow-up se Chatbot/Portal expuser evento browser — não forçar).

---

### Task 9: Documentação operacional + índice de planos

**Files:**
- Create: `docs/nao-plano/tutoriais/trafego-pago-loja.md`
- Modify: `docs/nao-plano/historico/README.md` — linha do plano
- Modify: `docs/referencia-viva/contexto-compacto.md` — eixo C cita este plano
- Modify: `#3B` topo — Task 5 “detalhada em 2026-07-20-plano-trafego…”
- Modify: `#6` E8 — “implementação: plano 2026-07-20…”

Conteúdo mínimo de `docs/nao-plano/tutoriais/trafego-pago-loja.md`:

1. Criar campanha no Meta com URL do catálogo + UTMs exemplo.
2. Cadastrar mesma `utm_campaign` no Revy.
3. Lançar gasto semanal (print Ads Manager → campo valor).
4. Conferir Pixel/CAPI (E10).
5. Ler ROI (last touch default).
6. Checklist de vazamento: Ads diz 50 msgs, CRM tem 20 leads → links sem UTM / WA direto / número errado.

- [ ] Commit

```bash
git commit -m "docs: guia de tráfego pago e índice do plano de campanhas/ROI"
```

---

## Critérios de aceite (produto)

1. Dono cadastra campanha Meta com `utm_campaign=seminovos-julho` e lança R$ 1.000 de gasto.
2. Lead chega do catálogo com a mesma UTM (e opcionalmente `fbclid`).
3. Lead aparece no ROI da campanha (modo last e first).
4. Venda confirmada com esse lead incrementa vendas/faturamento/ROAS da campanha.
5. Vendedor **não** acessa CRUD de campanhas nem ROI.
6. Lead sem UTM não “suja” campanha paga; aparece em “Sem campanha”.
7. Duas campanhas com mesmo `utm_campaign` na mesma loja são rejeitadas.
8. Testes: `portal-gestao` (`test_campanhas*`, `test_roi*`), `chatbot-api` attribution, `catalogo-publico` pages — verdes.
9. E10 continua funcionando (Purchase CAPI não regressa).

---

## Sequência de verificação final (após todas as tasks)

```bash
cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_campanhas_model.py tests/test_campanhas.py tests/test_roi.py tests/test_trafego.py tests/test_funil.py -q
cd ../chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_catalog_attribution.py -q
cd ../catalogo-publico && .\.venv\Scripts\python.exe -m pytest tests/test_pages.py -q
```

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Loja manda WA no anúncio sem passar pelo catálogo | Guia: usar link wa.me com UTM **ou** landing catálogo; futuro: deep link E11 |
| UTM inconsistente (typo) | Unique + copiar/colar do form Revy; mostrar “leads com utm_campaign desconhecida” no ROI |
| First/last confunde o dono | Default **last**; labels explícitos; sem “modelo de atribuição avançado” |
| Custo digitado errado | Vários lançamentos + nota; não auto-import |
| Performance listar todos leads | MVP: `listar_leads` já usado no financeiro; se >5k leads, paginar/filtrar por data na API depois |
| Migration chatbot em produção | Backfill first=last=utm; deploy Chatbot antes do Portal confiar em `*_first` |

---

## Estimativa (ordem de grandeza)

| Task | Esforço relativo |
|---:|---|
| T1 | P |
| T2 | M |
| T3 | M |
| T4 | P |
| T5 | P–M |
| T6 | M |
| T7 | P–M |
| T8 | P |
| T9 | P |
| **Total** | ~3–6 dias dev focado |

---

## Self-review (cobertura)

| Requisito da conversa / #3B / E8 | Task |
|---|---|
| Cadastrar campanha + UTM + custo | T1, T2 |
| First/last touch explícitos | T3, T6 |
| Origem no lead / click ids | T3, T4 |
| Amarrar venda à campanha | T5 |
| CPL, CPA, ROAS, faturamento | T6 |
| Filtros e export | T7 |
| Pixel além de PageView/Lead | T8 |
| Dono entende o fluxo | T9 |
| Não virar Ad Manager / E9 | Global Constraints |
| Reutilizar E10 | Não reabrir; link na UI |

**Placeholders:** nenhum TBD de implementação nas tasks T1–T9.
**Types:** `Campanha`, `CampanhaGasto`, `LinhaRoiCampanha`, `normalizar_utm`, `calcular_roi_loja` consistentes entre tasks.

---

## Handoff pós-entrega (2026-07-20)

**MVP entregue** — não reabrir T1–T9. Canônico: este arquivo + `docs/nao-plano/tutoriais/trafego-pago-loja.md`.

**Próximos incrementos opcionais (só se o dono priorizar):**
1. Enriquecer CAPI Purchase com phone hash / `fbclid` do lead (match Meta).
2. Import CSV de gastos de campanha em lote.
3. #3B Task 4 (eventos de funil) — independente deste plano.

**Ops:** suíte Fly lab **parada** (uso local). Redeploy só com pedido explícito.
