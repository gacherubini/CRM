# Plano #3 — Portal de Dashboards (LEGADO — substituído pelos Planos #3A e #3B)

> **STATUS: LEGADO — NÃO EXECUTAR.** Os planos válidos são #3A (Portal do Vendedor) e #3B (Dashboard do Dono).
> Motor ou Estoque. Ele consome APIs/eventos versionados e mantém somente seus dados próprios
> (usuários, vendedores, vendas, metas, campanhas e projeções necessárias). Deve funcionar com
> cadastros/importações manuais quando os outros produtos não estiverem instalados. Os papéis são
> `admin_plataforma`, `dono`, `gerente` e `vendedor`, conforme o Plano #0.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um portal web separado e vendável sozinho, onde o funcionário faz login e vê o dashboard **da sua loja** (métricas + últimas conversas do WhatsApp) e pode **rodar uma simulação** direto no site.

**Architecture:** App FastAPI própria (`portal-dashboards/`, deploy próprio) que **lê** os dados do bot por **views de relatório** no Postgres (usuário read-only) e **escreve** apenas via a API do serviço de simulação (motor `/simular`, `/leads`). Autenticação e multi-loja (`loja_id`) são do próprio portal. O motor de simulação é uma capacidade compartilhada entre bot e portal (mesmo contrato `/simular`).

**Tech Stack:** FastAPI, Jinja2, HTMX, Tailwind (via CDN), Chart.js (via CDN), SQLAlchemy 2, psycopg, passlib[bcrypt], Starlette SessionMiddleware, httpx, pytest.

## Global Constraints

- **Pré-requisitos:** Motor `/simular` e `/leads` do Plano #1/#2 disponíveis; Postgres do bot acessível.
- Produto **independente**: pasta/imagem/deploy próprios; nada importa código do bot.
- Portal é **read-only nos dados do bot** (só via `vw_leads`, `vw_conversas`, `vw_metricas`);
  read-write só nas tabelas próprias `lojas`, `usuarios`; escrita em lead **sempre** via API do serviço.
- **Multi-loja:** funcionário vê só `loja_id` dele; `admin` vê todas.
- Segredos via env: `DATABASE_URL_RO`, `SERVICE_BASE_URL`, `SESSION_SECRET`. Nunca commitar.
- Base do serviço na rede do compose: `http://servico-simulacao:8000`.
- TDD nas funções puras (auth, tenancy). Páginas com dados do banco: montar + verificar com evidência.
- Este plano é uma **fatia vertical MVP**. Funil kanban, CSV, admin-todas-lojas e handoff ficam para o Plano #4.

---

### Task 1: Contrato de dados (schema + views + usuário read-only)

**Files:**
- Create: `db/02-portal-contrato.sql`

**Interfaces:**
- Consumes: tabela `leads` (Plano #1/#2).
- Produces: coluna `leads.loja_id`; tabelas `mensagens`, `lojas`, `usuarios`; views `vw_leads`, `vw_conversas`, `vw_metricas`; role `portal_ro`.

- [ ] **Step 1: Criar `db/02-portal-contrato.sql`**

```sql
-- Produzido pelo bot: vínculo de loja e log de mensagens
ALTER TABLE leads ADD COLUMN IF NOT EXISTS loja_id INTEGER;

CREATE TABLE IF NOT EXISTS mensagens (
    id SERIAL PRIMARY KEY,
    loja_id INTEGER,
    telefone TEXT NOT NULL,
    direcao TEXT NOT NULL,             -- 'in' | 'out'
    texto TEXT,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Tabelas próprias do portal (auth/config)
CREATE TABLE IF NOT EXISTS lojas (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    evolution_instance TEXT,           -- mapeia instância WhatsApp -> loja
    criado_em TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    loja_id INTEGER REFERENCES lojas(id),
    papel TEXT NOT NULL DEFAULT 'funcionario',  -- 'funcionario' | 'admin'
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Contrato de leitura (o que o portal enxerga)
CREATE OR REPLACE VIEW vw_leads AS
SELECT id, loja_id, telefone, nome, moto_modelo, valor_moto, entrada,
       prazo_meses, status, criado_em
FROM leads;

CREATE OR REPLACE VIEW vw_conversas AS
SELECT loja_id, telefone,
       max(criado_em) AS ultima_em,
       count(*)       AS total_mensagens
FROM mensagens
GROUP BY loja_id, telefone;

CREATE OR REPLACE VIEW vw_metricas AS
SELECT loja_id,
       count(*)                                              AS total_leads,
       count(*) FILTER (WHERE criado_em::date = current_date) AS leads_hoje,
       count(*) FILTER (WHERE status = 'contatado')           AS contatados
FROM leads
GROUP BY loja_id;

-- Usuário read-only do portal
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'portal_ro') THEN
      CREATE ROLE portal_ro LOGIN PASSWORD 'portal_ro';
   END IF;
END $$;

GRANT CONNECT ON DATABASE financiamento TO portal_ro;
GRANT USAGE ON SCHEMA public TO portal_ro;
GRANT SELECT ON vw_leads, vw_conversas, vw_metricas, mensagens TO portal_ro;
-- Tabelas próprias do portal: leitura e escrita
GRANT SELECT, INSERT, UPDATE, DELETE ON lojas, usuarios TO portal_ro;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO portal_ro;
```

- [ ] **Step 2: Aplicar no Postgres**

Run:
```bash
docker compose exec -T postgres psql -U n8n -d financiamento < db/02-portal-contrato.sql
```
Expected: sem erros (mensagens de `CREATE`/`ALTER`/`GRANT`).

- [ ] **Step 3: Verificar as views**

Run:
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "SELECT * FROM vw_metricas;"
```
Expected: executa sem erro (0+ linhas).

- [ ] **Step 4: Commit**

```bash
git add db/02-portal-contrato.sql
git commit -m "feat: contrato de dados do portal (views + auth + read-only user)"
```

---

### Task 2: Bot grava mensagens e aceita loja_id / status

**Files:**
- Modify: `servico-simulacao/app/models_db.py`
- Modify: `servico-simulacao/app/main.py`
- Modify: `servico-simulacao/app/repositorio.py`
- Test: `servico-simulacao/tests/test_mensagens.py`

**Interfaces:**
- Consumes: `get_db`, `Base` de `app.db`.
- Produces:
  - Modelo `Mensagem` (tabela `mensagens`).
  - `repositorio.registrar_mensagem(db, dados: dict) -> Mensagem`
  - `repositorio.atualizar_status(db, lead_id: int, status: str) -> bool`
  - `POST /mensagens` body `{telefone, direcao, texto, loja_id?}` → `{"id": int}`
  - `PATCH /leads/{id}` body `{status}` → `{"ok": bool}`

- [ ] **Step 1: Adicionar o modelo `Mensagem` em `app/models_db.py`**

```python
class Mensagem(Base):
    __tablename__ = "mensagens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loja_id: Mapped[int] = mapped_column(Integer, nullable=True)
    telefone: Mapped[str] = mapped_column(String)
    direcao: Mapped[str] = mapped_column(String)  # 'in' | 'out'
    texto: Mapped[str] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_mensagens.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import repositorio


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_registrar_mensagem(db):
    m = repositorio.registrar_mensagem(db, {"telefone": "5511999", "direcao": "in", "texto": "oi"})
    assert m.id is not None
    assert m.direcao == "in"


def test_atualizar_status(db):
    lead = repositorio.criar_lead(db, {"telefone": "5511999", "consentimento": True})
    ok = repositorio.atualizar_status(db, lead.id, "contatado")
    assert ok is True
    assert repositorio.atualizar_status(db, 99999, "contatado") is False
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_mensagens.py -v`
Expected: FAIL com `AttributeError: module 'app.repositorio' has no attribute 'registrar_mensagem'`.

- [ ] **Step 4: Implementar no `app/repositorio.py`**

Adicione o import:
```python
from app.models_db import Lead, Mensagem
```
(substitua o import antigo `from app.models_db import Lead`). E adicione:
```python
def registrar_mensagem(db, dados: dict) -> Mensagem:
    m = Mensagem(
        telefone=dados["telefone"],
        direcao=dados["direcao"],
        texto=dados.get("texto"),
        loja_id=dados.get("loja_id"),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def atualizar_status(db, lead_id: int, status: str) -> bool:
    lead = db.get(Lead, lead_id)
    if lead is None:
        return False
    lead.status = status
    db.commit()
    return True
```

- [ ] **Step 5: Adicionar os endpoints em `app/main.py`**

```python
class MensagemInput(BaseModel):
    telefone: str
    direcao: str
    texto: Optional[str] = None
    loja_id: Optional[int] = None


@app.post("/mensagens")
def registrar_mensagem_endpoint(dados: MensagemInput, db: Session = Depends(get_db)):
    m = repositorio.registrar_mensagem(db, dados.model_dump())
    return {"id": m.id}


class StatusInput(BaseModel):
    status: str


@app.patch("/leads/{lead_id}")
def atualizar_status_endpoint(lead_id: int, dados: StatusInput, db: Session = Depends(get_db)):
    return {"ok": repositorio.atualizar_status(db, lead_id, dados.status)}
```

- [ ] **Step 6: Rodar TODA a suíte e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS (tudo, inclusive testes antigos).

- [ ] **Step 7: (n8n) Gravar cada mensagem**

No workflow `Bot` (Plano #2), adicione uma chamada **HTTP Request** logo após o Webhook/Set (mensagem recebida) e após o envio (resposta), para `POST http://servico-simulacao:8000/mensagens` com `{telefone, direcao:"in"/"out", texto}`. Verifique enviando uma mensagem e conferindo:
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "SELECT telefone, direcao, texto FROM mensagens ORDER BY id DESC LIMIT 4;"
```
Expected: as mensagens recentes aparecem.

- [ ] **Step 8: Commit**

```bash
git add servico-simulacao/app/models_db.py servico-simulacao/app/main.py servico-simulacao/app/repositorio.py servico-simulacao/tests/test_mensagens.py
git commit -m "feat: log de mensagens e atualização de status do lead"
```

---

### Task 3: Scaffold do portal + config + health

**Files:**
- Create: `portal-dashboards/requirements.txt`
- Create: `portal-dashboards/pytest.ini`
- Create: `portal-dashboards/app/__init__.py`
- Create: `portal-dashboards/app/config.py`
- Create: `portal-dashboards/app/main.py`
- Test: `portal-dashboards/tests/test_smoke.py`

**Interfaces:**
- Consumes: nada.
- Produces: FastAPI `app` em `app.main`; `GET /health` → `{"status": "ok"}`; `app.config.settings` com `database_url_ro`, `service_base_url`, `session_secret`.

- [ ] **Step 1: Criar `requirements.txt`**

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
jinja2==3.*
sqlalchemy==2.*
psycopg[binary]==3.*
passlib[bcrypt]==1.7.*
itsdangerous==2.*
httpx==0.27.*
pytest==8.*
```

- [ ] **Step 2: Criar `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 3: Criar `app/__init__.py` vazio e `app/config.py`**

`app/config.py`:
```python
import os


class Settings:
    database_url_ro = os.getenv(
        "DATABASE_URL_RO", "postgresql+psycopg://portal_ro:portal_ro@postgres:5432/financiamento"
    )
    service_base_url = os.getenv("SERVICE_BASE_URL", "http://servico-simulacao:8000")
    session_secret = os.getenv("SESSION_SECRET", "dev-secret-trocar")


settings = Settings()
```

- [ ] **Step 4: Instalar deps e escrever o teste que falha**

Rode de `portal-dashboards/`:
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```
Crie `tests/test_smoke.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 5: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 6: Implementar `app/main.py`**

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings

app = FastAPI(title="Portal de Dashboards")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add portal-dashboards/
git commit -m "feat: scaffold do portal de dashboards"
```

---

### Task 4: Autenticação (hash de senha + login por sessão)

**Files:**
- Create: `portal-dashboards/app/db.py`
- Create: `portal-dashboards/app/auth.py`
- Modify: `portal-dashboards/app/main.py`
- Create: `portal-dashboards/app/templates/base.html`
- Create: `portal-dashboards/app/templates/login.html`
- Test: `portal-dashboards/tests/test_auth.py`

**Interfaces:**
- Consumes: `settings` de `app.config`.
- Produces:
  - `app.auth.gerar_hash(senha: str) -> str`, `verificar_senha(senha, senha_hash) -> bool`
  - `app.auth.buscar_usuario_por_email(conn, email) -> dict | None`
  - `app.auth.usuario_atual(request) -> dict | None` (lê `request.session["usuario_id"]`)
  - `app.db.engine` (SQLAlchemy) sobre `database_url_ro`.
  - Rotas `GET /login`, `POST /login`, `GET /logout`.

- [ ] **Step 1: Criar `app/db.py`**

```python
from sqlalchemy import create_engine

from app.config import settings

engine = create_engine(settings.database_url_ro, pool_pre_ping=True)
```

- [ ] **Step 2: Escrever os testes que falham (funções puras)**

Crie `tests/test_auth.py`:
```python
from app.auth import gerar_hash, verificar_senha


def test_hash_diferente_da_senha():
    h = gerar_hash("segredo123")
    assert h != "segredo123"


def test_verificacao_correta():
    h = gerar_hash("segredo123")
    assert verificar_senha("segredo123", h) is True


def test_verificacao_incorreta():
    h = gerar_hash("segredo123")
    assert verificar_senha("errado", h) is False
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_auth.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 4: Implementar `app/auth.py`**

```python
from passlib.context import CryptContext
from sqlalchemy import text

from app.db import engine

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def gerar_hash(senha: str) -> str:
    return _pwd.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return _pwd.verify(senha, senha_hash)


def buscar_usuario_por_email(email: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, senha_hash, loja_id, papel FROM usuarios WHERE email = :e"),
            {"e": email},
        ).mappings().first()
        return dict(row) if row else None


def buscar_usuario_por_id(usuario_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, loja_id, papel FROM usuarios WHERE id = :i"),
            {"i": usuario_id},
        ).mappings().first()
        return dict(row) if row else None


def usuario_atual(request):
    uid = request.session.get("usuario_id")
    if not uid:
        return None
    return buscar_usuario_por_id(uid)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_auth.py -v`
Expected: PASS (3 testes).

- [ ] **Step 6: Criar os templates base e de login**

`app/templates/base.html`:
```html
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Portal{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-100 text-slate-800">
  {% block body %}{% endblock %}
</body>
</html>
```

`app/templates/login.html`:
```html
{% extends "base.html" %}
{% block title %}Entrar{% endblock %}
{% block body %}
<div class="min-h-screen flex items-center justify-center">
  <form method="post" action="/login" class="bg-white p-8 rounded-xl shadow w-80 space-y-4">
    <h1 class="text-xl font-bold">Portal da Loja</h1>
    {% if erro %}<p class="text-red-600 text-sm">{{ erro }}</p>{% endif %}
    <input name="email" type="email" placeholder="E-mail" class="w-full border rounded p-2" required>
    <input name="senha" type="password" placeholder="Senha" class="w-full border rounded p-2" required>
    <button class="w-full bg-slate-800 text-white rounded p-2">Entrar</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 7: Adicionar as rotas de login em `app/main.py`**

Adicione os imports e o `templates`:
```python
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import buscar_usuario_por_email, verificar_senha

templates = Jinja2Templates(directory="app/templates")
```
E as rotas:
```python
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, email: str = Form(...), senha: str = Form(...)):
    usuario = buscar_usuario_por_email(email)
    if not usuario or not verificar_senha(senha, usuario["senha_hash"]):
        return templates.TemplateResponse(
            "login.html", {"request": request, "erro": "Credenciais inválidas"}, status_code=401
        )
    request.session["usuario_id"] = usuario["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 8: Commit**

```bash
git add portal-dashboards/app/db.py portal-dashboards/app/auth.py portal-dashboards/app/main.py portal-dashboards/app/templates/ portal-dashboards/tests/test_auth.py
git commit -m "feat: autenticação por sessão no portal"
```

---

### Task 5: Escopo multi-loja (tenancy)

**Files:**
- Create: `portal-dashboards/app/tenancy.py`
- Test: `portal-dashboards/tests/test_tenancy.py`

**Interfaces:**
- Consumes: dict de usuário (`{papel, loja_id, ...}`).
- Produces: `app.tenancy.escopo_loja_id(usuario: dict) -> int | None` (None = todas as lojas, para admin).

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_tenancy.py`:
```python
from app.tenancy import escopo_loja_id


def test_admin_ve_todas():
    assert escopo_loja_id({"papel": "admin", "loja_id": 1}) is None


def test_funcionario_ve_sua_loja():
    assert escopo_loja_id({"papel": "funcionario", "loja_id": 7}) == 7
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_tenancy.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.tenancy'`.

- [ ] **Step 3: Implementar `app/tenancy.py`**

```python
def escopo_loja_id(usuario: dict):
    if usuario.get("papel") == "admin":
        return None
    return usuario.get("loja_id")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_tenancy.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-dashboards/app/tenancy.py portal-dashboards/tests/test_tenancy.py
git commit -m "feat: escopo multi-loja (tenancy)"
```

---

### Task 6: Dashboard — métricas + últimas conversas

**Files:**
- Create: `portal-dashboards/app/consultas.py`
- Create: `portal-dashboards/app/templates/dashboard.html`
- Modify: `portal-dashboards/app/main.py`

**Interfaces:**
- Consumes: `engine` de `app.db`; `escopo_loja_id` de `app.tenancy`; `usuario_atual` de `app.auth`.
- Produces:
  - `app.consultas.metricas(loja_id) -> dict` (`total_leads`, `leads_hoje`, `contatados`)
  - `app.consultas.ultimas_conversas(loja_id, limite=20) -> list[dict]`
  - Rota `GET /` (dashboard, exige login).

- [ ] **Step 1: Criar `app/consultas.py`**

```python
from sqlalchemy import text

from app.db import engine


def metricas(loja_id):
    with engine.connect() as conn:
        if loja_id is None:
            sql = text(
                "SELECT COALESCE(SUM(total_leads),0) total_leads, "
                "COALESCE(SUM(leads_hoje),0) leads_hoje, "
                "COALESCE(SUM(contatados),0) contatados FROM vw_metricas"
            )
            row = conn.execute(sql).mappings().first()
        else:
            sql = text(
                "SELECT total_leads, leads_hoje, contatados FROM vw_metricas WHERE loja_id = :l"
            )
            row = conn.execute(sql, {"l": loja_id}).mappings().first()
    return dict(row) if row else {"total_leads": 0, "leads_hoje": 0, "contatados": 0}


def ultimas_conversas(loja_id, limite: int = 20):
    with engine.connect() as conn:
        if loja_id is None:
            sql = text(
                "SELECT telefone, ultima_em, total_mensagens FROM vw_conversas "
                "ORDER BY ultima_em DESC LIMIT :lim"
            )
            rows = conn.execute(sql, {"lim": limite}).mappings().all()
        else:
            sql = text(
                "SELECT telefone, ultima_em, total_mensagens FROM vw_conversas "
                "WHERE loja_id = :l ORDER BY ultima_em DESC LIMIT :lim"
            )
            rows = conn.execute(sql, {"l": loja_id, "lim": limite}).mappings().all()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Criar `app/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block body %}
<div class="max-w-5xl mx-auto p-6">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-2xl font-bold">Dashboard</h1>
    <a href="/simular" class="bg-emerald-600 text-white px-4 py-2 rounded">Simular</a>
  </div>

  <div class="grid grid-cols-3 gap-4 mb-8">
    <div class="bg-white rounded-xl shadow p-4">
      <div class="text-slate-500 text-sm">Leads (total)</div>
      <div class="text-3xl font-bold">{{ m.total_leads }}</div>
    </div>
    <div class="bg-white rounded-xl shadow p-4">
      <div class="text-slate-500 text-sm">Leads hoje</div>
      <div class="text-3xl font-bold">{{ m.leads_hoje }}</div>
    </div>
    <div class="bg-white rounded-xl shadow p-4">
      <div class="text-slate-500 text-sm">Contatados</div>
      <div class="text-3xl font-bold">{{ m.contatados }}</div>
    </div>
  </div>

  <h2 class="text-lg font-semibold mb-2">Últimas conversas</h2>
  <div class="bg-white rounded-xl shadow divide-y">
    {% for c in conversas %}
    <a href="/conversa/{{ c.telefone }}" class="flex justify-between p-3 hover:bg-slate-50">
      <span>{{ c.telefone }}</span>
      <span class="text-slate-500 text-sm">{{ c.total_mensagens }} msgs · {{ c.ultima_em }}</span>
    </a>
    {% else %}
    <div class="p-3 text-slate-500">Nenhuma conversa ainda.</div>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Adicionar a rota `GET /` em `app/main.py`**

```python
from app.tenancy import escopo_loja_id
from app.auth import usuario_atual
from app import consultas


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    usuario = usuario_atual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    loja_id = escopo_loja_id(usuario)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "m": consultas.metricas(loja_id),
        "conversas": consultas.ultimas_conversas(loja_id),
    })
```

- [ ] **Step 4: Verificar (manual, com dados semeados)**

Suba o portal (Task 9 traz o Docker; por ora rode local apontando ao Postgres):
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "INSERT INTO lojas (nome) VALUES ('Loja Centro');"
```
Crie um usuário admin (gere o hash com o próprio portal):
```bash
.venv/Scripts/python -c "from app.auth import gerar_hash; print(gerar_hash('senha123'))"
```
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "INSERT INTO usuarios (email, senha_hash, loja_id, papel) VALUES ('admin@loja.com', 'COLE_O_HASH', 1, 'admin');"
```
Rode o portal local: `.venv/Scripts/python -m uvicorn app.main:app --port 9000` (com env `DATABASE_URL_RO` apontando ao Postgres em `localhost:5432`). Faça login em `http://localhost:9000/login` e veja o dashboard.
Expected: cards de métricas e lista de conversas renderizam sem erro.

- [ ] **Step 5: Commit**

```bash
git add portal-dashboards/app/consultas.py portal-dashboards/app/templates/dashboard.html portal-dashboards/app/main.py
git commit -m "feat: dashboard com métricas e últimas conversas"
```

---

### Task 7: Ver a conversa (thread de mensagens)

**Files:**
- Modify: `portal-dashboards/app/consultas.py`
- Create: `portal-dashboards/app/templates/conversa.html`
- Modify: `portal-dashboards/app/main.py`

**Interfaces:**
- Consumes: `engine`; `usuario_atual`; `escopo_loja_id`.
- Produces:
  - `app.consultas.mensagens_da_conversa(telefone, loja_id) -> list[dict]`
  - Rota `GET /conversa/{telefone}`.

- [ ] **Step 1: Adicionar a consulta em `app/consultas.py`**

```python
def mensagens_da_conversa(telefone, loja_id):
    with engine.connect() as conn:
        if loja_id is None:
            sql = text(
                "SELECT direcao, texto, criado_em FROM mensagens "
                "WHERE telefone = :t ORDER BY criado_em ASC"
            )
            rows = conn.execute(sql, {"t": telefone}).mappings().all()
        else:
            sql = text(
                "SELECT direcao, texto, criado_em FROM mensagens "
                "WHERE telefone = :t AND loja_id = :l ORDER BY criado_em ASC"
            )
            rows = conn.execute(sql, {"t": telefone, "l": loja_id}).mappings().all()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Criar `app/templates/conversa.html`**

```html
{% extends "base.html" %}
{% block title %}Conversa {{ telefone }}{% endblock %}
{% block body %}
<div class="max-w-2xl mx-auto p-6">
  <a href="/" class="text-slate-500 text-sm">&larr; Voltar</a>
  <h1 class="text-xl font-bold mb-4">Conversa — {{ telefone }}</h1>
  <div class="space-y-2">
    {% for msg in mensagens %}
    <div class="flex {% if msg.direcao == 'out' %}justify-end{% endif %}">
      <div class="{% if msg.direcao == 'out' %}bg-emerald-100{% else %}bg-white{% endif %} rounded-lg shadow px-3 py-2 max-w-[75%]">
        <div>{{ msg.texto }}</div>
        <div class="text-[10px] text-slate-400 text-right">{{ msg.criado_em }}</div>
      </div>
    </div>
    {% else %}
    <div class="text-slate-500">Sem mensagens.</div>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Adicionar a rota em `app/main.py`**

```python
@app.get("/conversa/{telefone}", response_class=HTMLResponse)
def conversa(request: Request, telefone: str):
    usuario = usuario_atual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    loja_id = escopo_loja_id(usuario)
    return templates.TemplateResponse("conversa.html", {
        "request": request,
        "telefone": telefone,
        "mensagens": consultas.mensagens_da_conversa(telefone, loja_id),
    })
```

- [ ] **Step 4: Verificar (manual)**

No dashboard, clique numa conversa.
Expected: as mensagens `in`/`out` aparecem em balões (entrada à esquerda, saída à direita).

- [ ] **Step 5: Commit**

```bash
git add portal-dashboards/app/consultas.py portal-dashboards/app/templates/conversa.html portal-dashboards/app/main.py
git commit -m "feat: visualização da thread de conversa"
```

---

### Task 8: Página "Simular" no portal

**Files:**
- Create: `portal-dashboards/app/simulacao.py`
- Create: `portal-dashboards/app/templates/simular.html`
- Modify: `portal-dashboards/app/main.py`
- Test: `portal-dashboards/tests/test_simulacao.py`

**Interfaces:**
- Consumes: `settings.service_base_url`.
- Produces:
  - `app.simulacao.simular(dados: dict) -> list[dict]` (chama o motor `/simular` via httpx e retorna `resultados`).
  - Rotas `GET /simular` (form) e `POST /simular` (renderiza resultados).

- [ ] **Step 1: Escrever o teste que falha (com httpx mockado)**

Crie `tests/test_simulacao.py`:
```python
import httpx

from app import simulacao


def test_simular_repassa_e_retorna_resultados(monkeypatch):
    def fake_post(url, json, timeout):
        assert url.endswith("/simular")
        assert json["categoria"] == "moto"
        return httpx.Response(200, json={"resultados": [{"banco": "BV", "valor_parcela": 500.0,
                                                          "taxa_am": 1.79, "n_parcelas": 48,
                                                          "valor_financiado": 15000, "status": "ok"}]})

    monkeypatch.setattr(simulacao.httpx, "post", fake_post)
    out = simulacao.simular({"cpf": "529.982.247-25", "nascimento": "1990-05-20",
                             "valor_moto": 20000, "entrada": 5000, "prazo_meses": 48})
    assert out[0]["banco"] == "BV"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_simulacao.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.simulacao'`.

- [ ] **Step 3: Implementar `app/simulacao.py`**

```python
import httpx

from app.config import settings


def simular(dados: dict) -> list[dict]:
    payload = {
        "cpf": dados["cpf"],
        "nascimento": dados["nascimento"],
        "valor_moto": float(dados["valor_moto"]),
        "entrada": float(dados.get("entrada") or 0),
        "prazo_meses": int(dados["prazo_meses"]),
        "categoria": "moto",
    }
    resp = httpx.post(f"{settings.service_base_url}/simular", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["resultados"]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_simulacao.py -v`
Expected: PASS.

- [ ] **Step 5: Criar `app/templates/simular.html`**

```html
{% extends "base.html" %}
{% block title %}Simular{% endblock %}
{% block body %}
<div class="max-w-2xl mx-auto p-6">
  <a href="/" class="text-slate-500 text-sm">&larr; Voltar</a>
  <h1 class="text-xl font-bold mb-4">Simular financiamento</h1>
  <form method="post" action="/simular" class="bg-white rounded-xl shadow p-4 grid grid-cols-2 gap-3">
    <input name="cpf" placeholder="CPF" class="border rounded p-2" required>
    <input name="nascimento" placeholder="Nascimento (DD/MM/AAAA)" class="border rounded p-2" required>
    <input name="valor_moto" type="number" step="0.01" placeholder="Valor da moto" class="border rounded p-2" required>
    <input name="entrada" type="number" step="0.01" placeholder="Entrada" class="border rounded p-2">
    <input name="prazo_meses" type="number" placeholder="Prazo (meses)" class="border rounded p-2" required>
    <button class="col-span-2 bg-emerald-600 text-white rounded p-2">Simular</button>
  </form>

  {% if resultados %}
  <table class="w-full mt-6 bg-white rounded-xl shadow overflow-hidden">
    <thead class="bg-slate-800 text-white text-left">
      <tr><th class="p-2">Banco</th><th class="p-2">Parcela</th><th class="p-2">Taxa a.m.</th><th class="p-2">Parcelas</th></tr>
    </thead>
    <tbody>
      {% for r in resultados %}
      <tr class="border-t">
        <td class="p-2">{{ r.banco }}</td>
        <td class="p-2">R$ {{ '%.2f'|format(r.valor_parcela) }}</td>
        <td class="p-2">{{ r.taxa_am }}%</td>
        <td class="p-2">{{ r.n_parcelas }}x</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 6: Adicionar as rotas em `app/main.py`**

```python
from app import simulacao


@app.get("/simular", response_class=HTMLResponse)
def simular_form(request: Request):
    if not usuario_atual(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("simular.html", {"request": request})


@app.post("/simular", response_class=HTMLResponse)
def simular_post(request: Request,
                 cpf: str = Form(...), nascimento: str = Form(...),
                 valor_moto: float = Form(...), entrada: float = Form(0),
                 prazo_meses: int = Form(...)):
    if not usuario_atual(request):
        return RedirectResponse("/login", status_code=303)
    resultados = simulacao.simular({
        "cpf": cpf, "nascimento": nascimento, "valor_moto": valor_moto,
        "entrada": entrada, "prazo_meses": prazo_meses,
    })
    return templates.TemplateResponse("simular.html", {"request": request, "resultados": resultados})
```

- [ ] **Step 7: Verificar (manual, com o motor no ar)**

Com `servico-simulacao` rodando, acesse `/simular`, preencha e envie.
Expected: a tabela mostra os 5 bancos com parcela/taxa/prazo (valores mockados).

- [ ] **Step 8: Commit**

```bash
git add portal-dashboards/app/simulacao.py portal-dashboards/app/templates/simular.html portal-dashboards/app/main.py portal-dashboards/tests/test_simulacao.py
git commit -m "feat: página de simulação no portal (consome motor /simular)"
```

---

### Task 9: Dockerizar o portal (deploy independente)

**Files:**
- Create: `portal-dashboards/Dockerfile`
- Create: `portal-dashboards/.dockerignore`
- Create: `portal-dashboards/docker-compose.yml`
- Modify: `docker-compose.yml` (raiz — adicionar o portal ao stack combinado)

**Interfaces:**
- Consumes: Postgres (read-only via `portal_ro`) e `servico-simulacao`.
- Produces: imagem do portal em `http://localhost:9000`; capaz de subir sozinho (compose próprio) ou junto (compose raiz).

- [ ] **Step 1: Criar `portal-dashboards/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

- [ ] **Step 2: Criar `portal-dashboards/.dockerignore`**

```
.venv/
tests/
.pytest_cache/
__pycache__/
```

- [ ] **Step 3: Criar `portal-dashboards/docker-compose.yml` (portal sozinho — venda separada)**

```yaml
# Sobe o portal isolado, apontando para um Postgres e um motor externos.
services:
  portal:
    build: .
    ports:
      - "9000:9000"
    environment:
      - DATABASE_URL_RO=${DATABASE_URL_RO}
      - SERVICE_BASE_URL=${SERVICE_BASE_URL}
      - SESSION_SECRET=${SESSION_SECRET}
```

- [ ] **Step 4: Adicionar o portal ao `docker-compose.yml` da raiz (stack combinado)**

Dentro de `services:`:
```yaml
  portal:
    build: ./portal-dashboards
    ports:
      - "9000:9000"
    environment:
      - DATABASE_URL_RO=postgresql+psycopg://portal_ro:portal_ro@postgres:5432/financiamento
      - SERVICE_BASE_URL=http://servico-simulacao:8000
      - SESSION_SECRET=${SESSION_SECRET}
    depends_on:
      - postgres
      - servico-simulacao
```

- [ ] **Step 5: Subir e verificar ponta a ponta**

Run: `docker compose up -d --build portal`
Acesse `http://localhost:9000/login`, entre com o usuário admin criado, e:
- veja o dashboard (métricas + conversas),
- abra uma conversa,
- rode uma simulação.
Expected: as três telas funcionam. **Critério de aceite do plano.**

- [ ] **Step 6: Commit**

```bash
git add portal-dashboards/Dockerfile portal-dashboards/.dockerignore portal-dashboards/docker-compose.yml docker-compose.yml
git commit -m "feat: dockeriza o portal (deploy isolado e combinado)"
```

---

### Task 10: Controle de handoff na conversa (assumir / devolver ao bot)

**Files:**
- Create: `portal-dashboards/app/handoff.py`
- Modify: `portal-dashboards/app/main.py` (rota da conversa + nova rota)
- Modify: `portal-dashboards/app/templates/conversa.html`
- Test: `portal-dashboards/tests/test_handoff_client.py`

**Interfaces:**
- Consumes: `settings.service_base_url`; endpoints de estado do serviço (Plano #2 Task 7).
- Produces:
  - `app.handoff.obter_estado(telefone) -> dict` (`{"bot_ativo": bool}`)
  - `app.handoff.definir(telefone, ativo: bool) -> dict`
  - Rota `POST /conversa/{telefone}/handoff` (form `ativo`).
  - Tela de conversa exibe o estado e o botão de assumir/devolver.

- [ ] **Step 1: Escrever o teste do client (httpx mockado)**

Crie `tests/test_handoff_client.py`:
```python
import httpx

from app import handoff


def test_obter_estado(monkeypatch):
    monkeypatch.setattr(handoff.httpx, "get",
                        lambda url, timeout: httpx.Response(200, json={"bot_ativo": True}))
    assert handoff.obter_estado("5511999")["bot_ativo"] is True


def test_definir(monkeypatch):
    capturado = {}

    def fake_patch(url, json, timeout):
        capturado["json"] = json
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(handoff.httpx, "patch", fake_patch)
    assert handoff.definir("5511999", False)["ok"] is True
    assert capturado["json"] == {"bot_ativo": False}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_handoff_client.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.handoff'`.

- [ ] **Step 3: Implementar `app/handoff.py`**

```python
import httpx

from app.config import settings


def obter_estado(telefone: str) -> dict:
    r = httpx.get(f"{settings.service_base_url}/conversas/{telefone}/estado", timeout=10)
    r.raise_for_status()
    return r.json()


def definir(telefone: str, ativo: bool) -> dict:
    r = httpx.patch(f"{settings.service_base_url}/conversas/{telefone}/estado",
                    json={"bot_ativo": ativo}, timeout=10)
    r.raise_for_status()
    return r.json()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_handoff_client.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Passar o estado para a tela de conversa**

Em `app/main.py`, na rota `GET /conversa/{telefone}`, adicione `estado`:
```python
from app import handoff
```
E no `TemplateResponse` da conversa, inclua:
```python
        "estado": handoff.obter_estado(telefone),
```

- [ ] **Step 6: Adicionar o botão em `app/templates/conversa.html`**

Logo abaixo do `<h1>` da conversa:
```html
<form method="post" action="/conversa/{{ telefone }}/handoff" class="mb-4">
  {% if estado.bot_ativo %}
    <input type="hidden" name="ativo" value="false">
    <button class="bg-amber-600 text-white px-3 py-1 rounded text-sm">Assumir conversa (pausar bot)</button>
  {% else %}
    <input type="hidden" name="ativo" value="true">
    <button class="bg-emerald-600 text-white px-3 py-1 rounded text-sm">Devolver ao bot</button>
  {% endif %}
</form>
```

- [ ] **Step 7: Adicionar a rota de alternância em `app/main.py`**

```python
@app.post("/conversa/{telefone}/handoff")
def alternar_handoff(request: Request, telefone: str, ativo: str = Form(...)):
    if not usuario_atual(request):
        return RedirectResponse("/login", status_code=303)
    handoff.definir(telefone, ativo == "true")
    return RedirectResponse(f"/conversa/{telefone}", status_code=303)
```

- [ ] **Step 8: Verificar (manual)**

Rebuild o portal, abra uma conversa, clique "Assumir conversa" e confirme (no WhatsApp) que o
bot para de responder àquele contato; clique "Devolver ao bot" e confirme que ele volta.
Expected: o botão alterna o estado e o bot obedece.

- [ ] **Step 9: Commit**

```bash
git add portal-dashboards/app/handoff.py portal-dashboards/app/main.py portal-dashboards/app/templates/conversa.html portal-dashboards/tests/test_handoff_client.py
git commit -m "feat: controle de handoff (assumir/devolver conversa) no portal"
```

---

## Resultado deste plano

Um portal web **separado e vendável sozinho**: login por loja, dashboard, visualização de
conversas integradas e simulação opcional. Consome APIs/eventos e mantém projeções próprias;
também funciona com cadastros/importações manuais, preservando a independência dos produtos.

## Cobertura vs. pedido

- Site com login por loja / "projeto x" → Tasks 3, 4, 5.
- Dashboards exclusivos por loja → Task 5 (tenancy) + 6.
- Últimas conversas do WhatsApp → Tasks 2 (log), 6, 7.
- "O mais importante num site assim" (métricas de gestão) → Task 6.
- Opção de **simular** no site → Task 8.
- Independente / vendável separado → contrato de views (Task 1) + deploy isolado (Task 9).
- Handoff humano (assumir/devolver conversa) → Task 10.

## O que fica para o Plano #4 (portal — recursos ricos)

- Funil de leads (kanban) + ação "marcar contatado" (via `PATCH /leads/{id}`).
- Exportar leads em CSV.
- Visão admin consolidada de todas as lojas + gráficos (Chart.js).
- Status da instância do WhatsApp (conectado?) no dashboard.
- Cadastro de lojas/usuários pela UI (hoje via SQL).
- Persistir cada simulação feita no portal na tabela `simulacoes`.
