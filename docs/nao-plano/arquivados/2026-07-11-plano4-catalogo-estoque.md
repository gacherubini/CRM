# Plano #4 — Catálogo de Estoque (LEGADO — substituído pelo Plano #4A)

> **STATUS: LEGADO — NÃO EXECUTAR.** O plano válido é o **Plano #4A — Estoque API Independente**.
> migrações e dados próprios. Não pertence ao `servico-simulacao`. Chatbot e Portal o consomem por
> `CatalogProvider`/HTTP quando disponível e continuam operando sem ele. `loja_id` é obrigatório e
> derivado do contexto autenticado; nenhum endpoint aceita acesso cruzado apenas por query/body.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada loja cadastra seus veículos (motos e carros) no portal, podendo marcá-los como "publicado"; o bot consulta esse estoque na conversa e o catálogo público (Plano #5) exibe os publicados. Fonte única de estoque, compartilhada entre bot, portal e vitrine.

**Architecture:** O serviço de simulação (dono da base de negócio) ganha a tabela `veiculos` (com `tipo` moto/carro e flag `publicado`) e um CRUD HTTP (`POST/GET/DELETE /veiculos`). O **portal** gerencia via API. O **n8n** consulta o mesmo `GET /veiculos` durante a conversa. O **catálogo público** (Plano #5) lê `GET /veiculos?publicado=true`.

**Tech Stack:** FastAPI + SQLAlchemy (serviço), httpx + Jinja/HTMX (portal), n8n (ferramenta HTTP).

## Global Constraints

- **Pré-requisitos:** Planos #1–#3 concluídos.
- Catálogo é **genérico**: `tipo ∈ {moto, carro}`. Campos: `loja_id, tipo, marca, modelo, ano, cor, km, valor, status, publicado, foto_url`.
- CRUD vive no **serviço**; portal, n8n e vitrine consomem por HTTP. Portal escreve só via API.
- Estoque é por loja (`loja_id`); no portal, o veículo herda o `loja_id` do usuário logado.
- Busca por `modelo`/`marca` parcial, case-insensitive (`ILIKE %termo%`).
- `publicado` default `false` (só aparece na vitrine quando a loja marcar).
- **Comportamento do bot:** ao identificar o veículo, chamar `consultar_catalogo`; se houver match, usar o `valor` do estoque (não perguntar valor) e a `categoria` conforme o tipo (`moto` → "moto"; `carro` → "leve"); se não houver, informar indisponibilidade e listar os disponíveis.
- TDD nas funções/endpoints e no client do portal (httpx mockado). n8n: montar + verificar.

---

### Task 1: Tabela `veiculos` + repositório

**Files:**
- Modify: `servico-simulacao/app/models_db.py`
- Modify: `servico-simulacao/app/repositorio.py`
- Test: `servico-simulacao/tests/test_catalogo.py`

**Interfaces:**
- Consumes: `Base` de `app.db`.
- Produces:
  - Modelo `Veiculo` (tabela `veiculos`).
  - `repositorio.criar_veiculo(db, dados: dict) -> Veiculo`
  - `repositorio.listar_veiculos(db, loja_id=None, tipo=None, busca=None, publicado=None) -> list[Veiculo]`
  - `repositorio.remover_veiculo(db, veiculo_id: int) -> bool`

- [ ] **Step 1: Adicionar o modelo `Veiculo` em `app/models_db.py`**

```python
class Veiculo(Base):
    __tablename__ = "veiculos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loja_id: Mapped[int] = mapped_column(Integer, nullable=True)
    tipo: Mapped[str] = mapped_column(String)  # 'moto' | 'carro'
    marca: Mapped[str] = mapped_column(String, nullable=True)
    modelo: Mapped[str] = mapped_column(String)
    ano: Mapped[int] = mapped_column(Integer, nullable=True)
    cor: Mapped[str] = mapped_column(String, nullable=True)
    km: Mapped[int] = mapped_column(Integer, nullable=True)
    valor: Mapped[float] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(String, default="disponivel")
    publicado: Mapped[bool] = mapped_column(Boolean, default=False)
    foto_url: Mapped[str] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```
Nota: adicione `Boolean` ao import do SQLAlchemy no topo do arquivo (`from sqlalchemy import Integer, String, Numeric, Date, DateTime, Boolean`).

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_catalogo.py`:
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


def _veiculo(db, modelo="Honda CG 160", tipo="moto", loja_id=1, valor=16000, publicado=False):
    return repositorio.criar_veiculo(db, {
        "modelo": modelo, "tipo": tipo, "loja_id": loja_id, "valor": valor,
        "ano": 2023, "publicado": publicado,
    })


def test_criar_veiculo(db):
    m = _veiculo(db)
    assert m.id is not None
    assert m.status == "disponivel"
    assert m.publicado is False


def test_listar_por_busca_parcial(db):
    _veiculo(db, "Honda CG 160")
    _veiculo(db, "Yamaha Fazer 250")
    achados = repositorio.listar_veiculos(db, loja_id=1, busca="cg")
    assert [v.modelo for v in achados] == ["Honda CG 160"]


def test_listar_filtra_por_tipo(db):
    _veiculo(db, "Honda CG 160", tipo="moto")
    _veiculo(db, "Fiat Argo", tipo="carro")
    assert len(repositorio.listar_veiculos(db, tipo="carro")) == 1


def test_listar_apenas_publicados(db):
    _veiculo(db, "Honda CG 160", publicado=True)
    _veiculo(db, "Honda Biz", publicado=False)
    assert len(repositorio.listar_veiculos(db, publicado=True)) == 1


def test_remover_veiculo(db):
    m = _veiculo(db)
    assert repositorio.remover_veiculo(db, m.id) is True
    assert repositorio.remover_veiculo(db, 99999) is False
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_catalogo.py -v`
Expected: FAIL com `AttributeError: module 'app.repositorio' has no attribute 'criar_veiculo'`.

- [ ] **Step 4: Implementar no `app/repositorio.py`**

Atualize o import de modelos:
```python
from app.models_db import Lead, Mensagem, Veiculo
```
E adicione:
```python
def criar_veiculo(db, dados: dict) -> Veiculo:
    v = Veiculo(
        loja_id=dados.get("loja_id"),
        tipo=dados["tipo"],
        marca=dados.get("marca"),
        modelo=dados["modelo"],
        ano=dados.get("ano"),
        cor=dados.get("cor"),
        km=dados.get("km"),
        valor=dados["valor"],
        status=dados.get("status", "disponivel"),
        publicado=bool(dados.get("publicado", False)),
        foto_url=dados.get("foto_url"),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def listar_veiculos(db, loja_id=None, tipo=None, busca=None, publicado=None):
    q = db.query(Veiculo)
    if loja_id is not None:
        q = q.filter(Veiculo.loja_id == loja_id)
    if tipo:
        q = q.filter(Veiculo.tipo == tipo)
    if publicado is not None:
        q = q.filter(Veiculo.publicado == publicado)
    if busca:
        like = f"%{busca}%"
        q = q.filter((Veiculo.modelo.ilike(like)) | (Veiculo.marca.ilike(like)))
    return q.order_by(Veiculo.modelo).all()


def remover_veiculo(db, veiculo_id: int) -> bool:
    v = db.get(Veiculo, veiculo_id)
    if v is None:
        return False
    db.delete(v)
    db.commit()
    return True
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_catalogo.py -v`
Expected: PASS (5 testes).

- [ ] **Step 6: Commit**

```bash
git add servico-simulacao/app/models_db.py servico-simulacao/app/repositorio.py servico-simulacao/tests/test_catalogo.py
git commit -m "feat: tabela e repositório de veículos (motos e carros)"
```

---

### Task 2: Endpoints CRUD `/veiculos`

**Files:**
- Modify: `servico-simulacao/app/main.py`
- Modify: `servico-simulacao/tests/test_api.py`

**Interfaces:**
- Consumes: `criar_veiculo`, `listar_veiculos`, `remover_veiculo` de `app.repositorio`.
- Produces:
  - `POST /veiculos` body `VeiculoInput` → `{"id": int}`
  - `GET /veiculos?loja_id=&tipo=&busca=&publicado=` → `list[dict]`
  - `DELETE /veiculos/{id}` → `{"ok": bool}`
  - `VeiculoInput`: `tipo: str`, `modelo: str`, `valor: float`, opcionais `loja_id, marca, ano, cor, km, foto_url`, `publicado: bool = False`, `status: str = "disponivel"`.

- [ ] **Step 1: Adicionar os testes que falham**

Adicione ao final de `tests/test_api.py`:
```python
def test_criar_e_listar_veiculo():
    r = client.post("/veiculos", json={"tipo": "moto", "modelo": "Honda CG 160", "valor": 16000, "loja_id": 1, "ano": 2023})
    assert r.status_code == 200
    assert isinstance(r.json()["id"], int)

    r2 = client.get("/veiculos", params={"loja_id": 1, "busca": "cg"})
    assert "Honda CG 160" in [v["modelo"] for v in r2.json()]


def test_listar_publicados():
    client.post("/veiculos", json={"tipo": "carro", "modelo": "Fiat Argo", "valor": 60000, "loja_id": 1, "publicado": True})
    r = client.get("/veiculos", params={"publicado": True})
    assert all(v["publicado"] for v in r.json())


def test_remover_veiculo_endpoint():
    rid = client.post("/veiculos", json={"tipo": "moto", "modelo": "Yamaha Fazer", "valor": 20000, "loja_id": 1}).json()["id"]
    assert client.delete(f"/veiculos/{rid}").json()["ok"] is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: FAIL (404 em `/veiculos`).

- [ ] **Step 3: Implementar em `app/main.py`**

```python
class VeiculoInput(BaseModel):
    tipo: str
    modelo: str
    valor: float
    loja_id: Optional[int] = None
    marca: Optional[str] = None
    ano: Optional[int] = None
    cor: Optional[str] = None
    km: Optional[int] = None
    foto_url: Optional[str] = None
    publicado: bool = False
    status: str = "disponivel"


@app.post("/veiculos")
def criar_veiculo_endpoint(dados: VeiculoInput, db: Session = Depends(get_db)):
    v = repositorio.criar_veiculo(db, dados.model_dump())
    return {"id": v.id}


@app.get("/veiculos")
def listar_veiculos_endpoint(loja_id: Optional[int] = None, tipo: Optional[str] = None,
                             busca: Optional[str] = None, publicado: Optional[bool] = None,
                             db: Session = Depends(get_db)):
    veiculos = repositorio.listar_veiculos(db, loja_id, tipo, busca, publicado)
    return [
        {"id": v.id, "loja_id": v.loja_id, "tipo": v.tipo, "marca": v.marca,
         "modelo": v.modelo, "ano": v.ano, "cor": v.cor, "km": v.km,
         "valor": float(v.valor), "status": v.status, "publicado": v.publicado,
         "foto_url": v.foto_url}
        for v in veiculos
    ]


@app.delete("/veiculos/{veiculo_id}")
def remover_veiculo_endpoint(veiculo_id: int, db: Session = Depends(get_db)):
    return {"ok": repositorio.remover_veiculo(db, veiculo_id)}
```

- [ ] **Step 4: Rodar TODA a suíte e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS (tudo).

- [ ] **Step 5: Rebuild e verificar no container**

Run:
```bash
docker compose up -d --build servico-simulacao
curl -s -X POST http://localhost:8000/veiculos -H "Content-Type: application/json" -d "{\"tipo\":\"moto\",\"modelo\":\"Honda CG 160\",\"valor\":16000,\"loja_id\":1,\"ano\":2023,\"publicado\":true}"
curl -s "http://localhost:8000/veiculos?publicado=true"
```
Expected: POST retorna `{"id":...}`; GET retorna a lista com a Honda CG 160.

- [ ] **Step 6: Commit**

```bash
git add servico-simulacao/app/main.py servico-simulacao/tests/test_api.py
git commit -m "feat: endpoints CRUD de veículos (/veiculos)"
```

---

### Task 3: Página de catálogo no portal (motos e carros + publicar)

**Files:**
- Create: `portal-dashboards/app/catalogo.py`
- Create: `portal-dashboards/app/templates/catalogo.html`
- Modify: `portal-dashboards/app/main.py`
- Modify: `portal-dashboards/app/templates/dashboard.html`
- Test: `portal-dashboards/tests/test_catalogo_client.py`

**Interfaces:**
- Consumes: `settings.service_base_url`; `usuario_atual`, `escopo_loja_id`.
- Produces:
  - `app.catalogo.listar(loja_id=None, tipo=None, busca=None) -> list[dict]`
  - `app.catalogo.inserir(dados: dict) -> dict`
  - `app.catalogo.remover(veiculo_id: int) -> dict`
  - Rotas `GET /catalogo`, `POST /catalogo`, `POST /catalogo/{veiculo_id}/remover`.

- [ ] **Step 1: Escrever o teste do client (httpx mockado)**

Crie `tests/test_catalogo_client.py`:
```python
import httpx

from app import catalogo


def test_listar_repassa_params(monkeypatch):
    capturado = {}

    def fake_get(url, params, timeout):
        capturado["url"] = url
        capturado["params"] = params
        return httpx.Response(200, json=[{"id": 1, "modelo": "Honda CG 160", "valor": 16000, "tipo": "moto"}])

    monkeypatch.setattr(catalogo.httpx, "get", fake_get)
    out = catalogo.listar(loja_id=1, tipo="moto")
    assert capturado["url"].endswith("/veiculos")
    assert capturado["params"] == {"loja_id": 1, "tipo": "moto"}
    assert out[0]["modelo"] == "Honda CG 160"


def test_inserir_envia_json(monkeypatch):
    def fake_post(url, json, timeout):
        assert url.endswith("/veiculos")
        assert json["tipo"] == "carro"
        return httpx.Response(200, json={"id": 5})

    monkeypatch.setattr(catalogo.httpx, "post", fake_post)
    assert catalogo.inserir({"tipo": "carro", "modelo": "Fiat Argo", "valor": 60000})["id"] == 5
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_catalogo_client.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.catalogo'`.

- [ ] **Step 3: Implementar `app/catalogo.py`**

```python
import httpx

from app.config import settings


def listar(loja_id=None, tipo=None, busca=None):
    params = {}
    if loja_id is not None:
        params["loja_id"] = loja_id
    if tipo:
        params["tipo"] = tipo
    if busca:
        params["busca"] = busca
    r = httpx.get(f"{settings.service_base_url}/veiculos", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def inserir(dados: dict):
    r = httpx.post(f"{settings.service_base_url}/veiculos", json=dados, timeout=15)
    r.raise_for_status()
    return r.json()


def remover(veiculo_id: int):
    r = httpx.delete(f"{settings.service_base_url}/veiculos/{veiculo_id}", timeout=15)
    r.raise_for_status()
    return r.json()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_catalogo_client.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Criar `app/templates/catalogo.html`**

```html
{% extends "base.html" %}
{% block title %}Catálogo{% endblock %}
{% block body %}
<div class="max-w-5xl mx-auto p-6">
  <a href="/" class="text-slate-500 text-sm">&larr; Voltar</a>
  <h1 class="text-xl font-bold mb-4">Catálogo de veículos</h1>

  <form method="post" action="/catalogo" class="bg-white rounded-xl shadow p-4 grid grid-cols-6 gap-3 mb-6">
    <select name="tipo" class="border rounded p-2">
      <option value="moto">Moto</option>
      <option value="carro">Carro</option>
    </select>
    <input name="marca" placeholder="Marca" class="border rounded p-2">
    <input name="modelo" placeholder="Modelo" class="border rounded p-2 col-span-2" required>
    <input name="ano" type="number" placeholder="Ano" class="border rounded p-2">
    <input name="km" type="number" placeholder="Km" class="border rounded p-2">
    <input name="cor" placeholder="Cor" class="border rounded p-2">
    <input name="valor" type="number" step="0.01" placeholder="Valor" class="border rounded p-2 col-span-2" required>
    <input name="foto_url" placeholder="URL da foto (opcional)" class="border rounded p-2 col-span-2">
    <label class="flex items-center gap-2 text-sm"><input type="checkbox" name="publicado" value="true"> Publicar no site</label>
    <button class="bg-emerald-600 text-white rounded p-2 col-span-6">Adicionar ao estoque</button>
  </form>

  <table class="w-full bg-white rounded-xl shadow overflow-hidden">
    <thead class="bg-slate-800 text-white text-left">
      <tr><th class="p-2">Tipo</th><th class="p-2">Veículo</th><th class="p-2">Ano</th><th class="p-2">Valor</th><th class="p-2">Publicado</th><th></th></tr>
    </thead>
    <tbody>
      {% for v in veiculos %}
      <tr class="border-t">
        <td class="p-2 capitalize">{{ v.tipo }}</td>
        <td class="p-2">{{ v.marca or '' }} {{ v.modelo }}</td>
        <td class="p-2">{{ v.ano or '-' }}</td>
        <td class="p-2">R$ {{ '%.2f'|format(v.valor) }}</td>
        <td class="p-2">{{ 'sim' if v.publicado else 'não' }}</td>
        <td class="p-2 text-right">
          <form method="post" action="/catalogo/{{ v.id }}/remover">
            <button class="text-red-600 text-sm">remover</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr><td class="p-3 text-slate-500" colspan="6">Estoque vazio.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 6: Adicionar as rotas em `app/main.py`**

```python
from app import catalogo


@app.get("/catalogo", response_class=HTMLResponse)
def catalogo_pagina(request: Request):
    usuario = usuario_atual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("catalogo.html", {
        "request": request,
        "veiculos": catalogo.listar(loja_id=escopo_loja_id(usuario)),
    })


@app.post("/catalogo")
def catalogo_inserir(request: Request,
                     tipo: str = Form(...), modelo: str = Form(...), valor: float = Form(...),
                     marca: str = Form(None), ano: int = Form(None), km: int = Form(None),
                     cor: str = Form(None), foto_url: str = Form(None), publicado: str = Form(None)):
    usuario = usuario_atual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    catalogo.inserir({
        "tipo": tipo, "modelo": modelo, "valor": valor, "marca": marca, "ano": ano,
        "km": km, "cor": cor, "foto_url": foto_url, "publicado": publicado == "true",
        "loja_id": usuario.get("loja_id"),
    })
    return RedirectResponse("/catalogo", status_code=303)


@app.post("/catalogo/{veiculo_id}/remover")
def catalogo_remover(request: Request, veiculo_id: int):
    if not usuario_atual(request):
        return RedirectResponse("/login", status_code=303)
    catalogo.remover(veiculo_id)
    return RedirectResponse("/catalogo", status_code=303)
```

- [ ] **Step 7: Adicionar o link do catálogo no dashboard**

Em `app/templates/dashboard.html`, ao lado do botão "Simular":
```html
<a href="/catalogo" class="bg-slate-700 text-white px-4 py-2 rounded">Catálogo</a>
```

- [ ] **Step 8: Verificar (manual)**

Suba o portal, faça login, abra **Catálogo**, adicione uma moto e um carro (marque "Publicar" em um), confira a lista, remova um e veja sumir.
Expected: inserção/remoção refletem; a coluna "Publicado" mostra o que foi marcado.

- [ ] **Step 9: Commit**

```bash
git add portal-dashboards/app/catalogo.py portal-dashboards/app/templates/catalogo.html portal-dashboards/app/main.py portal-dashboards/app/templates/dashboard.html portal-dashboards/tests/test_catalogo_client.py
git commit -m "feat: catálogo de veículos (moto/carro) com flag publicar no portal"
```

---

### Task 4: Bot consulta o catálogo na conversa

**Files:**
- Workflow `Bot` (Plano #2) atualizado; reexportar para `n8n/workflow-bot.json`.

**Interfaces:**
- Consumes: `GET http://servico-simulacao:8000/veiculos?busca=...`.
- Produces: ferramenta `consultar_catalogo` no AI Agent + regras no system prompt.

- [ ] **Step 1: Adicionar a ferramenta `consultar_catalogo` ao AI Agent**

No AI Agent do workflow `Bot`, adicione um **HTTP Request Tool**:
- Nome: `consultar_catalogo`
- Descrição: "Consulta o estoque de veículos da loja por modelo/marca. Use assim que o cliente disser qual veículo quer."
- Method: `GET`
- URL: `http://servico-simulacao:8000/veiculos`
- Query param `busca` = `{modelo}` (from-AI).

- [ ] **Step 2: Atualizar o System Prompt (regra do catálogo)**

No AI Agent → System Message, substitua a regra 2 por:
```
2. Depois do consentimento, pergunte QUAL veículo o cliente quer (moto ou carro).
   Assim que ele disser, use a ferramenta "consultar_catalogo" com o modelo.
   - Se encontrar no estoque: confirme o veículo e use o "valor" retornado (NÃO pergunte
     o valor). Se houver mais de um, liste as opções e deixe ele escolher. Guarde o "tipo".
   - Se NÃO encontrar: avise gentilmente que não está no estoque e liste os disponíveis
     (chame "consultar_catalogo" sem termo).
   Depois siga para: entrada, prazo (meses) e os dados pessoais (nome, CPF, nascimento).
```
E na regra da simulação, ajuste a `categoria` da ferramenta "simular": `moto` → "moto",
`carro` → "leve" (conforme o tipo do veículo escolhido).

- [ ] **Step 3: Testar ponta a ponta**

Cadastre no portal uma moto ("Honda CG 160", R$ 16.000) e um carro ("Fiat Argo", R$ 60.000).
No WhatsApp: "quero financiar uma CG 160".
Expected: o bot confirma a CG 160, **não pergunta o valor**, segue para entrada/prazo/dados e
simula com R$ 16.000. Teste também com "quero um Argo" (carro) e com um inexistente ("uma
Ferrari") — nesse, ele avisa e lista o estoque.

- [ ] **Step 4: Reexportar e commitar**

Download do workflow `Bot` → `n8n/workflow-bot.json`.
```bash
git add n8n/workflow-bot.json
git commit -m "feat: bot consulta catálogo de veículos na conversa"
```

---

## Resultado deste plano

Estoque genérico (motos e carros) como dado real: cadastrado no portal com flag "publicar",
lido pelo bot na conversa e pela vitrine pública (Plano #5). O cliente que pede um veículo
disponível recebe simulação já com o preço do estoque. Fonte única, três consumidores.

## Cobertura vs. pedido

- Catálogo para carro **e** moto → campo `tipo` (Tasks 1–3).
- Interligado entre n8n, dashboard e catálogo → mesma API `/veiculos` (Tasks 2–4).
- Base para o catálogo público (Produto C) → flag `publicado` + `GET /veiculos?publicado=true` (Plano #5).

## O que fica para o Plano #5 e além

- **Produto C — Catálogo público (vitrine):** consome `GET /veiculos?publicado=true`.
- Marcar veículo como `vendido`/`reservado` (`PATCH /veiculos/{id}`).
- Upload real de fotos (hoje é `foto_url`).
- Match melhor de modelo (sinônimos/apelidos).
