# Plano #1 — Infra + Serviço de Simulação (LEGADO — substituído pelo Plano #1A)

> **STATUS: LEGADO — NÃO EXECUTAR.** O plano válido do produto é o **Plano #1A — Motor de Simulação Independente**.
> Ele não armazena leads, mensagens, usuários, vendas ou estoque e não depende de n8n/WhatsApp.
> O endpoint síncrono do mock é uma compatibilidade de desenvolvimento; o contrato revendível é
> versionado e baseado em recurso/job (`/v1/simulacoes`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ter, rodando localmente via Docker, um serviço HTTP em Python que recebe os dados de um cliente e devolve simulações de financiamento mockadas dos 5 bancos, além da infra local (n8n + Postgres) pronta para o Plano #2.

**Architecture:** Micro-serviço FastAPI isolado (`servico-simulacao/`) com o "motor de simulação" plugável — nesta fase, um motor **mock** que calcula parcelas pela fórmula Price. Validação de CPF/data/valores e a simulação vivem no Python (testável em pytest). Infra local sobe com `docker-compose` (Postgres + n8n + o serviço). O n8n só será cabeado no Plano #2.

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, Pydantic v2, pytest, Docker/Docker Compose, Postgres 16, n8n (imagem oficial).

## Global Constraints

- Contrato HTTP do motor é **fixo** e não muda entre fases (mock → Playwright):
  - Entrada `POST /simular`: `{cpf, nascimento, valor_moto, entrada, prazo_meses, renda?, categoria}`
  - Saída: `{resultados: [{banco, valor_parcela, taxa_am, n_parcelas, valor_financiado, status}]}`
- Bancos do mock (nomes exatos): `Santander`, `Bradesco`, `Fontcred`, `Pan`, `BV`.
- `taxa_am` na saída é em **percentual** (ex.: `1.79` = 1,79% a.m.); internamente as taxas são fração (`0.0179`).
- Ambiente do dev já tem: Docker 29, Docker Compose v5, Node v24, Python 3.14. Nada adicional a instalar.
- Pacote Python é `app`; testes importam via `from app...`; rodar pytest a partir de `servico-simulacao/`.
- Commits frequentes, um por task. TDD: teste falhando → implementação mínima → teste passando.

---

### Task 1: Scaffold do projeto + infra local (Postgres + n8n)

**Files:**
- Create: `.gitignore`
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: nada (primeira task).
- Produces: `docker-compose.yml` com serviços `postgres` (porta 5432) e `n8n` (porta 5678); rede default do compose usada pelas tasks seguintes.

- [ ] **Step 1: Inicializar git no projeto**

Rode a partir de `bot-whatsapp-financiamento/`:
```bash
git init
```
Expected: `Initialized empty Git repository in .../bot-whatsapp-financiamento/.git/`

- [ ] **Step 2: Criar `.gitignore`**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/

# Docker / dados locais
pg_data/
n8n_data/

# Ambiente
.env
```

- [ ] **Step 3: Criar `docker-compose.yml` com Postgres + n8n**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: n8n
      POSTGRES_PASSWORD: n8n
      POSTGRES_DB: n8n
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  n8n:
    image: docker.n8n.io/n8nio/n8n
    ports:
      - "5678:5678"
    environment:
      - N8N_SECURE_COOKIE=false
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=n8n
      - DB_POSTGRESDB_PASSWORD=n8n
      - N8N_ENCRYPTION_KEY=troque-esta-chave-antes-de-producao
    volumes:
      - n8n_data:/home/node/.n8n
    depends_on:
      - postgres

volumes:
  pg_data:
  n8n_data:
```

- [ ] **Step 4: Subir a infra e verificar**

Run: `docker compose up -d`
Depois: `docker compose ps`
Expected: serviços `postgres` e `n8n` com status `running`/`healthy`.
Abra `http://localhost:5678` no navegador. Expected: tela de setup do n8n carrega (criar usuário local).

- [ ] **Step 5: Commit**

```bash
git add .gitignore docker-compose.yml
git commit -m "chore: scaffold projeto com docker-compose (postgres + n8n)"
```

---

### Task 2: Scaffold do serviço Python + endpoint /health

**Files:**
- Create: `servico-simulacao/requirements.txt`
- Create: `servico-simulacao/pytest.ini`
- Create: `servico-simulacao/app/__init__.py`
- Create: `servico-simulacao/app/main.py`
- Test: `servico-simulacao/tests/test_api.py`

**Interfaces:**
- Consumes: nada do projeto.
- Produces: objeto FastAPI `app` em `app.main`; endpoint `GET /health` → `{"status": "ok"}`.

- [ ] **Step 1: Criar `requirements.txt`**

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
pydantic==2.*
pytest==8.*
httpx==0.27.*
```

- [ ] **Step 2: Criar `pytest.ini` (torna o pacote `app` importável nos testes)**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 3: Criar `app/__init__.py` vazio**

```python
```

- [ ] **Step 4: Instalar dependências (ambiente virtual local)**

Rode a partir de `servico-simulacao/`:
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```
Expected: instalação conclui sem erros. (No PowerShell use `.venv\Scripts\pip`.)

- [ ] **Step 5: Escrever o teste que falha**

Crie `tests/test_api.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 6: Rodar o teste e ver falhar**

Run (de `servico-simulacao/`): `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 7: Implementar o mínimo (`app/main.py`)**

```python
from fastapi import FastAPI

app = FastAPI(title="Serviço de Simulação")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 8: Rodar o teste e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add servico-simulacao/
git commit -m "feat: scaffold serviço FastAPI com endpoint /health"
```

---

### Task 3: Validação de CPF

**Files:**
- Create: `servico-simulacao/app/validadores.py`
- Test: `servico-simulacao/tests/test_validadores.py`

**Interfaces:**
- Consumes: nada.
- Produces: `valida_cpf(cpf: str) -> bool` em `app.validadores`.

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_validadores.py`:
```python
from app.validadores import valida_cpf


def test_valida_cpf_valido():
    assert valida_cpf("529.982.247-25") is True


def test_valida_cpf_invalido_digito():
    assert valida_cpf("529.982.247-24") is False


def test_valida_cpf_sequencia_repetida():
    assert valida_cpf("111.111.111-11") is False


def test_valida_cpf_tamanho_errado():
    assert valida_cpf("123") is False


def test_valida_cpf_none():
    assert valida_cpf(None) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_validadores.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.validadores'`.

- [ ] **Step 3: Implementar `app/validadores.py`**

```python
import re


def valida_cpf(cpf: str) -> bool:
    numeros = re.sub(r"\D", "", cpf or "")
    if len(numeros) != 11:
        return False
    if numeros == numeros[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(numeros[num]) * ((i + 1) - num) for num in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(numeros[i]):
            return False
    return True
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_validadores.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add servico-simulacao/app/validadores.py servico-simulacao/tests/test_validadores.py
git commit -m "feat: validação de CPF com dígito verificador"
```

---

### Task 4: Parse de data de nascimento, idade e valor monetário

**Files:**
- Modify: `servico-simulacao/app/validadores.py`
- Modify: `servico-simulacao/tests/test_validadores.py`

**Interfaces:**
- Consumes: `app.validadores`.
- Produces:
  - `parse_nascimento(texto: str) -> datetime.date | None`
  - `idade(nascimento: date, hoje: date | None = None) -> int`
  - `parse_valor(texto: str) -> float | None`

- [ ] **Step 1: Adicionar os testes que falham**

Adicione ao topo de `tests/test_validadores.py`:
```python
from datetime import date

from app.validadores import parse_nascimento, idade, parse_valor
```
E adicione os testes ao final do arquivo:
```python
def test_parse_nascimento_formatos():
    assert parse_nascimento("20/05/1990") == date(1990, 5, 20)
    assert parse_nascimento("1990-05-20") == date(1990, 5, 20)


def test_parse_nascimento_invalido():
    assert parse_nascimento("banana") is None


def test_idade_antes_do_aniversario():
    assert idade(date(2000, 6, 1), hoje=date(2026, 1, 1)) == 25


def test_idade_depois_do_aniversario():
    assert idade(date(2000, 1, 1), hoje=date(2026, 6, 1)) == 26


def test_parse_valor_variacoes():
    assert parse_valor("20 mil") == 20000
    assert parse_valor("R$ 20.000") == 20000
    assert parse_valor("20000") == 20000
    assert parse_valor("20.000,50") == 20000.50


def test_parse_valor_invalido():
    assert parse_valor("abc") is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_validadores.py -v`
Expected: FAIL com `ImportError: cannot import name 'parse_nascimento'`.

- [ ] **Step 3: Implementar (adicionar a `app/validadores.py`)**

Adicione no topo do arquivo:
```python
from datetime import date, datetime
```
E adicione as funções:
```python
def parse_nascimento(texto: str):
    if not texto:
        return None
    texto = str(texto).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def idade(nascimento: date, hoje: date = None) -> int:
    hoje = hoje or date.today()
    antes_do_aniversario = (hoje.month, hoje.day) < (nascimento.month, nascimento.day)
    return hoje.year - nascimento.year - (1 if antes_do_aniversario else 0)


def parse_valor(texto: str):
    if texto is None:
        return None
    s = str(texto).lower().strip().replace("r$", "").strip()
    multiplicador = 1000 if "mil" in s else 1
    s = s.replace("mil", "").strip()
    s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^0-9.]", "", s)
    if s == "" or s == ".":
        return None
    try:
        return float(s) * multiplicador
    except ValueError:
        return None
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_validadores.py -v`
Expected: PASS (todos os testes de validadores).

- [ ] **Step 5: Commit**

```bash
git add servico-simulacao/app/validadores.py servico-simulacao/tests/test_validadores.py
git commit -m "feat: parse de nascimento, cálculo de idade e parse de valor"
```

---

### Task 5: Fórmula de amortização (Price)

**Files:**
- Create: `servico-simulacao/app/motor/__init__.py`
- Create: `servico-simulacao/app/motor/amortizacao.py`
- Test: `servico-simulacao/tests/test_amortizacao.py`

**Interfaces:**
- Consumes: nada.
- Produces: `calcula_parcela_price(valor_financiado: float, taxa_mensal: float, n_parcelas: int) -> float` em `app.motor.amortizacao` (taxa em fração, ex.: `0.0179`).

- [ ] **Step 1: Criar `app/motor/__init__.py` vazio**

```python
```

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_amortizacao.py`:
```python
import pytest

from app.motor.amortizacao import calcula_parcela_price


def test_parcela_taxa_zero():
    assert calcula_parcela_price(1200, 0, 12) == 100.0


def test_parcela_price_conhecida():
    # PV=1000, i=1% a.m., n=12 -> ~88.85
    assert calcula_parcela_price(1000, 0.01, 12) == pytest.approx(88.85, abs=0.01)


def test_parcela_n_invalido():
    with pytest.raises(ValueError):
        calcula_parcela_price(1000, 0.01, 0)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_amortizacao.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.motor.amortizacao'`.

- [ ] **Step 4: Implementar `app/motor/amortizacao.py`**

```python
def calcula_parcela_price(valor_financiado: float, taxa_mensal: float, n_parcelas: int) -> float:
    if n_parcelas <= 0:
        raise ValueError("n_parcelas deve ser > 0")
    if taxa_mensal == 0:
        return round(valor_financiado / n_parcelas, 2)
    i = taxa_mensal
    fator = (i * (1 + i) ** n_parcelas) / ((1 + i) ** n_parcelas - 1)
    return round(valor_financiado * fator, 2)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_amortizacao.py -v`
Expected: PASS (3 testes).

- [ ] **Step 6: Commit**

```bash
git add servico-simulacao/app/motor/
git commit -m "feat: cálculo de parcela pela fórmula Price"
```

---

### Task 6: Modelos e motor mock

**Files:**
- Create: `servico-simulacao/app/motor/base.py`
- Create: `servico-simulacao/app/motor/mock.py`
- Test: `servico-simulacao/tests/test_mock.py`

**Interfaces:**
- Consumes: `calcula_parcela_price` de `app.motor.amortizacao`.
- Produces:
  - Modelos Pydantic `SimulacaoInput`, `ResultadoBanco`, `SimulacaoOutput` em `app.motor.base`.
  - `TAXAS_MOCK: dict[str, float]` e `simular_mock(dados: SimulacaoInput) -> list[ResultadoBanco]` em `app.motor.mock`.
  - `SimulacaoInput`: campos `cpf: str`, `nascimento: str`, `valor_moto: float`, `entrada: float = 0`, `prazo_meses: int`, `renda: float | None = None`, `categoria: str = "moto"`.
  - `ResultadoBanco`: `banco: str`, `valor_parcela: float`, `taxa_am: float`, `n_parcelas: int`, `valor_financiado: float`, `status: str = "ok"`.

- [ ] **Step 1: Criar os modelos `app/motor/base.py`**

```python
from typing import Optional, List

from pydantic import BaseModel


class SimulacaoInput(BaseModel):
    cpf: str
    nascimento: str
    valor_moto: float
    entrada: float = 0
    prazo_meses: int
    renda: Optional[float] = None
    categoria: str = "moto"


class ResultadoBanco(BaseModel):
    banco: str
    valor_parcela: float
    taxa_am: float
    n_parcelas: int
    valor_financiado: float
    status: str = "ok"


class SimulacaoOutput(BaseModel):
    resultados: List[ResultadoBanco]
```

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_mock.py`:
```python
from app.motor.base import SimulacaoInput
from app.motor.mock import simular_mock, TAXAS_MOCK


def _dados():
    return SimulacaoInput(
        cpf="529.982.247-25",
        nascimento="1990-05-20",
        valor_moto=20000,
        entrada=5000,
        prazo_meses=48,
    )


def test_mock_retorna_todos_bancos():
    resultados = simular_mock(_dados())
    assert {r.banco for r in resultados} == set(TAXAS_MOCK.keys())


def test_mock_valor_financiado_desconta_entrada():
    resultados = simular_mock(_dados())
    assert all(r.valor_financiado == 15000 for r in resultados)


def test_mock_parcela_positiva():
    resultados = simular_mock(_dados())
    assert all(r.valor_parcela > 0 for r in resultados)


def test_mock_taxa_am_em_percentual():
    resultados = simular_mock(_dados())
    # taxas mock estão entre 1% e 3% a.m.
    assert all(1.0 <= r.taxa_am <= 3.0 for r in resultados)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_mock.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.motor.mock'`.

- [ ] **Step 4: Implementar `app/motor/mock.py`**

```python
from app.motor.base import SimulacaoInput, ResultadoBanco
from app.motor.amortizacao import calcula_parcela_price

# Taxas fictícias por banco (a.m. em fração). Substituídas por dados reais nas fases de RPA.
TAXAS_MOCK = {
    "Santander": 0.0189,
    "Bradesco": 0.0185,
    "Fontcred": 0.0210,
    "Pan": 0.0172,
    "BV": 0.0179,
}


def simular_mock(dados: SimulacaoInput) -> list[ResultadoBanco]:
    valor_financiado = max(dados.valor_moto - dados.entrada, 0)
    resultados = []
    for banco, taxa in TAXAS_MOCK.items():
        parcela = calcula_parcela_price(valor_financiado, taxa, dados.prazo_meses)
        resultados.append(
            ResultadoBanco(
                banco=banco,
                valor_parcela=parcela,
                taxa_am=round(taxa * 100, 2),
                n_parcelas=dados.prazo_meses,
                valor_financiado=valor_financiado,
            )
        )
    return resultados
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_mock.py -v`
Expected: PASS (4 testes).

- [ ] **Step 6: Commit**

```bash
git add servico-simulacao/app/motor/base.py servico-simulacao/app/motor/mock.py servico-simulacao/tests/test_mock.py
git commit -m "feat: modelos e motor de simulação mock"
```

---

### Task 7: Endpoints /validar/cpf e /simular

**Files:**
- Modify: `servico-simulacao/app/main.py`
- Modify: `servico-simulacao/tests/test_api.py`

**Interfaces:**
- Consumes: `valida_cpf` de `app.validadores`; `SimulacaoInput`, `SimulacaoOutput` de `app.motor.base`; `simular_mock` de `app.motor.mock`.
- Produces:
  - `POST /validar/cpf` body `{"cpf": "..."}` → `{"valido": bool}`
  - `POST /simular` body = `SimulacaoInput` → `SimulacaoOutput`.

- [ ] **Step 1: Adicionar os testes que falham**

Adicione ao final de `tests/test_api.py`:
```python
def test_validar_cpf_valido():
    r = client.post("/validar/cpf", json={"cpf": "529.982.247-25"})
    assert r.status_code == 200
    assert r.json() == {"valido": True}


def test_validar_cpf_invalido():
    r = client.post("/validar/cpf", json={"cpf": "111.111.111-11"})
    assert r.json() == {"valido": False}


def test_simular_retorna_cinco_bancos():
    payload = {
        "cpf": "529.982.247-25",
        "nascimento": "1990-05-20",
        "valor_moto": 20000,
        "entrada": 5000,
        "prazo_meses": 48,
        "categoria": "moto",
    }
    r = client.post("/simular", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert len(body["resultados"]) == 5
    assert body["resultados"][0]["n_parcelas"] == 48
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: FAIL (404 nos endpoints novos).

- [ ] **Step 3: Implementar (substituir `app/main.py`)**

```python
from fastapi import FastAPI

from app.validadores import valida_cpf
from app.motor.base import SimulacaoInput, SimulacaoOutput
from app.motor.mock import simular_mock

app = FastAPI(title="Serviço de Simulação")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validar/cpf")
def validar_cpf(payload: dict):
    return {"valido": valida_cpf(payload.get("cpf", ""))}


@app.post("/simular", response_model=SimulacaoOutput)
def simular(dados: SimulacaoInput):
    return SimulacaoOutput(resultados=simular_mock(dados))
```

- [ ] **Step 4: Rodar TODA a suíte e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS (todos os testes de todos os arquivos).

- [ ] **Step 5: Commit**

```bash
git add servico-simulacao/app/main.py servico-simulacao/tests/test_api.py
git commit -m "feat: endpoints /validar/cpf e /simular"
```

---

### Task 8: Dockerizar o serviço e integrar no compose

**Files:**
- Create: `servico-simulacao/Dockerfile`
- Create: `servico-simulacao/.dockerignore`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: o serviço FastAPI de `app.main`.
- Produces: serviço `servico-simulacao` no compose, acessível em `http://localhost:8000` no host e como `http://servico-simulacao:8000` dentro da rede do compose (o n8n usará este último no Plano #2).

- [ ] **Step 1: Criar `servico-simulacao/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Criar `servico-simulacao/.dockerignore`**

```
.venv/
tests/
.pytest_cache/
__pycache__/
```

- [ ] **Step 3: Adicionar o serviço ao `docker-compose.yml`**

Adicione dentro de `services:` (antes de `volumes:`):
```yaml
  servico-simulacao:
    build: ./servico-simulacao
    ports:
      - "8000:8000"
```

- [ ] **Step 4: Buildar e subir**

Run: `docker compose up -d --build servico-simulacao`
Expected: build conclui e o container `servico-simulacao` fica `running`.

- [ ] **Step 5: Verificar o serviço no ar (end-to-end)**

Run:
```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/simular -H "Content-Type: application/json" -d "{\"cpf\":\"529.982.247-25\",\"nascimento\":\"1990-05-20\",\"valor_moto\":20000,\"entrada\":5000,\"prazo_meses\":48,\"categoria\":\"moto\"}"
```
Expected: `/health` → `{"status":"ok"}`; `/simular` → JSON com `resultados` contendo 5 bancos (`Santander`, `Bradesco`, `Fontcred`, `Pan`, `BV`) e parcelas positivas.

- [ ] **Step 6: Commit**

```bash
git add servico-simulacao/Dockerfile servico-simulacao/.dockerignore docker-compose.yml
git commit -m "feat: dockeriza serviço de simulação e integra no compose"
```

---

## Resultado deste plano

Ao final, `docker compose up -d --build` sobe **Postgres + n8n + serviço de simulação**, e o endpoint `POST /simular` devolve as 5 simulações mockadas. O serviço está pronto para o n8n consumir no Plano #2.

## O que fica para o Plano #2 (n8n + WhatsApp)

- Subir e conectar a **Evolution API** (WhatsApp via QR) no compose.
- Workflow n8n: webhook de recebimento → nó do **Claude** (coleta/entende dados) → chamadas a `/validar/cpf` e `/simular` → formatação e resposta no WhatsApp.
- Persistência de leads/consentimento no Postgres (Fase 2 do design).
- Rotina de expurgo LGPD (6 meses).

## O que fica para os Planos #3+ (motor real)

- Substituir o motor mock por **drivers Playwright** por banco (`app/motor/drivers/*.py`),
  mantendo o mesmo contrato `/simular`. Começar pelo portal mais simples / BV.
- Deploy de produção no **Fly.io** (n8n com volume + `min_machines_running=1`, Evolution sempre-on, Postgres, serviço Python).
