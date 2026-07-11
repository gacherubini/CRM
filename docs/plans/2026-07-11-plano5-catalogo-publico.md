# Plano #5 — Catálogo Público (LEGADO — substituído pelo Plano #5A)

> **STATUS: LEGADO — NÃO EXECUTAR.** O plano válido é o **Plano #5A — Catálogo Público Independente**.
> não acessa views nem credenciais do banco de outro produto. Seu compose isolado precisa funcionar
> apontando apenas para `ESTOQUE_API_URL`, e cliques de interesse são emitidos como eventos para uma
> URL opcional — a ausência de Chatbot ou Portal não pode quebrar a vitrine.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um site público (sem login) onde o cliente navega pelo estoque **publicado** de uma loja (motos e carros), filtra por tipo e clica em "Tenho interesse" para falar no WhatsApp da loja.

**Architecture alvo:** App própria (`catalogo-publico/`, deploy próprio, vendável sozinha). Lê
somente veículos publicados pela API do Produto de Estoque. Não recebe credencial de banco de outro
produto. O botão de interesse gera `wa.me` e pode emitir um evento para webhook opcional.

**Tech Stack:** FastAPI, Jinja2, Tailwind (CDN), SQLAlchemy 2, psycopg, pytest.

## Global Constraints

- **Pré-requisitos:** Plano #4 concluído (tabela `veiculos` com `publicado`, `foto_url`); Plano #3 (tabela `lojas`).
- Produto **independente**: pasta/imagem/deploy próprios; **read-only** no banco (só views).
- Uma loja por URL: `/l/{loja_id}`. Só aparecem veículos `publicado = true` daquela loja.
- Sem autenticação (site público). Sem nenhuma escrita.
- Segredos via env: `DATABASE_URL_RO`. Nunca commitar.
- TDD no que é função pura/rota; páginas com dados: montar + verificar.

---

### Task 1: Contrato público (views + coluna whatsapp)

**Files:**
- Create: `db/03-catalogo-publico.sql`

**Interfaces:**
- Consumes: tabelas `veiculos` (Plano #4), `lojas` (Plano #3).
- Produces: coluna `lojas.whatsapp`; views `vw_veiculos_publicos`, `vw_lojas_publicas`; SELECT concedido a `portal_ro`.

- [ ] **Step 1: Criar `db/03-catalogo-publico.sql`**

```sql
ALTER TABLE lojas ADD COLUMN IF NOT EXISTS whatsapp TEXT;  -- ex.: 5511999999999

CREATE OR REPLACE VIEW vw_veiculos_publicos AS
SELECT id, loja_id, tipo, marca, modelo, ano, cor, km, valor, foto_url, criado_em
FROM veiculos
WHERE publicado = true AND status = 'disponivel';

CREATE OR REPLACE VIEW vw_lojas_publicas AS
SELECT id, nome, whatsapp
FROM lojas;

GRANT SELECT ON vw_veiculos_publicos, vw_lojas_publicas TO portal_ro;
```

- [ ] **Step 2: Aplicar no Postgres**

Run:
```bash
docker compose exec -T postgres psql -U n8n -d financiamento < db/03-catalogo-publico.sql
```
Expected: sem erros.

- [ ] **Step 3: Semear dado de teste (uma loja com whatsapp + veículo publicado)**

Run:
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "UPDATE lojas SET whatsapp='5511999999999' WHERE id=1;"
docker compose exec postgres psql -U n8n -d financiamento -c "SELECT * FROM vw_veiculos_publicos WHERE loja_id=1;"
```
Expected: retorna os veículos publicados da loja 1 (crie um no portal se estiver vazio).

- [ ] **Step 4: Commit**

```bash
git add db/03-catalogo-publico.sql
git commit -m "feat: contrato público (views de vitrine + whatsapp da loja)"
```

---

### Task 2: Scaffold do catálogo público + health

**Files:**
- Create: `catalogo-publico/requirements.txt`
- Create: `catalogo-publico/pytest.ini`
- Create: `catalogo-publico/app/__init__.py`
- Create: `catalogo-publico/app/config.py`
- Create: `catalogo-publico/app/db.py`
- Create: `catalogo-publico/app/main.py`
- Test: `catalogo-publico/tests/test_smoke.py`

**Interfaces:**
- Consumes: nada.
- Produces: FastAPI `app`; `GET /health` → `{"status": "ok"}`; `app.config.settings.database_url_ro`; `app.db.engine`.

- [ ] **Step 1: Criar `requirements.txt`**

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
jinja2==3.*
sqlalchemy==2.*
psycopg[binary]==3.*
httpx==0.27.*
pytest==8.*
```

- [ ] **Step 2: Criar `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 3: Criar `app/__init__.py` vazio, `app/config.py` e `app/db.py`**

`app/config.py`:
```python
import os


class Settings:
    database_url_ro = os.getenv(
        "DATABASE_URL_RO", "postgresql+psycopg://portal_ro:portal_ro@postgres:5432/financiamento"
    )


settings = Settings()
```
`app/db.py`:
```python
from sqlalchemy import create_engine

from app.config import settings

engine = create_engine(settings.database_url_ro, pool_pre_ping=True)
```

- [ ] **Step 4: Instalar deps e escrever o teste que falha**

De `catalogo-publico/`:
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

app = FastAPI(title="Catálogo Público")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add catalogo-publico/
git commit -m "feat: scaffold do catálogo público"
```

---

### Task 3: Vitrine por loja (`/l/{loja_id}`)

**Files:**
- Create: `catalogo-publico/app/consultas.py`
- Create: `catalogo-publico/app/templates/base.html`
- Create: `catalogo-publico/app/templates/vitrine.html`
- Modify: `catalogo-publico/app/main.py`

**Interfaces:**
- Consumes: `engine` de `app.db`.
- Produces:
  - `app.consultas.loja_publica(loja_id) -> dict | None`
  - `app.consultas.veiculos_publicos(loja_id, tipo=None) -> list[dict]`
  - Rota `GET /l/{loja_id}?tipo=` (HTML da vitrine).

- [ ] **Step 1: Criar `app/consultas.py`**

```python
from sqlalchemy import text

from app.db import engine


def loja_publica(loja_id):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, nome, whatsapp FROM vw_lojas_publicas WHERE id = :i"),
            {"i": loja_id},
        ).mappings().first()
        return dict(row) if row else None


def veiculos_publicos(loja_id, tipo=None):
    sql = (
        "SELECT id, tipo, marca, modelo, ano, cor, km, valor, foto_url "
        "FROM vw_veiculos_publicos WHERE loja_id = :l"
    )
    params = {"l": loja_id}
    if tipo:
        sql += " AND tipo = :t"
        params["t"] = tipo
    sql += " ORDER BY criado_em DESC"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Criar `app/templates/base.html`**

```html
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Catálogo{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 text-slate-800">
  {% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Criar `app/templates/vitrine.html`**

```html
{% extends "base.html" %}
{% block title %}{{ loja.nome }} — Estoque{% endblock %}
{% block body %}
<header class="bg-slate-800 text-white p-6">
  <h1 class="text-2xl font-bold">{{ loja.nome }}</h1>
  <p class="text-slate-300">Confira nosso estoque disponível</p>
</header>

<div class="max-w-6xl mx-auto p-6">
  <nav class="flex gap-2 mb-6">
    <a href="?" class="px-3 py-1 rounded {{ 'bg-slate-800 text-white' if not tipo else 'bg-white' }}">Todos</a>
    <a href="?tipo=moto" class="px-3 py-1 rounded {{ 'bg-slate-800 text-white' if tipo == 'moto' else 'bg-white' }}">Motos</a>
    <a href="?tipo=carro" class="px-3 py-1 rounded {{ 'bg-slate-800 text-white' if tipo == 'carro' else 'bg-white' }}">Carros</a>
  </nav>

  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    {% for v in veiculos %}
    <div class="bg-white rounded-xl shadow overflow-hidden">
      {% if v.foto_url %}<img src="{{ v.foto_url }}" alt="{{ v.modelo }}" class="w-full h-44 object-cover">{% endif %}
      <div class="p-4">
        <div class="font-semibold">{{ v.marca or '' }} {{ v.modelo }}</div>
        <div class="text-sm text-slate-500">{{ v.ano or '' }}{% if v.km %} · {{ v.km }} km{% endif %}{% if v.cor %} · {{ v.cor }}{% endif %}</div>
        <div class="text-xl font-bold mt-2">R$ {{ '%.2f'|format(v.valor) }}</div>
        {% if loja.whatsapp %}
        <a target="_blank" href="https://wa.me/{{ loja.whatsapp }}?text=Tenho%20interesse%20no%20{{ v.modelo | urlencode }}"
           class="mt-3 block text-center bg-emerald-600 text-white rounded p-2">Tenho interesse</a>
        {% endif %}
      </div>
    </div>
    {% else %}
    <p class="text-slate-500">Nenhum veículo disponível no momento.</p>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Adicionar a rota em `app/main.py`**

```python
from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app import consultas

templates = Jinja2Templates(directory="app/templates")


@app.get("/l/{loja_id}", response_class=HTMLResponse)
def vitrine(request: Request, loja_id: int, tipo: str | None = None):
    loja = consultas.loja_publica(loja_id)
    if not loja:
        return PlainTextResponse("Loja não encontrada", status_code=404)
    return templates.TemplateResponse("vitrine.html", {
        "request": request,
        "loja": loja,
        "tipo": tipo,
        "veiculos": consultas.veiculos_publicos(loja_id, tipo),
    })
```

- [ ] **Step 5: Verificar (manual)**

Suba o site (Task 4 traz o Docker; ou rode local com `DATABASE_URL_RO` apontando ao Postgres):
`.venv/Scripts/python -m uvicorn app.main:app --port 9100` e acesse `http://localhost:9100/l/1`.
Expected: a vitrine da loja 1 lista os veículos publicados; filtros "Motos/Carros" funcionam;
"Tenho interesse" abre o WhatsApp da loja com a mensagem preenchida.

- [ ] **Step 6: Commit**

```bash
git add catalogo-publico/app/consultas.py catalogo-publico/app/templates/ catalogo-publico/app/main.py
git commit -m "feat: vitrine pública por loja com filtro e interesse via WhatsApp"
```

---

### Task 4: Dockerizar o catálogo público (deploy independente)

**Files:**
- Create: `catalogo-publico/Dockerfile`
- Create: `catalogo-publico/.dockerignore`
- Create: `catalogo-publico/docker-compose.yml`
- Modify: `docker-compose.yml` (raiz)

**Interfaces:**
- Consumes: Postgres (read-only via `portal_ro`).
- Produces: site em `http://localhost:9100`; capaz de subir sozinho ou junto.

- [ ] **Step 1: Criar `catalogo-publico/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9100"]
```

- [ ] **Step 2: Criar `catalogo-publico/.dockerignore`**

```
.venv/
tests/
.pytest_cache/
__pycache__/
```

- [ ] **Step 3: Criar `catalogo-publico/docker-compose.yml` (isolado — venda separada)**

```yaml
services:
  catalogo:
    build: .
    ports:
      - "9100:9100"
    environment:
      - DATABASE_URL_RO=${DATABASE_URL_RO}
```

- [ ] **Step 4: Adicionar ao `docker-compose.yml` da raiz (stack combinado)**

Dentro de `services:`:
```yaml
  catalogo-publico:
    build: ./catalogo-publico
    ports:
      - "9100:9100"
    environment:
      - DATABASE_URL_RO=postgresql+psycopg://portal_ro:portal_ro@postgres:5432/financiamento
    depends_on:
      - postgres
```

- [ ] **Step 5: Subir e verificar ponta a ponta**

Run: `docker compose up -d --build catalogo-publico`
Acesse `http://localhost:9100/l/1`.
Expected: a vitrine carrega com os veículos publicados; interesse abre o WhatsApp. **Critério de aceite.**

- [ ] **Step 6: Commit**

```bash
git add catalogo-publico/Dockerfile catalogo-publico/.dockerignore catalogo-publico/docker-compose.yml docker-compose.yml
git commit -m "feat: dockeriza o catálogo público (deploy isolado e combinado)"
```

---

## Resultado deste plano

Um site público **vendável sozinho**: cada loja tem sua vitrine (`/l/{loja_id}`) com o estoque
que ela marcou como publicado, filtro moto/carro e botão que leva direto ao WhatsApp da loja.
Consome somente a API pública do Estoque; Motor, Bot, Portal e Vitrine seguem independentes e
podem ser combinados por contratos.

## Cobertura vs. pedido

- Outro site que serve de catálogo (Produto C) → todo este plano.
- Interligado: tudo que entra no estoque pode ir para a vitrine → flag `publicado` (Plano #4) + `vw_veiculos_publicos` (Task 1).
- Deploy/venda separada → app e compose próprios (Task 4).

## O que fica para depois

- Página de detalhe do veículo (`/l/{loja_id}/v/{id}`) com galeria de fotos.
- Domínio/subdomínio por loja (hoje é `/l/{loja_id}`); slug amigável.
- Registrar o clique "Tenho interesse" como lead/evento (analytics).
- Upload real de fotos (hoje `foto_url` manual).
