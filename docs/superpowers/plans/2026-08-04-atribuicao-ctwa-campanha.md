# Atribuição CTWA → campanha — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer os leads de anúncio nascerem cedo (2ª mensagem) e serem atribuídos à campanha certa — primeiro por `ad_id` cadastrado à mão (Fase 1), depois resolvendo `ad_id → campaign_id` via Graph API (Fase 2).

**Architecture:** Dois produtos. O **Chatbot** (`chatbot-api`, Postgres) cria o lead na 2ª mensagem de uma conversa com tracking CTWA pendente. O **Revy Tráfego** (`revy-trafego`, SQLite no bundle) ganha uma tabela filha de `ad_id` por campanha e uma regra de match no casador; na Fase 2, um worker resolve o `ad_id` para `campaign_id` via Graph e o casador passa a usar esse mapa. Revy puxa leads do Chatbot por HTTP (`GET /v1/leads`), que já expõe `meta_ad_id`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, httpx, pytest.

## Global Constraints

- **Ordem obrigatória:** Fase 1 (Tasks 1–4) inteira e verde antes de começar a Fase 2 (Tasks 5–8).
- **Sem import Python entre produtos.** Integração Chatbot↔Revy só por HTTP.
- **Rodar testes de dentro da pasta do produto** (`chatbot-api` ou `revy-trafego`) com o venv local: `.\.venv\Scripts\python.exe -m pytest -q`.
- **Migrations:** conferir `.\.venv\Scripts\python.exe -m alembic upgrade head` na pasta `revy-trafego`. Próximos números: `0014` e depois `0015`.
- **Credenciais Meta só no Revy, cifradas** (`revy-trafego/app/cripto.py`). Nunca logar/commitar token.
- **Normalização de IDs Meta:** usar `normalizar_meta_campaign_id` de `revy-trafego/app/meta_ads_spend.py` (só dígitos) para `ad_id` e `campaign_id`.
- **Commits pequenos por passo.** Não commitar segredos. Fechar cada task com `git status --short` limpo do que não é seu.

---

# FASE 1 — Lead cedo + match por ad_id (sem Meta API)

### Task 1: Tabela filha `campanha_anuncios` (Revy)

**Files:**
- Modify: `revy-trafego/app/models.py` (adicionar classe `CampanhaAnuncio` + relationship em `Campanha`, perto da classe `Campanha` na linha 649)
- Create: `revy-trafego/alembic/versions/0014_campanha_anuncios.py`
- Test: `revy-trafego/tests/test_campanha_anuncios_model.py`

**Interfaces:**
- Produces: modelo `CampanhaAnuncio(id, loja_slug, campanha_id, ad_id, criada_em)` com `UniqueConstraint(campanha_id, ad_id)`; relationship `Campanha.anuncios -> list[CampanhaAnuncio]`.

- [ ] **Step 1: Write the failing test**

```python
# revy-trafego/tests/test_campanha_anuncios_model.py
from app.db import Base, engine, SessionLocal
from app.models import Campanha, CampanhaAnuncio, novo_id


def _setup():
    Base.metadata.create_all(bind=engine)


def test_campanha_tem_anuncios():
    _setup()
    db = SessionLocal()
    try:
        c = Campanha(
            id=novo_id(), loja_slug="moto-center", nome="MT03 CAUA",
            utm_campaign="mt03", utm_campaign_norm="mt03", criada_por_email="a@b.com",
        )
        db.add(c)
        db.flush()
        db.add(CampanhaAnuncio(id=novo_id(), loja_slug="moto-center",
                               campanha_id=c.id, ad_id="120252470707220341"))
        db.commit()
        db.refresh(c)
        assert [a.ad_id for a in c.anuncios] == ["120252470707220341"]
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_campanha_anuncios_model.py -q`
Expected: FAIL (`ImportError: cannot import name 'CampanhaAnuncio'`).

- [ ] **Step 3: Add the model + relationship**

Em `revy-trafego/app/models.py`, logo após a classe `Campanha` (após a linha 677, dentro do mesmo módulo). Reusa os imports já presentes (`Mapped`, `mapped_column`, `ForeignKey`, `UniqueConstraint`, `String`, `DateTime`, `relationship`, `novo_id`, `agora`):

```python
class CampanhaAnuncio(Base):
    __tablename__ = "campanha_anuncios"
    __table_args__ = (
        UniqueConstraint("campanha_id", "ad_id", name="uq_campanha_ad_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    campanha_id: Mapped[str] = mapped_column(
        ForeignKey("campanhas.id", ondelete="CASCADE"), index=True
    )
    ad_id: Mapped[str] = mapped_column(String(64), index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    campanha: Mapped["Campanha"] = relationship(back_populates="anuncios")
```

E dentro da classe `Campanha` (após o relationship `gastos`, linha 675-677) adicionar:

```python
    anuncios: Mapped[list["CampanhaAnuncio"]] = relationship(
        back_populates="campanha", cascade="all, delete-orphan"
    )
```

- [ ] **Step 4: Create the Alembic migration**

```python
# revy-trafego/alembic/versions/0014_campanha_anuncios.py
"""campanha_anuncios (ad_id por campanha)"""
from alembic import op
import sqlalchemy as sa

revision = "0014_campanha_anuncios"
down_revision = "0013_revy_control_readiness_alert_acceptances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campanha_anuncios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_slug", sa.String(length=120), nullable=False, index=True),
        sa.Column("campanha_id", sa.String(length=36),
                  sa.ForeignKey("campanhas.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("ad_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("campanha_id", "ad_id", name="uq_campanha_ad_id"),
    )


def downgrade() -> None:
    op.drop_table("campanha_anuncios")
```

Confirmar o `down_revision` real: `cd revy-trafego && .\.venv\Scripts\python.exe -m alembic heads` e usar o id impresso se diferir do texto acima.

- [ ] **Step 5: Run migration + test**

Run:
```
cd revy-trafego
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/test_campanha_anuncios_model.py -q
```
Expected: migration aplica sem erro; teste PASSA.

- [ ] **Step 6: Commit**

```bash
git add revy-trafego/app/models.py revy-trafego/alembic/versions/0014_campanha_anuncios.py revy-trafego/tests/test_campanha_anuncios_model.py
git commit -m "feat(revy): tabela campanha_anuncios (ad_id por campanha)"
```

---

### Task 2: Match por ad_id no casador (Revy)

**Files:**
- Modify: `revy-trafego/app/campanhas.py:213-267` (`lead_casa_campanha`)
- Test: `revy-trafego/tests/test_campanhas_match_ad_id.py`

**Interfaces:**
- Consumes: `CampanhaAnuncio` (Task 1); `normalizar_meta_campaign_id` (existente).
- Produces: `lead_casa_campanha` passa a casar quando `lead["meta_ad_id"]` (ou `_first` no modo first) está em `{a.ad_id for a in campanha.anuncios}`.

- [ ] **Step 1: Write the failing test**

```python
# revy-trafego/tests/test_campanhas_match_ad_id.py
from types import SimpleNamespace
from app.campanhas import lead_casa_campanha


def _camp(ad_ids):
    return SimpleNamespace(
        utm_campaign="mt03", utm_content=None, meta_campaign_id=None,
        codigo_ctwa=None, anuncios=[SimpleNamespace(ad_id=a) for a in ad_ids],
    )


def test_casa_por_ad_id_last():
    camp = _camp(["120252470707220341"])
    lead = {"meta_ad_id": "120252470707220341"}
    assert lead_casa_campanha(lead, camp, modo="last") is True


def test_nao_casa_ad_id_fora_da_lista():
    camp = _camp(["120252470707220341"])
    lead = {"meta_ad_id": "999999999999999999"}
    assert lead_casa_campanha(lead, camp, modo="last") is False


def test_casa_por_ad_id_first():
    camp = _camp(["120252470707220341"])
    lead = {"meta_ad_id_first": "120252470707220341", "meta_ad_id": "outro"}
    assert lead_casa_campanha(lead, camp, modo="first") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_campanhas_match_ad_id.py -q`
Expected: FAIL (`test_casa_por_ad_id_last` retorna False — regra ainda não existe).

- [ ] **Step 3: Add rule #4 in `lead_casa_campanha`**

Em `revy-trafego/app/campanhas.py`, dentro de `lead_casa_campanha`, **antes** do `return False` final (linha 267), adicionar:

```python
    # 4) ad_id manual (Fase 1): muitos anúncios → 1 campanha
    ad_ids_camp = {
        normalizar_meta_campaign_id(getattr(a, "ad_id", None))
        for a in getattr(campanha, "anuncios", [])
    }
    ad_ids_camp.discard(None)
    lead_ad = normalizar_meta_campaign_id(
        (lead.get("meta_ad_id_first") if modo == "first" else lead.get("meta_ad_id"))
        or lead.get("meta_ad_id")
    )
    if ad_ids_camp and lead_ad and lead_ad in ad_ids_camp:
        return True
```

`normalizar_meta_campaign_id` já é importado localmente na função (linha 255). Se o import estiver dentro do bloco `meta_campaign_id`, mover o `from app.meta_ads_spend import normalizar_meta_campaign_id` para o topo da função para valer nas duas regras.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_campanhas_match_ad_id.py -q`
Expected: PASS (3 testes).

- [ ] **Step 5: Guard against regression — full suite**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_roi.py tests/test_campanhas_model.py -q`
Expected: PASS (nenhuma regressão no ROI / match existente).

- [ ] **Step 6: Commit**

```bash
git add revy-trafego/app/campanhas.py revy-trafego/tests/test_campanhas_match_ad_id.py
git commit -m "feat(revy): casar lead por ad_id (Fase 1)"
```

---

### Task 3: UI — cadastrar ad_ids na campanha (Revy)

**Files:**
- Create: `revy-trafego/app/campanha_anuncios.py` (helper de sync, testável isolado)
- Modify: `revy-trafego/app/main.py:775-816` (`campanhas_nova_post`) e `:1085-1126` (`campanhas_editar_post`)
- Modify: `revy-trafego/app/templates/campanhas/form.html` (textarea + pré-preenchimento)
- Modify: `revy-trafego/app/main.py:1052-1084` (`campanhas_editar_get`) para passar os ad_ids atuais ao form
- Test: `revy-trafego/tests/test_campanha_anuncios_sync.py`

**Interfaces:**
- Produces: `sincronizar_anuncios(db, campanha, linhas_texto: str) -> list[str]` — parseia texto (um ad_id por linha), normaliza (só dígitos, sem vazios/dups) e sincroniza `campanha_anuncios` (insere novos, remove ausentes). Retorna a lista final de ad_ids.

- [ ] **Step 1: Write the failing test**

```python
# revy-trafego/tests/test_campanha_anuncios_sync.py
from app.db import Base, engine, SessionLocal
from app.models import Campanha, CampanhaAnuncio, novo_id
from app.campanha_anuncios import sincronizar_anuncios


def _camp(db):
    c = Campanha(id=novo_id(), loja_slug="moto-center", nome="c",
                 utm_campaign="mt03", utm_campaign_norm="mt03", criada_por_email="a@b.com")
    db.add(c); db.flush(); return c


def test_sync_insere_e_remove():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        c = _camp(db)
        sincronizar_anuncios(db, c, "120252470707220341\n120252470799120341\n")
        db.commit()
        assert {a.ad_id for a in db.query(CampanhaAnuncio).all()} == {
            "120252470707220341", "120252470799120341"}
        # reeditar removendo um e adicionando lixo (deve normalizar/ignorar)
        sincronizar_anuncios(db, c, " 120252470707220341 \nabc\n")
        db.commit()
        assert {a.ad_id for a in db.query(CampanhaAnuncio).filter_by(campanha_id=c.id)} == {
            "120252470707220341"}
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_campanha_anuncios_sync.py -q`
Expected: FAIL (`ModuleNotFoundError: app.campanha_anuncios`).

- [ ] **Step 3: Implement the sync helper**

```python
# revy-trafego/app/campanha_anuncios.py
from __future__ import annotations
from sqlalchemy.orm import Session
from app.meta_ads_spend import normalizar_meta_campaign_id
from app.models import CampanhaAnuncio, novo_id


def parse_ad_ids(texto: str | None) -> list[str]:
    vistos: list[str] = []
    for linha in (texto or "").splitlines():
        n = normalizar_meta_campaign_id(linha)
        if n and n not in vistos:
            vistos.append(n)
    return vistos


def sincronizar_anuncios(db: Session, campanha, texto: str | None) -> list[str]:
    desejados = set(parse_ad_ids(texto))
    atuais = {a.ad_id: a for a in db.query(CampanhaAnuncio)
              .filter(CampanhaAnuncio.campanha_id == campanha.id).all()}
    for ad_id, obj in atuais.items():
        if ad_id not in desejados:
            db.delete(obj)
    for ad_id in desejados:
        if ad_id not in atuais:
            db.add(CampanhaAnuncio(id=novo_id(), loja_slug=campanha.loja_slug,
                                   campanha_id=campanha.id, ad_id=ad_id))
    return sorted(desejados)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_campanha_anuncios_sync.py -q`
Expected: PASS.

- [ ] **Step 5: Wire into the routes + template**

Em `campanhas_nova_post` (após `db.add(c)` na linha 814, antes do `db.commit()`):

```python
    from app.campanha_anuncios import sincronizar_anuncios
    sincronizar_anuncios(db, c, form.get("ad_ids"))
```

Em `campanhas_editar_post` (após `preencher_campanha(campanha, dados)` na linha 1124, antes do `db.commit()`):

```python
    from app.campanha_anuncios import sincronizar_anuncios
    sincronizar_anuncios(db, campanha, form.get("ad_ids"))
```

Em `campanhas_editar_get` (linha 1052-1084), incluir no contexto os ad_ids atuais para o textarea, ex.:

```python
    ad_ids_texto = "\n".join(a.ad_id for a in campanha.anuncios)
    # passar ad_ids_texto para _campanha_form_ctx / valores
```

Em `templates/campanhas/form.html`, adicionar o campo (perto de `meta_campaign_id`):

```html
<label>IDs de anúncio (um por linha)
  <textarea name="ad_ids" rows="4"
    placeholder="120252470707220341">{{ valores.ad_ids or ad_ids_texto or '' }}</textarea>
  <small>Cole o ID de cada anúncio desta campanha (Gerenciador de Anúncios → Anúncios).</small>
</label>
```

- [ ] **Step 6: Run the campaign-route tests (or add one) + full suite**

Se houver teste de rota de campanha (`grep -l campanhas_nova revy-trafego/tests`), rodá-lo; senão confiar no teste do helper.
Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (suite inteira do produto).

- [ ] **Step 7: Commit**

```bash
git add revy-trafego/app/campanha_anuncios.py revy-trafego/app/main.py revy-trafego/app/templates/campanhas/form.html revy-trafego/tests/test_campanha_anuncios_sync.py
git commit -m "feat(revy): cadastrar ad_ids na campanha (UI + sync)"
```

---

### Task 4: Chatbot — criar lead na 2ª mensagem CTWA

**Files:**
- Modify: `chatbot-api/app/servico.py` — bloco `if not from_me and loja_operacional:` (linha 778-841); a função de persistência de mensagem que já calcula `primeira_mensagem` (linha 737) e monta o retorno (linhas 941-955)
- Test: `chatbot-api/tests/test_lead_2a_mensagem.py`

**Interfaces:**
- Consumes: `primeira_mensagem` (servico.py:737), `_carregar_tracking_pendente` (146), `_get_or_create_lead` (1585), `_vincular_tracking_pendente_ao_lead` (1626).
- Produces: lead criado automaticamente na 2ª entrada de conversa com tracking CTWA pendente; retorno do webhook ganha `lead_criado_auto: bool`.

- [ ] **Step 1: Write the failing test**

```python
# chatbot-api/tests/test_lead_2a_mensagem.py
def test_segunda_mensagem_ctwa_cria_lead(client, loja_a):
    inst, headers = loja_a["instance"], loja_a["headers"]
    # 1ª msg (clique do anúncio) — NÃO cria lead
    r1 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511987654321", "texto": "oi",
        "provider_message_id": "wamid-1", "from_me": False,
        "ctwa_clid": "ARclid1", "meta_ad_id": "120252470707220341"})
    assert r1.status_code == 200
    assert client.get("/v1/leads", headers=headers).json()["leads"] == []
    # 2ª msg (cliente respondeu de verdade) — cria lead com o ad_id
    r2 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511987654321", "texto": "quero saber o preço",
        "provider_message_id": "wamid-2", "from_me": False})
    assert r2.status_code == 200
    assert r2.json().get("lead_criado_auto") is True
    leads = client.get("/v1/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
    assert leads[0]["meta_ad_id"] == "120252470707220341"
    assert leads[0]["origem"] == "meta_ctwa"


def test_segunda_mensagem_sem_ctwa_nao_cria_lead(client, loja_a):
    inst, headers = loja_a["instance"], loja_a["headers"]
    for i in (1, 2):
        client.post("/webhook/mensagem", json={
            "instance": inst, "telefone": "5511900000000", "texto": "oi",
            "provider_message_id": f"nctwa-{i}", "from_me": False})
    assert client.get("/v1/leads", headers=headers).json()["leads"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_lead_2a_mensagem.py -q`
Expected: FAIL (`test_segunda_mensagem_ctwa_cria_lead`: leads vazio / `lead_criado_auto` ausente).

- [ ] **Step 3: Implement auto-create on 2nd message**

Em `chatbot-api/app/servico.py`, dentro do bloco `if not from_me and loja_operacional:`, **após** o tratamento de touch/pendência CTWA (após a linha 826) e **antes** do `registrar_auditoria_ctwa` (linha 827), inserir:

```python
        lead_criado_auto = False
        if lead_ctwa is None and not primeira_mensagem:
            pend = _carregar_tracking_pendente(conversa)
            tem_ctwa_pend = any(
                pend.get(k) for k in ("ctwa_clid", "meta_ad_id", "meta_campaign_id", "ctwa_codigo")
            )
            if tem_ctwa_pend:
                lead_novo = _get_or_create_lead(db, loja.id, telefone)
                _vincular_tracking_pendente_ao_lead(db, loja.id, telefone, lead_novo)
                if not lead_novo.origem:
                    lead_novo.origem = "meta_ctwa"
                lead_novo.atualizada_em = datetime.now(timezone.utc)
                lead_ctwa_id = lead_novo.id
                lead_criado_auto = True
```

Inicializar `lead_criado_auto = False` junto das outras flags (perto da linha 774-777) para o retorno sempre ter a chave, e adicionar `"lead_criado_auto": lead_criado_auto` no dict de retorno do fluxo normal (junto de `"ctwa_pendente"`, linha ~955). Garantir que `aplicar_touch_ctwa` (chamado dentro de `_vincular_tracking_pendente_ao_lead`) seta `origem=meta_ctwa` — o fallback acima cobre caso não.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_lead_2a_mensagem.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Idempotência + suite CTWA**

Run: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_ctwa_attribution.py tests/test_leads.py -q`
Expected: PASS. Se `test_webhook_ctwa_enriquece_lead` quebrar (ele criava lead via POST após 2 mensagens), ajustar o teste para o novo comportamento (lead já existe) — não relaxar a idempotência (`_get_or_create_lead` não pode duplicar).

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/servico.py chatbot-api/tests/test_lead_2a_mensagem.py
git commit -m "feat(chatbot): criar lead na 2a mensagem de conversa CTWA"
```

---

**➡️ Checkpoint Fase 1:** rodar as duas suites inteiras (`chatbot-api` e `revy-trafego`) verdes + `alembic upgrade head` no Revy antes de seguir. A partir daqui a atribuição já funciona com ad_id manual. **Só então iniciar a Fase 2.**

---

# FASE 2 — Resolver ad_id → campaign_id via Graph API

### Task 5: Cache `meta_ad_campanha` + token ads_read (Revy)

**Files:**
- Modify: `revy-trafego/app/models.py` (classe `MetaAdCampanha`; garantir campo de token em `meta_ads_config` — já tem `token_ciphertext`, adicionar `ad_account_id` se faltar)
- Create: `revy-trafego/alembic/versions/0015_meta_ad_campanha.py`
- Test: `revy-trafego/tests/test_meta_ad_campanha_model.py`

**Interfaces:**
- Produces: `MetaAdCampanha(loja_slug, ad_id, meta_campaign_id, meta_campaign_nome, resolvido_em, erro, tentativas)` com `UniqueConstraint(loja_slug, ad_id)`.

- [ ] **Step 1: Write the failing test**

```python
# revy-trafego/tests/test_meta_ad_campanha_model.py
from app.db import Base, engine, SessionLocal
from app.models import MetaAdCampanha


def test_cache_grava_resolucao():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(MetaAdCampanha(loja_slug="moto-center", ad_id="120252470707220341",
                              meta_campaign_id="120249613359800224",
                              meta_campaign_nome="MT03 CAUA", tentativas=1))
        db.commit()
        row = db.query(MetaAdCampanha).filter_by(ad_id="120252470707220341").one()
        assert row.meta_campaign_id == "120249613359800224"
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_meta_ad_campanha_model.py -q`
Expected: FAIL (`ImportError: MetaAdCampanha`).

- [ ] **Step 3: Add model**

```python
# revy-trafego/app/models.py (nova classe)
class MetaAdCampanha(Base):
    __tablename__ = "meta_ad_campanha"
    __table_args__ = (
        UniqueConstraint("loja_slug", "ad_id", name="uq_meta_ad_campanha"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    ad_id: Mapped[str] = mapped_column(String(64), index=True)
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta_campaign_nome: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    resolvido_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    erro: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    tentativas: Mapped[int] = mapped_column(default=0)
```

- [ ] **Step 4: Migration**

```python
# revy-trafego/alembic/versions/0015_meta_ad_campanha.py
"""cache meta_ad_campanha"""
from alembic import op
import sqlalchemy as sa

revision = "0015_meta_ad_campanha"
down_revision = "0014_campanha_anuncios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_ad_campanha",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_slug", sa.String(length=120), nullable=False, index=True),
        sa.Column("ad_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("meta_campaign_id", sa.String(length=64), nullable=True),
        sa.Column("meta_campaign_nome", sa.String(length=200), nullable=True),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.String(length=300), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("loja_slug", "ad_id", name="uq_meta_ad_campanha"),
    )


def downgrade() -> None:
    op.drop_table("meta_ad_campanha")
```

- [ ] **Step 5: Run migration + test**

Run:
```
cd revy-trafego
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/test_meta_ad_campanha_model.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add revy-trafego/app/models.py revy-trafego/alembic/versions/0015_meta_ad_campanha.py revy-trafego/tests/test_meta_ad_campanha_model.py
git commit -m "feat(revy): cache meta_ad_campanha (Fase 2)"
```

---

### Task 6: Cliente Graph (Revy)

**Files:**
- Create: `revy-trafego/app/clients/meta_graph.py`
- Test: `revy-trafego/tests/test_meta_graph_client.py`

**Interfaces:**
- Produces: `resolver_campanha_do_anuncio(ad_id: str, token: str, *, timeout: float = 5.0, transport=None) -> tuple[str | None, str | None]` — retorna `(campaign_id, campaign_nome)` ou `(None, None)` em falha. Nunca lança; nunca inclui o token em mensagem.

- [ ] **Step 1: Write the failing test (httpx mock, sem rede)**

```python
# revy-trafego/tests/test_meta_graph_client.py
import httpx
from app.clients.meta_graph import resolver_campanha_do_anuncio


def _transport(status, payload):
    def handler(req):
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(handler)


def test_resolve_ok():
    t = _transport(200, {"campaign": {"id": "120249613359800224", "name": "MT03 CAUA"}})
    cid, nome = resolver_campanha_do_anuncio("120252470707220341", "TOKEN", transport=t)
    assert cid == "120249613359800224"
    assert nome == "MT03 CAUA"


def test_resolve_erro_nao_lanca():
    t = _transport(400, {"error": {"message": "bad"}})
    assert resolver_campanha_do_anuncio("x", "TOKEN", transport=t) == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_meta_graph_client.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement client**

```python
# revy-trafego/app/clients/meta_graph.py
from __future__ import annotations
import logging
import httpx

logger = logging.getLogger(__name__)
GRAPH_VERSION = "v21.0"  # confirmar versão estável atual antes de deploy


def resolver_campanha_do_anuncio(
    ad_id: str, token: str, *, timeout: float = 5.0, transport=None
) -> tuple[str | None, str | None]:
    ad_id = (ad_id or "").strip()
    if not ad_id or not token:
        return (None, None)
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{ad_id}"
    params = {"fields": "campaign{id,name}", "access_token": token}
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("meta_graph: ad %s status %s", ad_id, resp.status_code)
                return (None, None)
            camp = (resp.json() or {}).get("campaign") or {}
            return (camp.get("id"), camp.get("name"))
    except (httpx.HTTPError, ValueError):
        logger.warning("meta_graph: falha ao resolver ad %s", ad_id)
        return (None, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_meta_graph_client.py -q`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/clients/meta_graph.py revy-trafego/tests/test_meta_graph_client.py
git commit -m "feat(revy): cliente Graph resolve ad_id->campanha"
```

---

### Task 7: Worker de resolução (Revy)

**Files:**
- Create: `revy-trafego/app/meta_ad_resolver_job.py`
- Test: `revy-trafego/tests/test_meta_ad_resolver_job.py`

**Interfaces:**
- Consumes: `MetaAdCampanha` (Task 5), `resolver_campanha_do_anuncio` (Task 6).
- Produces: `resolver_ads_pendentes(db, loja_slug, ad_ids: list[str], resolver=resolver_campanha_do_anuncio, token: str) -> int` — faz upsert no cache dos `ad_ids` ainda não resolvidos; retorna quantos resolveu. Nunca lança. Gated no orquestrador por env `REVY_TRAFEGO_AD_RESOLVER_ENABLED`.

- [ ] **Step 1: Write the failing test (resolver injetado, sem rede)**

```python
# revy-trafego/tests/test_meta_ad_resolver_job.py
from app.db import Base, engine, SessionLocal
from app.models import MetaAdCampanha
from app.meta_ad_resolver_job import resolver_ads_pendentes


def fake_resolver(ad_id, token, **kw):
    return ("120249613359800224", "MT03 CAUA") if ad_id == "120252470707220341" else (None, None)


def test_resolve_e_cacheia():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = resolver_ads_pendentes(db, "moto-center",
                                   ["120252470707220341", "999"],
                                   resolver=fake_resolver, token="T")
        db.commit()
        assert n == 1
        row = db.query(MetaAdCampanha).filter_by(ad_id="120252470707220341").one()
        assert row.meta_campaign_id == "120249613359800224"
        # não re-resolve o que já está cacheado
        assert resolver_ads_pendentes(db, "moto-center", ["120252470707220341"],
                                      resolver=fake_resolver, token="T") == 0
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_meta_ad_resolver_job.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement worker function**

```python
# revy-trafego/app/meta_ad_resolver_job.py
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.clients.meta_graph import resolver_campanha_do_anuncio
from app.meta_ads_spend import normalizar_meta_campaign_id
from app.models import MetaAdCampanha, novo_id


def resolver_ads_pendentes(db: Session, loja_slug: str, ad_ids, *,
                           token: str, resolver=resolver_campanha_do_anuncio) -> int:
    if not token:
        return 0
    ja = {r.ad_id for r in db.query(MetaAdCampanha)
          .filter(MetaAdCampanha.loja_slug == loja_slug,
                  MetaAdCampanha.meta_campaign_id.isnot(None)).all()}
    resolvidos = 0
    for raw in ad_ids:
        ad_id = normalizar_meta_campaign_id(raw)
        if not ad_id or ad_id in ja:
            continue
        cid, nome = resolver(ad_id, token)
        row = (db.query(MetaAdCampanha)
               .filter_by(loja_slug=loja_slug, ad_id=ad_id).first())
        if row is None:
            row = MetaAdCampanha(id=novo_id(), loja_slug=loja_slug, ad_id=ad_id)
            db.add(row)
        row.tentativas = (row.tentativas or 0) + 1
        if cid:
            row.meta_campaign_id = normalizar_meta_campaign_id(cid)
            row.meta_campaign_nome = nome
            row.resolvido_em = datetime.now(timezone.utc)
            row.erro = None
            resolvidos += 1
        else:
            row.erro = "nao_resolvido"
    return resolvidos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_meta_ad_resolver_job.py -q`
Expected: PASS.

- [ ] **Step 5: Wire the scheduler entrypoint (gated, OFF by default)**

No ponto onde o Revy agenda os workers (mesmo lugar do `meta_ads_spend_job`/`meta_capi_job`; procurar `REVY_TRAFEGO_CAPI_WORKER` / `META_SPEND_SYNC` em `app/main.py` ou `app/config.py`), adicionar um loop periódico só se `os.getenv("REVY_TRAFEGO_AD_RESOLVER_ENABLED") == "1"`, que para cada loja: puxa leads (`get_chatbot(slug).listar_leads()`), extrai `meta_ad_id`/`meta_ad_id_first` distintos, decifra o token (`app/cripto.decifrar`) da `meta_ads_config` e chama `resolver_ads_pendentes(...)`. Envolver em try/except que loga e segue (nunca derruba o processo).

- [ ] **Step 6: Commit**

```bash
git add revy-trafego/app/meta_ad_resolver_job.py revy-trafego/tests/test_meta_ad_resolver_job.py revy-trafego/app/main.py revy-trafego/app/config.py
git commit -m "feat(revy): worker resolve ad_id->campanha (gated OFF)"
```

---

### Task 8: Casador usa o cache (Revy)

**Files:**
- Modify: `revy-trafego/app/roi_calc.py:90-124` (`calcular_roi_loja`) e `revy-trafego/app/campanhas.py` (`lead_casa_campanha`)
- Modify: `revy-trafego/app/api_v1.py:104-124` e/ou `app/main.py` (ROI): montar `mapa_ad_campaign` do cache e passar adiante
- Test: `revy-trafego/tests/test_match_via_cache.py`

**Interfaces:**
- Consumes: `MetaAdCampanha` (Task 5).
- Produces: `calcular_roi_loja(..., mapa_ad_campaign: dict[str, str] | None = None)`; `lead_casa_campanha(lead, campanha, *, modo, mapa_ad_campaign=None)` casa quando `mapa_ad_campaign[lead_ad] == normalizar(campanha.meta_campaign_id)`.

- [ ] **Step 1: Write the failing test**

```python
# revy-trafego/tests/test_match_via_cache.py
from types import SimpleNamespace
from app.campanhas import lead_casa_campanha


def test_casa_via_cache_ad_para_campaign():
    camp = SimpleNamespace(utm_campaign="mt03", utm_content=None,
                           meta_campaign_id="120249613359800224",
                           codigo_ctwa=None, anuncios=[])
    lead = {"meta_ad_id": "120252470707220341"}
    mapa = {"120252470707220341": "120249613359800224"}
    assert lead_casa_campanha(lead, camp, modo="last", mapa_ad_campaign=mapa) is True
    assert lead_casa_campanha(lead, camp, modo="last", mapa_ad_campaign={}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_match_via_cache.py -q`
Expected: FAIL (`TypeError: unexpected keyword argument 'mapa_ad_campaign'`).

- [ ] **Step 3: Thread the map through**

Em `lead_casa_campanha`, adicionar o parâmetro `mapa_ad_campaign: dict | None = None` e, **após** a regra #4 (Task 2) e antes do `return False`:

```python
    # 5) Fase 2: ad_id resolvido para campaign_id via cache Graph
    if mapa_ad_campaign and lead_ad:
        cid = normalizar_meta_campaign_id(mapa_ad_campaign.get(lead_ad))
        if cid and cid == camp_meta:
            return True
```

(`lead_ad` e `camp_meta` já existem no corpo da função vindos das regras #2/#4.) Em `calcular_roi_loja`, aceitar `mapa_ad_campaign=None` e repassá-lo nas duas chamadas de `lead_casa_campanha` (linhas 111-113 e 163). Em `resolver_campanhas_do_lead`/`venda_casa_campanha` manter compat (default None).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_match_via_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Build the map at ROI time**

No endpoint de ROI (`api_v1.py` ~linha 116, e o equivalente em `main.py` se existir), antes de `calcular_roi_loja`, montar:

```python
    from app.models import MetaAdCampanha
    mapa_ad_campaign = {
        r.ad_id: r.meta_campaign_id
        for r in db.query(MetaAdCampanha)
        .filter(MetaAdCampanha.loja_slug == slug,
                MetaAdCampanha.meta_campaign_id.isnot(None)).all()
    }
```

e passar `mapa_ad_campaign=mapa_ad_campaign` para `calcular_roi_loja`.

- [ ] **Step 6: Full suite (no regression)**

Run: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add revy-trafego/app/roi_calc.py revy-trafego/app/campanhas.py revy-trafego/app/api_v1.py revy-trafego/tests/test_match_via_cache.py
git commit -m "feat(revy): casar por ad_id resolvido via cache Graph (Fase 2)"
```

---

## Self-review (feito pelo autor do plano)

- **Cobertura do spec:** 1A→Task 4; 1B tabela→Task 1, matcher→Task 2, UI→Task 3; 2.1 token→Task 5; 2.2 cache→Task 5; 2.3 cliente→Task 6; 2.4 worker→Task 7; 2.5 casador via mapa→Task 8. ✅
- **Ordem:** Fase 1 (1–4) com checkpoint antes da Fase 2 (5–8). ✅
- **Sem placeholders:** todo passo tem código real e comando de teste.
- **Consistência de tipos:** `normalizar_meta_campaign_id` usado igual em Tasks 2/7/8; `mapa_ad_campaign: dict[str,str]` idem; `resolver(ad_id, token)` assinatura consistente entre Task 6 e 7.

## Notas de verificação final (antes de deploy)
- Confirmar `alembic heads` para os `down_revision` reais (0013/0014).
- Confirmar a versão estável do Graph (`GRAPH_VERSION`).
- Fase 2 permanece OFF (`REVY_TRAFEGO_AD_RESOLVER_ENABLED` ausente) até o token existir.
