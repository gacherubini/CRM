# Plano #2 — n8n + WhatsApp + Conversa (LEGADO — substituído pelo Plano #2A)

> **STATUS: LEGADO — NÃO EXECUTAR.** O plano válido do produto é o **Plano #2A — Chatbot Standalone Revendível**.
> Leads, consentimentos, mensagens, conversas e handoff pertencem a `chatbot-api/`, com banco e
> compose próprios. As amostras antigas que colocam essas tabelas/endpoints em `servico-simulacao/`
> estão supersedidas pelo Plano #0. O Motor é uma dependência opcional via `SimulationProvider`;
> Portal e Catálogo não são dependências. O critério final é subir e operar somente
> `deploy/chatbot-standalone/docker-compose.yml`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um cliente manda mensagem no WhatsApp, o bot (n8n + Claude) conversa, coleta e valida os dados com consentimento LGPD, chama o serviço de simulação do Plano #1 e devolve as opções dos 5 bancos formatadas — com o lead persistido no Postgres.

**Architecture:** A Evolution API expõe o WhatsApp e envia mensagens recebidas para um webhook do n8n. No n8n, um nó **AI Agent (Claude)** conduz a conversa usando **ferramentas HTTP** que apontam para o serviço Python do Plano #1 (`validar_cpf`, `simular`, `registrar_lead`, `apagar_dados`). O serviço Python ganha endpoints de persistência (leads + consentimento + expurgo LGPD), testados em pytest. A memória da conversa fica no Postgres via nó de memória do n8n.

**Tech Stack:** n8n (AI Agent / LangChain), Evolution API v2, Redis, Claude (Anthropic API), FastAPI + SQLAlchemy 2 + psycopg, Postgres 16, Docker Compose.

## Global Constraints

- **Pré-requisito:** Plano #1 concluído (serviço `servico-simulacao` no compose, endpoints `/health`, `/validar/cpf`, `/simular` funcionando).
- Serviço Python é o dono de **toda a lógica e persistência de negócio**; o n8n só orquestra conversa. Nenhuma regra de crédito/validação vive no n8n.
- Consentimento LGPD é **obrigatório antes** de coletar qualquer dado pessoal. Guardar `consentimento_em` (timestamp) + `consentimento_texto`.
- Retenção: leads não `contatado` são expurgados após **180 dias**.
- Base URL do serviço dentro da rede do compose: `http://servico-simulacao:8000`.
- Bancos e contrato do `/simular` inalterados em relação ao Plano #1.
- Segredos (Anthropic API key, Evolution API key, N8N_ENCRYPTION_KEY) via variáveis de ambiente, nunca commitados.
- TDD nas tasks Python (teste falha → implementa → passa → commit). Tasks de n8n/Evolution: montar na UI e verificar com evidência (mensagem enviada → resposta recebida).

---

### Task 1: Camada de persistência (leads + consentimento + expurgo)

**Files:**
- Create: `servico-simulacao/app/db.py`
- Create: `servico-simulacao/app/models_db.py`
- Create: `servico-simulacao/app/repositorio.py`
- Test: `servico-simulacao/tests/test_persistencia.py`
- Modify: `servico-simulacao/requirements.txt`

**Interfaces:**
- Consumes: nada do Plano #1 (camada nova).
- Produces:
  - `app.db`: `Base`, `engine`, `SessionLocal`, `get_db()` (generator), `init_db()`.
  - `app.models_db.Lead` (tabela `leads`).
  - `app.repositorio`:
    - `criar_lead(db, dados: dict) -> Lead`
    - `apagar_por_telefone(db, telefone: str) -> int`
    - `expurgar_antigos(db, dias: int = 180, agora: datetime | None = None) -> int`

- [ ] **Step 1: Adicionar dependências em `requirements.txt`**

Acrescente ao arquivo:
```
sqlalchemy==2.*
psycopg[binary]==3.*
```
E reinstale: `.venv/Scripts/pip install -r requirements.txt`

- [ ] **Step 2: Criar `app/db.py`**

```python
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    from app import models_db  # noqa: F401 — registra os modelos
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: Criar `app/models_db.py`**

```python
from datetime import datetime, date

from sqlalchemy import Integer, String, Numeric, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefone: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String, nullable=True)
    cpf: Mapped[str] = mapped_column(String, nullable=True)
    nascimento: Mapped[date] = mapped_column(Date, nullable=True)
    moto_modelo: Mapped[str] = mapped_column(String, nullable=True)
    ano: Mapped[int] = mapped_column(Integer, nullable=True)
    valor_moto: Mapped[float] = mapped_column(Numeric, nullable=True)
    entrada: Mapped[float] = mapped_column(Numeric, nullable=True)
    prazo_meses: Mapped[int] = mapped_column(Integer, nullable=True)
    renda: Mapped[float] = mapped_column(Numeric, nullable=True)
    status: Mapped[str] = mapped_column(String, default="novo")
    consentimento_em: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    consentimento_texto: Mapped[str] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Escrever os testes que falham**

Crie `tests/test_persistencia.py`:
```python
import pytest
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import repositorio
from app.models_db import Lead


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_criar_lead_grava_consentimento(db):
    lead = repositorio.criar_lead(db, {
        "telefone": "5511999999999",
        "nome": "Fulano",
        "cpf": "52998224725",
        "nascimento": date(1990, 5, 20),
        "consentimento": True,
        "consentimento_texto": "Aceito os termos",
    })
    assert lead.id is not None
    assert lead.consentimento_em is not None
    assert lead.status == "novo"


def test_apagar_por_telefone(db):
    repositorio.criar_lead(db, {"telefone": "5511888888888", "consentimento": True})
    removidos = repositorio.apagar_por_telefone(db, "5511888888888")
    assert removidos == 1
    assert db.query(Lead).count() == 0


def test_expurgar_antigos(db):
    lead = repositorio.criar_lead(db, {"telefone": "5511777777777", "consentimento": True})
    lead.criado_em = datetime.utcnow() - timedelta(days=200)
    db.commit()
    assert repositorio.expurgar_antigos(db, dias=180) == 1
```

- [ ] **Step 5: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_persistencia.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.repositorio'`.

- [ ] **Step 6: Implementar `app/repositorio.py`**

```python
from datetime import datetime, timedelta

from app.models_db import Lead


def criar_lead(db, dados: dict) -> Lead:
    lead = Lead(
        telefone=dados["telefone"],
        nome=dados.get("nome"),
        cpf=dados.get("cpf"),
        nascimento=dados.get("nascimento"),
        moto_modelo=dados.get("moto_modelo"),
        ano=dados.get("ano"),
        valor_moto=dados.get("valor_moto"),
        entrada=dados.get("entrada"),
        prazo_meses=dados.get("prazo_meses"),
        renda=dados.get("renda"),
        consentimento_em=datetime.utcnow() if dados.get("consentimento") else None,
        consentimento_texto=dados.get("consentimento_texto"),
        status="novo",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def apagar_por_telefone(db, telefone: str) -> int:
    q = db.query(Lead).filter(Lead.telefone == telefone)
    n = q.count()
    q.delete()
    db.commit()
    return n


def expurgar_antigos(db, dias: int = 180, agora: datetime = None) -> int:
    agora = agora or datetime.utcnow()
    limite = agora - timedelta(days=dias)
    q = db.query(Lead).filter(Lead.criado_em < limite, Lead.status != "contatado")
    n = q.count()
    q.delete()
    db.commit()
    return n
```

- [ ] **Step 7: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_persistencia.py -v`
Expected: PASS (3 testes).

- [ ] **Step 8: Commit**

```bash
git add servico-simulacao/app/db.py servico-simulacao/app/models_db.py servico-simulacao/app/repositorio.py servico-simulacao/tests/test_persistencia.py servico-simulacao/requirements.txt
git commit -m "feat: persistência de leads com consentimento e expurgo LGPD"
```

---

### Task 2: Endpoints de lead + expurgo + wiring no compose

**Files:**
- Modify: `servico-simulacao/app/main.py`
- Modify: `servico-simulacao/tests/test_api.py`
- Modify: `.gitignore`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `get_db`, `init_db` de `app.db`; `criar_lead`, `apagar_por_telefone`, `expurgar_antigos` de `app.repositorio`; `parse_nascimento` de `app.validadores`.
- Produces:
  - `POST /leads` body `LeadInput` → `{"id": int}`
  - `DELETE /leads?telefone=...` → `{"removidos": int}`
  - `POST /manutencao/expurgo` → `{"removidos": int}`
  - `LeadInput` (campos: `telefone: str`, opcionais `nome, cpf, nascimento(str), moto_modelo, ano, valor_moto, entrada, prazo_meses, renda`, `consentimento: bool = False`, `consentimento_texto: str | None`).

- [ ] **Step 1: Adicionar os testes que falham**

Adicione ao final de `tests/test_api.py`:
```python
def test_criar_lead_endpoint():
    r = client.post("/leads", json={
        "telefone": "5511999999999",
        "consentimento": True,
        "consentimento_texto": "Aceito",
    })
    assert r.status_code == 200
    assert isinstance(r.json()["id"], int)


def test_apagar_lead_endpoint():
    client.post("/leads", json={"telefone": "5511000000000", "consentimento": True})
    r = client.delete("/leads", params={"telefone": "5511000000000"})
    assert r.status_code == 200
    assert r.json()["removidos"] >= 1
```
E adicione, logo após `from app.main import app`, a sobrescrita do banco por SQLite em memória (no topo do arquivo):
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db

_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(_engine)
_TestSession = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: FAIL (404 em `/leads`).

- [ ] **Step 3: Implementar (adicionar a `app/main.py`)**

Adicione os imports no topo:
```python
from typing import Optional

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app import repositorio
from app.validadores import parse_nascimento
```
Logo após `app = FastAPI(...)`, inicialize o schema:
```python
init_db()
```
Adicione o modelo e os endpoints:
```python
class LeadInput(BaseModel):
    telefone: str
    nome: Optional[str] = None
    cpf: Optional[str] = None
    nascimento: Optional[str] = None
    moto_modelo: Optional[str] = None
    ano: Optional[int] = None
    valor_moto: Optional[float] = None
    entrada: Optional[float] = None
    prazo_meses: Optional[int] = None
    renda: Optional[float] = None
    consentimento: bool = False
    consentimento_texto: Optional[str] = None


@app.post("/leads")
def criar_lead_endpoint(dados: LeadInput, db: Session = Depends(get_db)):
    payload = dados.model_dump()
    if payload.get("nascimento"):
        payload["nascimento"] = parse_nascimento(payload["nascimento"])
    lead = repositorio.criar_lead(db, payload)
    return {"id": lead.id}


@app.delete("/leads")
def apagar_lead_endpoint(telefone: str, db: Session = Depends(get_db)):
    return {"removidos": repositorio.apagar_por_telefone(db, telefone)}


@app.post("/manutencao/expurgo")
def expurgo_endpoint(db: Session = Depends(get_db)):
    return {"removidos": repositorio.expurgar_antigos(db)}
```
Nota: `BaseModel` já está importado do Plano #1. Se não estiver, adicione `from pydantic import BaseModel`.

- [ ] **Step 4: Adicionar `*.db` ao `.gitignore`**

Acrescente ao `.gitignore` (na raiz do projeto):
```gitignore
*.db
```

- [ ] **Step 5: Rodar TODA a suíte e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS (todos os testes, incluindo os de `/simular` do Plano #1).

- [ ] **Step 6: Apontar o serviço para o Postgres no compose**

No `docker-compose.yml`, no serviço `servico-simulacao`, adicione `environment` e `depends_on`:
```yaml
  servico-simulacao:
    build: ./servico-simulacao
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+psycopg://n8n:n8n@postgres:5432/financiamento
    depends_on:
      - postgres
```

- [ ] **Step 7: Criar o banco `financiamento` no Postgres**

Run:
```bash
docker compose up -d postgres
docker compose exec postgres psql -U n8n -d n8n -c "CREATE DATABASE financiamento;"
```
Expected: `CREATE DATABASE` (ou erro "already exists", que é ok).

- [ ] **Step 8: Rebuild e verificar o endpoint contra o Postgres**

Run:
```bash
docker compose up -d --build servico-simulacao
curl -s -X POST http://localhost:8000/leads -H "Content-Type: application/json" -d "{\"telefone\":\"5511999999999\",\"consentimento\":true,\"consentimento_texto\":\"Aceito\"}"
```
Expected: `{"id": 1}` (ou id incremental). Confirma persistência:
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "SELECT id, telefone, consentimento_em FROM leads;"
```
Expected: uma linha com o telefone e `consentimento_em` preenchido.

- [ ] **Step 9: Commit**

```bash
git add servico-simulacao/app/main.py servico-simulacao/tests/test_api.py .gitignore docker-compose.yml
git commit -m "feat: endpoints de lead/expurgo e wiring com Postgres"
```

---

### Task 3: Subir a Evolution API e conectar o WhatsApp

**Files:**
- Modify: `docker-compose.yml`
- Create: `.env.example`

**Interfaces:**
- Consumes: `postgres` do compose.
- Produces: Evolution API em `http://localhost:8080`, com uma instância conectada a um número de WhatsApp; base interna `http://evolution:8080` para o n8n.

- [ ] **Step 1: Criar `.env.example` (documenta os segredos)**

```dotenv
EVOLUTION_API_KEY=troque-esta-chave-evolution
ANTHROPIC_API_KEY=coloque-sua-chave-claude
```
Crie também um `.env` real com valores verdadeiros (não commitado — já está no `.gitignore`).

- [ ] **Step 2: Adicionar Redis e Evolution ao `docker-compose.yml`**

Dentro de `services:`:
```yaml
  redis:
    image: redis:7-alpine

  evolution:
    image: atendai/evolution-api:v2.1.1
    ports:
      - "8080:8080"
    environment:
      - AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}
      - DATABASE_ENABLED=true
      - DATABASE_PROVIDER=postgresql
      - DATABASE_CONNECTION_URI=postgresql://n8n:n8n@postgres:5432/evolution
      - DATABASE_CONNECTION_CLIENT_NAME=evolution
      - CACHE_REDIS_ENABLED=true
      - CACHE_REDIS_URI=redis://redis:6379
      - CACHE_REDIS_PREFIX_KEY=evolution
      - CACHE_LOCAL_ENABLED=false
    depends_on:
      - postgres
      - redis
    volumes:
      - evolution_instances:/evolution/instances
```
E em `volumes:` adicione:
```yaml
  evolution_instances:
```
> Nota de versão: a Evolution API muda variáveis entre releases. Se o container não subir, confira as env vars da tag `v2.1.1` na doc oficial da Evolution e ajuste. O restante do plano não depende dos nomes exatos dessas envs.

- [ ] **Step 3: Criar o banco `evolution` no Postgres**

Run:
```bash
docker compose exec postgres psql -U n8n -d n8n -c "CREATE DATABASE evolution;"
```
Expected: `CREATE DATABASE` (ou "already exists").

- [ ] **Step 4: Subir a Evolution**

Run: `docker compose up -d redis evolution`
Depois: `docker compose logs evolution --tail=20`
Expected: logs indicando servidor iniciado na porta 8080, sem erro de conexão ao banco.

- [ ] **Step 5: Criar uma instância e conectar o número via QR**

Crie a instância:
```bash
curl -s -X POST http://localhost:8080/instance/create -H "Content-Type: application/json" -H "apikey: SEU_EVOLUTION_API_KEY" -d "{\"instanceName\":\"loja\",\"integration\":\"WHATSAPP-BAILEYS\",\"qrcode\":true}"
```
Depois abra o **QR** no navegador (Evolution Manager em `http://localhost:8080/manager`, login com a API key) e escaneie com o WhatsApp do número dedicado (Configurações → Aparelhos conectados).
Expected: status da instância vira `open`/`connected`.

- [ ] **Step 6: Verificar envio manual**

Run (troque o número de destino por um seu, formato `55DDDNUMERO`):
```bash
curl -s -X POST http://localhost:8080/message/sendText/loja -H "Content-Type: application/json" -H "apikey: SEU_EVOLUTION_API_KEY" -d "{\"number\":\"55SEUNUMERO\",\"text\":\"teste do bot\"}"
```
Expected: você recebe "teste do bot" no WhatsApp. **Este é o critério de aceite da task.**

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: adiciona Evolution API + Redis e conecta WhatsApp"
```

---

### Task 4: Webhook n8n recebe mensagem e responde (eco) — Fase 0

**Files:**
- Nenhum arquivo de código (workflow montado na UI do n8n).
- Ao final, exportar o workflow para: `n8n/workflow-eco.json`

**Interfaces:**
- Consumes: Evolution API (webhook de mensagens) e endpoint de envio.
- Produces: workflow n8n "Eco" que responde qualquer mensagem recebida com o mesmo texto — prova o ciclo WhatsApp → n8n → WhatsApp.

- [ ] **Step 1: Criar o workflow e o nó Webhook**

No n8n (`http://localhost:5678`): New Workflow → adicione nó **Webhook**.
- HTTP Method: `POST`
- Path: `whatsapp`
- Copie a **Production URL** (algo como `http://localhost:5678/webhook/whatsapp`; para a Evolution no compose, use `http://n8n:5678/webhook/whatsapp`).

- [ ] **Step 2: Registrar o webhook na Evolution**

Aponte a instância `loja` para o webhook do n8n:
```bash
curl -s -X POST http://localhost:8080/webhook/set/loja -H "Content-Type: application/json" -H "apikey: SEU_EVOLUTION_API_KEY" -d "{\"webhook\":{\"enabled\":true,\"url\":\"http://n8n:5678/webhook/whatsapp\",\"events\":[\"MESSAGES_UPSERT\"]}}"
```
Expected: resposta de sucesso da Evolution.

- [ ] **Step 3: Extrair telefone e texto da mensagem**

Adicione um nó **Set** (ou **Edit Fields**) após o Webhook, criando:
- `telefone` = `{{ $json.body.data.key.remoteJid.split('@')[0] }}`
- `texto` = `{{ $json.body.data.message.conversation }}`
> Os caminhos exatos dependem do payload da Evolution; use o nó **Webhook** em modo "Listen for Test Event", mande uma mensagem real e inspecione o JSON recebido para confirmar os caminhos antes de fixar.

- [ ] **Step 4: Responder com o mesmo texto (nó HTTP Request → Evolution)**

Adicione nó **HTTP Request**:
- Method: `POST`
- URL: `http://evolution:8080/message/sendText/loja`
- Header: `apikey` = sua Evolution API key
- Body (JSON):
```json
{ "number": "{{ $json.telefone }}", "text": "Você disse: {{ $json.texto }}" }
```

- [ ] **Step 5: Ativar e testar ponta a ponta**

Ative o workflow (toggle **Active**). Do seu WhatsApp pessoal, mande uma mensagem para o número do bot.
Expected: o bot responde "Você disse: <sua mensagem>". **Critério de aceite.**

- [ ] **Step 6: Exportar o workflow e commitar**

No n8n: menu do workflow → **Download** → salve como `n8n/workflow-eco.json` no projeto.
```bash
git add n8n/workflow-eco.json
git commit -m "feat: workflow n8n de eco (ciclo WhatsApp <-> n8n)"
```

---

### Task 5: Agente conversacional (Claude) com ferramentas + resposta formatada

**Files:**
- Workflow montado na UI; exportar ao final para: `n8n/workflow-bot.json`

**Interfaces:**
- Consumes: serviço Python (`http://servico-simulacao:8000`) via ferramentas; Evolution para enviar resposta; Claude via credencial Anthropic no n8n.
- Produces: workflow n8n "Bot" completo — recebe mensagem, conduz a conversa com consentimento LGPD, valida, simula, persiste o lead e responde formatado.

- [ ] **Step 1: Duplicar o workflow de eco**

Duplique `Eco` → renomeie para `Bot`. Mantenha o nó Webhook + o Set (`telefone`, `texto`). Remova o HTTP Request de eco (será substituído).

- [ ] **Step 2: Adicionar credencial do Claude**

Em Credentials → New → **Anthropic API**, cole a `ANTHROPIC_API_KEY`.

- [ ] **Step 3: Adicionar o nó AI Agent**

Adicione o nó **AI Agent** após o Set. Sub-nós:
- **Chat Model:** Anthropic Chat Model → model `claude-sonnet-5` (ou `claude-opus-4-8`), credencial do passo anterior.
- **Memory:** Postgres Chat Memory → conexão do Postgres do compose; **Session Key** = `{{ $json.telefone }}` (memória por número).
- **User message:** `{{ $json.texto }}`.

- [ ] **Step 4: Definir o System Prompt do agente**

No AI Agent → System Message, cole:
```
Você é o assistente de uma loja de motos no WhatsApp. Seu objetivo é simular
financiamento de moto para o cliente. Fale em português, tom simpático e direto.

REGRAS:
1. LGPD: ANTES de pedir qualquer dado pessoal (nome, CPF, nascimento), peça o
   consentimento explícito: explique que os dados serão usados só para a simulação
   e contato da loja, e pergunte se pode seguir. Só continue após um "sim".
2. Depois do consentimento, colete, um assunto por vez:
   - A moto: modelo, ano e valor aproximado.
   - Condições: valor de entrada e prazo desejado (em meses).
   - Dados: nome completo, CPF e data de nascimento. Renda é opcional.
3. Ao receber o CPF, use a ferramenta "validar_cpf". Se inválido, peça de novo.
4. Quando tiver valor_moto, entrada, prazo_meses, cpf e nascimento, use a
   ferramenta "simular" e apresente TODAS as opções de bancos de forma organizada:
   uma linha por banco com valor da parcela, taxa e nº de parcelas.
5. Assim que o cliente consentir e você tiver os dados, use "registrar_lead" para
   salvar (envie consentimento=true e o texto do consentimento que você usou).
6. Se o cliente pedir para apagar os dados, use "apagar_dados".
7. Nunca invente parcela ou taxa: os números vêm SEMPRE das ferramentas.

O telefone do cliente é: {{ $json.telefone }}
```

- [ ] **Step 5: Adicionar as ferramentas HTTP ao agente**

Adicione 4 sub-nós **HTTP Request Tool** ligados ao AI Agent. Em cada um, descreva bem o `Tool Description` (o agente escolhe pela descrição):

1. **validar_cpf** — "Valida um CPF brasileiro. Use quando o cliente informar o CPF."
   - POST `http://servico-simulacao:8000/validar/cpf`
   - Body JSON: `{ "cpf": "{cpf}" }` (parâmetro `cpf` definido como *from AI*).

2. **simular** — "Simula o financiamento nos bancos. Use quando tiver todos os dados."
   - POST `http://servico-simulacao:8000/simular`
   - Body JSON com parâmetros from-AI:
     `{ "cpf":"{cpf}", "nascimento":"{nascimento}", "valor_moto":{valor_moto}, "entrada":{entrada}, "prazo_meses":{prazo_meses}, "categoria":"moto" }`

3. **registrar_lead** — "Salva o lead do cliente com consentimento. Use após o consentimento e coleta dos dados."
   - POST `http://servico-simulacao:8000/leads`
   - Body JSON from-AI incluindo `telefone` = `{{ $json.telefone }}`, os campos coletados, `consentimento`: true, `consentimento_texto`.

4. **apagar_dados** — "Apaga os dados do cliente. Use se ele pedir para remover os dados."
   - DELETE `http://servico-simulacao:8000/leads?telefone={{ $json.telefone }}`

- [ ] **Step 6: Enviar a resposta do agente ao WhatsApp**

Adicione nó **HTTP Request** após o AI Agent:
- POST `http://evolution:8080/message/sendText/loja`
- Header `apikey` = Evolution API key
- Body: `{ "number": "{{ $('Set').item.json.telefone }}", "text": "{{ $json.output }}" }`
  (`$json.output` é a resposta textual do AI Agent.)

- [ ] **Step 7: Ativar e testar o fluxo completo (end-to-end)**

Ative o workflow `Bot` (desative o `Eco` para não conflitar no mesmo webhook path). Do WhatsApp pessoal, mande: "quero financiar uma moto".
Verifique a jornada completa:
1. Bot pede **consentimento** antes de dados pessoais. ✅
2. Coleta moto (modelo/ano/valor), entrada, prazo, nome, CPF, nascimento. ✅
3. CPF inválido é rejeitado (teste mandando `111.111.111-11`). ✅
4. Bot devolve as **5 opções de bancos** com parcela/taxa/nº parcelas. ✅
5. Confirma persistência:
   ```bash
   docker compose exec postgres psql -U n8n -d financiamento -c "SELECT telefone, nome, consentimento_em FROM leads ORDER BY id DESC LIMIT 1;"
   ```
   Expected: o lead recém-criado aparece com consentimento preenchido.
6. Mande "apagar meus dados" → confirme que o lead some da tabela. ✅

- [ ] **Step 8: Exportar e commitar**

No n8n: Download do workflow → `n8n/workflow-bot.json`.
```bash
git add n8n/workflow-bot.json
git commit -m "feat: bot conversacional com Claude, ferramentas e persistência"
```

---

### Task 6: Expurgo LGPD agendado (opcional, recomendado)

**Files:**
- Workflow montado na UI; exportar para: `n8n/workflow-expurgo.json`

**Interfaces:**
- Consumes: `POST http://servico-simulacao:8000/manutencao/expurgo`.
- Produces: workflow agendado que apaga leads > 180 dias.

- [ ] **Step 1: Criar workflow com Schedule Trigger**

Novo workflow → nó **Schedule Trigger** (ex.: diariamente às 03:00).

- [ ] **Step 2: Chamar o endpoint de expurgo**

Nó **HTTP Request** → POST `http://servico-simulacao:8000/manutencao/expurgo`.

- [ ] **Step 3: Ativar e testar manualmente**

Clique em **Execute Workflow**.
Expected: resposta `{"removidos": N}` (N ≥ 0). Ative o workflow.

- [ ] **Step 4: Exportar e commitar**

```bash
git add n8n/workflow-expurgo.json
git commit -m "feat: expurgo LGPD agendado (180 dias)"
```

---

### Task 7: Handoff — pausar o bot quando o humano assume ("até certo ponto")

**Files:**
- Modify: `servico-simulacao/app/models_db.py`
- Modify: `servico-simulacao/app/repositorio.py`
- Modify: `servico-simulacao/app/main.py`
- Test: `servico-simulacao/tests/test_handoff.py`
- Workflow `Bot` atualizado.

**Interfaces:**
- Consumes: `Base`, `get_db`.
- Produces:
  - Modelo `ConversaControle` (tabela `conversa_controle`, PK `telefone`, `bot_ativo`).
  - `repositorio.obter_estado(db, telefone) -> dict` (`{"bot_ativo": bool}`; default `True`).
  - `repositorio.definir_bot_ativo(db, telefone, ativo: bool) -> None`
  - `GET /conversas/{telefone}/estado` → `{"bot_ativo": bool}`
  - `PATCH /conversas/{telefone}/estado` body `{bot_ativo}` → `{"ok": true}`

- [ ] **Step 1: Adicionar o modelo em `app/models_db.py`**

```python
class ConversaControle(Base):
    __tablename__ = "conversa_controle"

    telefone: Mapped[str] = mapped_column(String, primary_key=True)
    bot_ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```
Nota: garanta `Boolean` no import do SQLAlchemy (`from sqlalchemy import Integer, String, Numeric, Date, DateTime, Boolean`).

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_handoff.py`:
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


def test_estado_default_ativo(db):
    assert repositorio.obter_estado(db, "5511999")["bot_ativo"] is True


def test_definir_e_ler(db):
    repositorio.definir_bot_ativo(db, "5511999", False)
    assert repositorio.obter_estado(db, "5511999")["bot_ativo"] is False
    repositorio.definir_bot_ativo(db, "5511999", True)
    assert repositorio.obter_estado(db, "5511999")["bot_ativo"] is True
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_handoff.py -v`
Expected: FAIL com `AttributeError: module 'app.repositorio' has no attribute 'obter_estado'`.

- [ ] **Step 4: Implementar no `app/repositorio.py`**

Atualize o import: `from app.models_db import Lead, Mensagem, ConversaControle`. E adicione:
```python
def obter_estado(db, telefone: str) -> dict:
    c = db.get(ConversaControle, telefone)
    return {"bot_ativo": True if c is None else c.bot_ativo}


def definir_bot_ativo(db, telefone: str, ativo: bool) -> None:
    c = db.get(ConversaControle, telefone)
    if c is None:
        db.add(ConversaControle(telefone=telefone, bot_ativo=ativo))
    else:
        c.bot_ativo = ativo
        c.atualizado_em = datetime.utcnow()
    db.commit()
```

- [ ] **Step 5: Adicionar os endpoints em `app/main.py`**

```python
@app.get("/conversas/{telefone}/estado")
def obter_estado_endpoint(telefone: str, db: Session = Depends(get_db)):
    return repositorio.obter_estado(db, telefone)


class EstadoInput(BaseModel):
    bot_ativo: bool


@app.patch("/conversas/{telefone}/estado")
def definir_estado_endpoint(telefone: str, dados: EstadoInput, db: Session = Depends(get_db)):
    repositorio.definir_bot_ativo(db, telefone, dados.bot_ativo)
    return {"ok": True}
```

- [ ] **Step 6: Rodar TODA a suíte e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS (tudo).

- [ ] **Step 7: (n8n) Gate do agente — só responde se `bot_ativo`**

No workflow `Bot`, entre o Set (telefone/texto) e o AI Agent, adicione:
- **HTTP Request** GET `http://servico-simulacao:8000/conversas/{{ $json.telefone }}/estado`.
- **IF**: condição `{{ $json.bot_ativo }}` é `true`.
  - **true** → segue para o AI Agent (responde normalmente).
  - **false** → **No-Op** (não responde; só registra a mensagem via `/mensagens`).

> Opcional (auto-pausa): se a mensagem recebida vier com `fromMe = true` (atendente
> respondeu manualmente pelo WhatsApp), chame `PATCH .../estado {bot_ativo:false}` para
> pausar o bot automaticamente. A distinção entre mensagem do atendente e a própria resposta
> do bot exige deduplicação — tratamento completo fica no Plano #6.

- [ ] **Step 8: Testar**

No WhatsApp, converse com o bot; depois, pelo Postgres, pause:
```bash
docker compose exec postgres psql -U n8n -d financiamento -c "INSERT INTO conversa_controle (telefone, bot_ativo) VALUES ('55SEUNUMERO', false) ON CONFLICT (telefone) DO UPDATE SET bot_ativo=false;"
```
Mande outra mensagem. Expected: o bot **não responde** (mensagem só é registrada). Volte
`bot_ativo=true` e confirme que ele volta a responder.

- [ ] **Step 9: Commit**

```bash
git add servico-simulacao/app/models_db.py servico-simulacao/app/repositorio.py servico-simulacao/app/main.py servico-simulacao/tests/test_handoff.py n8n/workflow-bot.json
git commit -m "feat: handoff — pausa o bot quando o humano assume a conversa"
```

---

### Task 8: Buffer de mensagens (agrupar mensagens rápidas)

**Files:**
- Workflow `Bot` atualizado (usa o Redis já existente do compose).

**Interfaces:**
- Consumes: Redis (`redis:6379`); Evolution (mensagens recebidas).
- Produces: no workflow `Bot`, o texto que chega ao AI Agent é a **concatenação** das mensagens que o cliente enviou em rajada, em vez de uma resposta por mensagem.

- [ ] **Step 1: Acumular a mensagem no Redis**

No `Bot`, logo após o Set (telefone/texto), adicione nós **Redis**:
- `RPUSH` na lista `buffer:{{ $json.telefone }}` com o valor `{{ $json.texto }}`.
- `SET` na chave `ts:{{ $json.telefone }}` com `{{ $now.toMillis() }}` (marca do horário desta mensagem). Guarde esse valor como `minha_ts`.

- [ ] **Step 2: Esperar a rajada terminar**

Adicione um nó **Wait** de ~8 segundos.

- [ ] **Step 3: Verificar se esta é a última mensagem da rajada**

Após o Wait:
- **Redis GET** `ts:{{ $json.telefone }}` → `ts_atual`.
- **IF**: `ts_atual == minha_ts`?
  - **false** (chegou mensagem mais nova) → **No-Op** (esta execução para; a mais recente processa a rajada).
  - **true** → segue para o Step 4.

- [ ] **Step 4: Puxar e concatenar as mensagens**

- **Redis LRANGE** `buffer:{{ $json.telefone }}` `0 -1` → lista de textos.
- **Redis DEL** `buffer:{{ $json.telefone }}` (limpa o buffer).
- Nó **Set/Code**: junte os textos com espaço/quebra de linha em `texto` e siga para o gate de handoff (Task 7) + AI Agent.

- [ ] **Step 5: Testar**

No WhatsApp, mande 3 mensagens em sequência rápida (ex.: "quero financiar", "uma cg 160",
"pode ser 48x").
Expected: o bot responde **uma vez**, considerando as 3 juntas — não três respostas picotadas.

- [ ] **Step 6: Exportar e commitar**

Download do `Bot` → `n8n/workflow-bot.json`.
```bash
git add n8n/workflow-bot.json
git commit -m "feat: buffer de mensagens (agrupa rajadas com Redis + Wait)"
```

---

## Resultado deste plano

Fluxo ponta a ponta funcionando com motor **mockado**: cliente conversa no WhatsApp, dá
consentimento, informa os dados, recebe as 5 simulações formatadas, e o lead fica salvo no
Postgres — com expurgo LGPD agendado. A troca do mock por RPA real (Plano #3) não exige
mudança alguma no n8n nem na conversa.

## Cobertura vs. design

- Fluxo conversacional + consentimento LGPD (design §5, §6) → Tasks 4, 5.
- Validação de CPF na conversa (design §5) → ferramenta `validar_cpf` (Task 5) + Plano #1 Task 3.
- Persistência de leads + consentimento (design §8) → Tasks 1, 2.
- Retenção 180 dias (design §6) → Tasks 1, 6.
- Canal WhatsApp Evolution (design §12) → Task 3.
- Orquestração n8n + Claude (design §3, §4) → Tasks 4, 5.
- Handoff / "automatizar até certo ponto" (bot pausa quando o humano assume) → Task 7.
- Buffer de mensagens (agrupar rajadas) → Task 8.

## O que fica para os Planos #3+

- Drivers Playwright reais por banco substituindo `simular_mock` (mesmo contrato).
- Persistir cada simulação na tabela `simulacoes` (design §8) — endpoint e escrita.
- Deploy de produção no Fly.io (n8n com volume + always-on, Evolution, Postgres, serviço Python).
