# Cadastro por WhatsApp para números autorizados — Implementation Plan

> **Status 2026-07-22:** base E5 + menu estoque **implementados na main**.  
> Continuação (bugs foto/telefone/menu + próximos E2E):  
> `docs/plans/2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md`.  
> Este arquivo = histórico de tasks da feature original.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que um número salvo e autorizado (gerido no Portal) mande `cadastro` no WhatsApp, abra uma sessão e cadastre veículos por texto, sem alterar o fluxo de atendimento ao cliente.

**Architecture:** A decisão de roteamento (cliente / ignorar / cadastro / controle) sai do gate do n8n e passa para um endpoint do Chatbot (`POST /v1/operacao/roteamento`), em Python testável. O n8n consulta esse endpoint e ramifica. O Portal ganha uma tela BFF que faz proxy da API de números autorizados que já existe no Chatbot. O caminho de fotos (E6) já funciona para números autorizados salvos e **não** é alterado.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2 (Chatbot); FastAPI + Jinja2 + httpx (Portal); n8n workflow JSON + validador Python.

## Global Constraints

- Integração entre produtos é **só HTTP**. Estoque é a fonte de verdade de veículos.
- Credenciais/tokens nunca no JSON versionado do n8n — só placeholders (`__CHATBOT_WEBHOOK_TOKEN__`, `__INSTANCE__`, `__EVOLUTION_KEY__`).
- Telefone normalizado com `app.operacao.normalizar_telefone` (só dígitos).
- Loja sempre resolvida pela instância no servidor — nunca vem do body do cliente.
- Fail-safe: se `/v1/operacao/roteamento` falhar, o n8n cai no gate antigo (`is_saved === false → cliente`, senão `ignorar`). O fluxo de cliente nunca quebra por causa desta feature.
- Gatilho de abertura fixo: texto normalizado (strip + casefold) igual a `cadastro`. Encerramento: `fim` ou `sair`. Sessão expira por inatividade em `CADASTRO_SESSION_TTL_SECONDS` (padrão 1800s).
- **Não commitar** os arquivos já modificados fora do escopo (`deploy/fly/*.sh`, `*/fly.toml`). Stage explícito por arquivo em cada commit.

---

### Task 1: Migration 0008 + colunas no modelo

**Files:**
- Modify: `chatbot-api/app/models_db.py` (classe `NumeroAutorizado`)
- Create: `chatbot-api/alembic/versions/0008_cadastro_sessao_e_nome.py`

**Interfaces:**
- Produces: `NumeroAutorizado.nome: str | None`, `NumeroAutorizado.cadastro_expira_em: datetime | None`.

- [ ] **Step 1: Adicionar colunas ao modelo**

Em `chatbot-api/app/models_db.py`, na classe `NumeroAutorizado`, logo após `foto_sessao_expira_em`:

```python
    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cadastro_expira_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 2: Criar a migration**

Criar `chatbot-api/alembic/versions/0008_cadastro_sessao_e_nome.py`:

```python
"""Nome e sessão de cadastro por número autorizado.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.add_column(sa.Column("nome", sa.String(length=120), nullable=True))
        batch.add_column(
            sa.Column(
                "cadastro_expira_em",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.drop_column("cadastro_expira_em")
        batch.drop_column("nome")
```

- [ ] **Step 3: Verificar migration (upgrade em SQLite temporário)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -c "from alembic.config import Config; from alembic import command; import tempfile,os; db=tempfile.mktemp(suffix='.db'); c=Config('alembic.ini'); c.set_main_option('sqlalchemy.url','sqlite:///'+db); command.upgrade(c,'head'); command.downgrade(c,'0007'); print('migration OK')"`
Expected: imprime `migration OK` sem erro.

- [ ] **Step 4: Commit**

```bash
git add chatbot-api/app/models_db.py chatbot-api/alembic/versions/0008_cadastro_sessao_e_nome.py
git commit -m "feat(chatbot): coluna nome e sessao de cadastro em numeros_autorizados (0008)"
```

---

### Task 2: `nome` na saída e no cadastro de número

**Files:**
- Modify: `chatbot-api/app/operacao.py` (`_para_saida_numero`, `adicionar_numero`)
- Modify: `chatbot-api/app/main.py` (`NumeroAutorizadoInput`, `adicionar_numero_autorizado`)
- Test: `chatbot-api/tests/test_operacao_veiculos.py`

**Interfaces:**
- Consumes: `NumeroAutorizado.nome` (Task 1).
- Produces: `adicionar_numero(db, loja_id, telefone, papel="vendedor", ativo=True, nome=None)`; saída de número inclui `"nome"`.

- [ ] **Step 1: Teste — número aceita e devolve nome**

Adicionar em `chatbot-api/tests/test_operacao_veiculos.py`:

```python
def test_numero_autorizado_guarda_nome(client, loja_a):
    r = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "5511988887777", "nome": "João Vendedor"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["nome"] == "João Vendedor"
    lista = client.get(
        "/v1/operacao/numeros-autorizados", headers=loja_a["headers"]
    ).json()["numeros"]
    assert any(n["nome"] == "João Vendedor" for n in lista)
```

- [ ] **Step 2: Rodar o teste (falha)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests/test_operacao_veiculos.py::test_numero_autorizado_guarda_nome -v`
Expected: FAIL (nome não é aceito/retornado).

- [ ] **Step 3: Implementar**

Em `app/operacao.py`, `_para_saida_numero` — adicionar `"nome": n.nome,` no dict.

`adicionar_numero` — nova assinatura e persistência:

```python
def adicionar_numero(
    db: Session,
    loja_id: str,
    telefone: str,
    papel: str = "vendedor",
    ativo: bool = True,
    nome: str | None = None,
) -> dict:
```

Dentro, no ramo `if existente:` adicionar antes do `db.commit()`:

```python
        if nome is not None:
            existente.nome = (nome or "").strip() or None
```

E no `NumeroAutorizado(...)` novo, adicionar `nome=(nome or "").strip() or None,`.

Em `app/main.py`, `NumeroAutorizadoInput` — adicionar campo:

```python
    nome: Optional[str] = Field(default=None, max_length=120)
```

E `adicionar_numero_autorizado` passa o nome:

```python
    return operacao.adicionar_numero(
        db, ctx.loja_id, dados.telefone, dados.papel, dados.ativo, dados.nome
    )
```

- [ ] **Step 4: Rodar o teste (passa)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests/test_operacao_veiculos.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/operacao.py chatbot-api/app/main.py chatbot-api/tests/test_operacao_veiculos.py
git commit -m "feat(chatbot): nome opcional no numero autorizado"
```

---

### Task 3: Lógica de roteamento e sessão de cadastro

**Files:**
- Modify: `chatbot-api/app/config.py` (TTL)
- Modify: `chatbot-api/app/operacao.py` (constantes + helpers + `decidir_roteamento`)
- Create: `chatbot-api/tests/test_roteamento.py`

**Interfaces:**
- Consumes: `_numero_autorizado_ativo`, `normalizar_telefone` (existentes); `NumeroAutorizado.cadastro_expira_em` (Task 1).
- Produces: `decidir_roteamento(db, loja_id, telefone, texto, is_saved) -> dict` com `{"acao": "cliente"|"ignorar"|"cadastro"|"cadastro_controle", "resposta": str | None}`.

- [ ] **Step 1: Config TTL**

Em `chatbot-api/app/config.py`, junto das outras sessões:

```python
CADASTRO_SESSION_TTL_SECONDS = max(
    0, int(os.getenv("CHATBOT_CADASTRO_SESSION_TTL_SECONDS", "1800"))
)
```

- [ ] **Step 2: Testes de roteamento**

Criar `chatbot-api/tests/test_roteamento.py`:

```python
"""Roteamento WhatsApp: cliente / ignorar / cadastro / controle de sessão."""
from datetime import datetime, timedelta, timezone

from app import operacao
from app.models_db import NumeroAutorizado


def _autorizar(client, loja, telefone, ativo=True):
    r = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": telefone, "ativo": ativo},
        headers=loja["headers"],
    )
    assert r.status_code == 201, r.text


def test_nao_salvo_vai_para_cliente(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000000", "oi", False)
    assert d["acao"] == "cliente"


def test_salvo_nao_autorizado_ignora(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000001", "oi", True)
    assert d["acao"] == "ignorar"


def test_autorizado_sem_sessao_texto_normal_ignora(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000002")
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000002", "bom dia", True)
    assert d["acao"] == "ignorar"


def test_autorizado_gatilho_abre_sessao(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000003")
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000003", " Cadastro ", True)
    assert d["acao"] == "cadastro_controle"
    assert "aberto" in d["resposta"].lower()
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000003")
        .first()
    )
    assert row.cadastro_expira_em is not None


def test_dados_dentro_da_sessao_vao_para_cadastro(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000004")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000004", "cadastro", True)
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000004", "Honda CG 160 2023 placa ABC1D23", True
    )
    assert d["acao"] == "cadastro"


def test_fim_encerra_sessao(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000005")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000005", "cadastro", True)
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000005", "fim", True)
    assert d["acao"] == "cadastro_controle"
    assert "encerrado" in d["resposta"].lower()
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000005")
        .first()
    )
    assert row.cadastro_expira_em is None


def test_sessao_expirada_volta_a_ignorar(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000006")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000006", "cadastro", True)
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000006")
        .first()
    )
    row.cadastro_expira_em = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000006", "Honda CG 160", True
    )
    assert d["acao"] == "ignorar"


def test_is_saved_desconhecido_trata_como_salvo(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000007", "oi", None)
    assert d["acao"] == "ignorar"
```

- [ ] **Step 3: Rodar (falha)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests/test_roteamento.py -q`
Expected: FAIL (`decidir_roteamento` não existe).

- [ ] **Step 4: Implementar helpers + decisão em `app/operacao.py`**

Adicionar constantes perto do topo (após `_TIPOS`):

```python
_GATILHO_CADASTRO = frozenset({"cadastro"})
_ENCERRAR_CADASTRO = frozenset({"fim", "sair"})
```

Adicionar `from app import config` já existe. Adicionar helpers (perto dos helpers de sessão de fotos):

```python
def _sessao_cadastro_aberta(numero: NumeroAutorizado) -> bool:
    expira = numero.cadastro_expira_em
    if expira is None:
        return False
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    return expira > datetime.now(timezone.utc)


def _abrir_ou_renovar_cadastro(db: Session, numero: NumeroAutorizado) -> None:
    ttl = max(1, config.CADASTRO_SESSION_TTL_SECONDS)
    numero.cadastro_expira_em = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    db.commit()


def _fechar_cadastro(db: Session, numero: NumeroAutorizado) -> None:
    numero.cadastro_expira_em = None
    db.commit()


def decidir_roteamento(
    db: Session,
    loja_id: str,
    telefone: str,
    texto: str | None,
    is_saved: bool | None,
) -> dict:
    """Decide como o n8n trata a mensagem. Ver plano/design para os ramos."""
    if is_saved is False:
        return {"acao": "cliente", "resposta": None}

    numero = _numero_autorizado_ativo(db, loja_id, telefone)
    if numero is None:
        return {"acao": "ignorar", "resposta": None}

    normal = (texto or "").strip().casefold()

    if _sessao_cadastro_aberta(numero):
        if normal in _ENCERRAR_CADASTRO:
            _fechar_cadastro(db, numero)
            return {"acao": "cadastro_controle", "resposta": "Cadastro encerrado."}
        _abrir_ou_renovar_cadastro(db, numero)
        return {"acao": "cadastro", "resposta": None}

    if normal in _GATILHO_CADASTRO:
        _abrir_ou_renovar_cadastro(db, numero)
        return {
            "acao": "cadastro_controle",
            "resposta": (
                "Modo cadastro aberto. Envie os dados do veículo e as fotos. "
                "Mande 'fim' para encerrar."
            ),
        }

    return {"acao": "ignorar", "resposta": None}
```

- [ ] **Step 5: Rodar (passa)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests/test_roteamento.py -q`
Expected: PASS (8 testes).

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/config.py chatbot-api/app/operacao.py chatbot-api/tests/test_roteamento.py
git commit -m "feat(chatbot): logica de roteamento e sessao de cadastro"
```

---

### Task 4: Endpoint `POST /v1/operacao/roteamento`

**Files:**
- Modify: `chatbot-api/app/main.py` (schema `RoteamentoInput` + rota)
- Test: `chatbot-api/tests/test_roteamento.py`

**Interfaces:**
- Consumes: `operacao.decidir_roteamento` (Task 3); `servico.resolver_loja_por_instancia`; `verificar_webhook_token`.
- Produces: `POST /v1/operacao/roteamento` → `{"acao": ..., "resposta": ...}`.

- [ ] **Step 1: Teste do endpoint**

Adicionar em `chatbot-api/tests/test_roteamento.py`:

```python
def test_endpoint_roteamento_fluxo(client, loja_a):
    inst = loja_a["instance"]
    client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "5511970000010"},
        headers=loja_a["headers"],
    )
    # não salvo -> cliente
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000011", "texto": "oi", "is_saved": False},
    )
    assert r.status_code == 200 and r.json()["acao"] == "cliente"
    # autorizado manda cadastro -> controle
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000010", "texto": "cadastro", "is_saved": True},
    )
    assert r.json()["acao"] == "cadastro_controle"
    # dado seguinte -> cadastro
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000010", "texto": "Honda CG 160 2023 ABC1D23", "is_saved": True},
    )
    assert r.json()["acao"] == "cadastro"
```

- [ ] **Step 2: Rodar (falha)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests/test_roteamento.py::test_endpoint_roteamento_fluxo -v`
Expected: FAIL (404 rota inexistente).

- [ ] **Step 3: Implementar schema + rota em `app/main.py`**

Schema (perto de `FotoVeiculoWebhookInput`):

```python
class RoteamentoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance: str
    telefone: str
    texto: Optional[str] = Field(default=None, max_length=config.WEBHOOK_MAX_TEXT_CHARS)
    is_saved: Optional[bool] = None

    @field_validator("instance")
    @classmethod
    def validar_instance(cls, value: str) -> str:
        return validar_identificador(
            value, nome="instance", limite=config.WEBHOOK_MAX_INSTANCE_CHARS
        )

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, value: str) -> str:
        return normalizar_telefone_webhook(value)
```

Rota (perto do webhook de foto):

```python
@app.post("/v1/operacao/roteamento")
def operacao_roteamento(
    dados: RoteamentoInput,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_webhook_token),
):
    """Decide como o n8n trata a mensagem (cliente/ignorar/cadastro/controle)."""
    loja = servico.resolver_loja_por_instancia(db, dados.instance)
    return operacao.decidir_roteamento(
        db, loja.id, dados.telefone, dados.texto, dados.is_saved
    )
```

- [ ] **Step 4: Rodar suíte do chatbot (passa)**

Run: `cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests -q`
Expected: PASS (139 + novos).

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_roteamento.py
git commit -m "feat(chatbot): endpoint /v1/operacao/roteamento"
```

---

### Task 5: Portal — cliente BFF de números autorizados

**Files:**
- Modify: `portal-gestao/app/clients/chatbot.py` (métodos)
- Test: `portal-gestao/tests/test_numeros_cadastro.py` (criar)

**Interfaces:**
- Produces: `ChatbotClient.listar_numeros_cadastro()`, `.adicionar_numero_cadastro(telefone, nome)`, `.remover_numero_cadastro(telefone)`.

- [ ] **Step 1: Teste do cliente (com transporte fake)**

Verificar primeiro como os testes existentes mockam o `ChatbotClient` (procurar em `portal-gestao/tests/` por `ChatbotClient` ou `respx`/`httpx_mock`). Criar `portal-gestao/tests/test_numeros_cadastro.py` seguindo o mesmo padrão de mock já usado no repositório. Estrutura mínima:

```python
from app.clients.chatbot import ChatbotClient


def _client(handler):
    import httpx
    transport = httpx.MockTransport(handler)
    c = ChatbotClient("http://chatbot", "tok", retries=0)
    c._transport = transport  # usado no _request (Step 3)
    return c


def test_listar_numeros_cadastro():
    def handler(req):
        import httpx
        assert req.url.path == "/v1/operacao/numeros-autorizados"
        return httpx.Response(200, json={"numeros": [{"telefone": "5511", "nome": "Ana", "ativo": True}]})
    c = _client(handler)
    assert c.listar_numeros_cadastro()[0]["nome"] == "Ana"
```

> Nota ao implementador: se os testes existentes do Portal já injetam transporte de outra forma (ex.: `respx.mock` sobre `httpx.Client`), use exatamente esse mecanismo em vez de `_transport`, e ajuste `_request` só se necessário. Não introduzir um segundo padrão de mock.

- [ ] **Step 2: Rodar (falha)**

Run: `cd portal-gestao && ./.venv/Scripts/python.exe -m pytest tests/test_numeros_cadastro.py -q`
Expected: FAIL (métodos inexistentes).

- [ ] **Step 3: Implementar métodos em `app/clients/chatbot.py`**

No fim da classe `ChatbotClient`:

```python
    # --- Operação: números autorizados a cadastrar ----------------------------

    def listar_numeros_cadastro(self) -> list[dict]:
        return self._request("GET", "/v1/operacao/numeros-autorizados")["numeros"]

    def adicionar_numero_cadastro(self, telefone: str, nome: str | None = None) -> dict:
        return self._request(
            "POST",
            "/v1/operacao/numeros-autorizados",
            json={"telefone": telefone, "nome": nome, "ativo": True},
        )

    def remover_numero_cadastro(self, telefone: str) -> dict:
        return self._request(
            "DELETE", f"/v1/operacao/numeros-autorizados/{telefone}"
        )
```

- [ ] **Step 4: Rodar (passa)**

Run: `cd portal-gestao && ./.venv/Scripts/python.exe -m pytest tests/test_numeros_cadastro.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/clients/chatbot.py portal-gestao/tests/test_numeros_cadastro.py
git commit -m "feat(portal): cliente BFF de numeros de cadastro"
```

---

### Task 6: Portal — página "Números de cadastro"

**Files:**
- Modify: `portal-gestao/app/main.py` (rotas GET/POST + link de navegação)
- Create: `portal-gestao/templates/operacao/numeros.html`
- Test: `portal-gestao/tests/test_numeros_cadastro.py`

**Interfaces:**
- Consumes: `ChatbotClient.listar/adicionar/remover_numero_cadastro` (Task 5); helpers de auth do Portal (`usuario_atual`, `redirecionar_login`, `contexto`, `get_chatbot_client`).

- [ ] **Step 1: Localizar os padrões de auth/nav**

Ler em `portal-gestao/app/main.py`: assinatura de `get_chatbot_client`, `usuario_atual`, `redirecionar_login`, `contexto`, e uma rota POST-form existente (ex.: estoque) para copiar o padrão de `Form(...)` + `RedirectResponse(..., 303)`. Ler `templates/base.html` (ou equivalente) para achar o bloco de navegação e o padrão de página.

- [ ] **Step 2: Teste da página (GET renderiza, POST adiciona)**

Adicionar em `portal-gestao/tests/test_numeros_cadastro.py` um teste com o `TestClient` do Portal autenticado (seguir o helper de login já usado nos outros testes de página; se existir fixture `usuario_logado`/`client_logado`, reutilizar). Esboço:

```python
def test_pagina_numeros_lista(client_logado, chatbot_stub):
    chatbot_stub.numeros = [{"telefone": "5511999", "nome": "Ana", "ativo": True}]
    r = client_logado.get("/app/operacao/numeros")
    assert r.status_code == 200
    assert "Ana" in r.text
```

> Se não houver fixtures equivalentes, seguir exatamente o mecanismo de login/stub dos testes de página já existentes no Portal (ex.: `test_estoque*.py`). Não criar um novo mecanismo.

- [ ] **Step 3: Rodar (falha)**

Run: `cd portal-gestao && ./.venv/Scripts/python.exe -m pytest tests/test_numeros_cadastro.py -q`
Expected: FAIL (rota/template inexistentes).

- [ ] **Step 4: Template `templates/operacao/numeros.html`**

Criar seguindo o layout base do Portal (estender o mesmo base das outras páginas — confirmar o nome no Step 1). Conteúdo essencial:

```html
{% extends "base.html" %}
{% block conteudo %}
<h1>Números de cadastro</h1>
<p>Números autorizados a cadastrar veículos pelo WhatsApp (mandam <strong>cadastro</strong> para começar).</p>
{% if integracao_erro %}<div class="erro">{{ integracao_erro }}</div>{% endif %}
<form method="post" action="/app/operacao/numeros">
  <input name="telefone" placeholder="5511999998888" required>
  <input name="nome" placeholder="Nome (opcional)">
  <button type="submit">Adicionar</button>
</form>
<table>
  <thead><tr><th>Telefone</th><th>Nome</th><th>Ativo</th><th></th></tr></thead>
  <tbody>
  {% for n in numeros %}
    <tr>
      <td>{{ mascarar_telefone(n.telefone) }}</td>
      <td>{{ n.nome or "—" }}</td>
      <td>{{ "sim" if n.ativo else "não" }}</td>
      <td>
        <form method="post" action="/app/operacao/numeros/remover">
          <input type="hidden" name="telefone" value="{{ n.telefone }}">
          <button type="submit">Remover</button>
        </form>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

> Ajustar nomes de bloco (`{% block conteudo %}`) e classes ao base real identificado no Step 1.

- [ ] **Step 5: Rotas em `app/main.py`**

Seguindo o padrão das rotas de página (mesma assinatura de `usuario_atual`/`get_chatbot_client` do Step 1):

```python
@app.get("/app/operacao/numeros", response_class=HTMLResponse)
def operacao_numeros(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    numeros, erro = [], None
    try:
        numeros = chatbot.listar_numeros_cadastro()
    except ChatbotIndisponivel as exc:
        erro = str(exc)
    return templates.TemplateResponse(
        "operacao/numeros.html",
        contexto(request, usuario, numeros=numeros, integracao_erro=erro),
    )


@app.post("/app/operacao/numeros")
def operacao_numeros_add(
    request: Request,
    telefone: str = Form(...),
    nome: str = Form(""),
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    try:
        chatbot.adicionar_numero_cadastro(telefone, nome.strip() or None)
    except ChatbotIndisponivel:
        pass
    return RedirectResponse("/app/operacao/numeros", status_code=303)


@app.post("/app/operacao/numeros/remover")
def operacao_numeros_remover(
    request: Request,
    telefone: str = Form(...),
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    try:
        chatbot.remover_numero_cadastro(telefone)
    except ChatbotIndisponivel:
        pass
    return RedirectResponse("/app/operacao/numeros", status_code=303)
```

Garantir imports: `Form` de fastapi e `ChatbotIndisponivel` de `app.clients.chatbot` (conferir se já importados).

Adicionar link de navegação no template base, junto dos outros itens do menu:

```html
<a href="/app/operacao/numeros">Números de cadastro</a>
```

- [ ] **Step 6: Rodar (passa)**

Run: `cd portal-gestao && ./.venv/Scripts/python.exe -m pytest tests/test_numeros_cadastro.py -q`
Expected: PASS.

- [ ] **Step 7: Suíte completa do Portal**

Run: `cd portal-gestao && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (251 + novos).

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/main.py portal-gestao/templates/operacao/numeros.html portal-gestao/templates portal-gestao/tests/test_numeros_cadastro.py
git commit -m "feat(portal): pagina de numeros de cadastro"
```

---

### Task 7: n8n — nó de roteamento e ramos

**Files:**
- Modify: `n8n/workflow-ai-nao-salvos.json`
- Modify: `n8n/validate_workflow.py`

**Interfaces:**
- Consumes: `POST /v1/operacao/roteamento` (Task 4).
- Produces: no workflow, um nó HTTP `Rotear operacao1` e ramos por `acao`.

**Contexto obrigatório antes de editar:** o roteamento entra **entre** o texto já resolvido (pós-transcrição, saída de `Aplicar transcricao1`/`Extrair1`) e o `Gate somente nao salvos1`. O nó de foto (`Salvar foto no estoque1`) **não muda** — o caminho de foto já é autorizado no Chatbot.

- [ ] **Step 1: Estudar a topologia atual**

Ler `n8n/workflow-ai-nao-salvos.json`: identificar o nó `Consultar contato na Evolution1`, `Gate somente nao salvos1`, `AI Agent1`, e como `isSaved`, `telefone` e o texto (`origem`) fluem. Mapear as `connections` de entrada/saída do gate.

- [ ] **Step 2: Adicionar o nó HTTP `Rotear operacao1`**

Novo nó `n8n-nodes-base.httpRequest` (typeVersion 4.2), inserido logo antes do gate, com:
- `method: POST`, `url: http://chatbot-api:8000/v1/operacao/roteamento`
- header `X-Webhook-Token: __CHATBOT_WEBHOOK_TOKEN__` (`sendHeaders: true`)
- `sendBody: true`, `specifyBody: json`, `jsonBody` (expressão) montando `{ instance: __INSTANCE__, telefone: <telefone da origem>, texto: <texto/transcrição>, is_saved: <chat.isSaved> }` a partir dos nós corretos (mesmos que o gate lê hoje).
- `options: { neverError: true }` para permitir o fallback (Step 4).

- [ ] **Step 3: Ramificar por `acao`**

Substituir o `Gate somente nao salvos1` por um nó de código que lê `acao` da resposta do roteamento e decide, mantendo o **texto/origem** no output (não descartar a transcrição — igual ao gate atual, que referencia `Aplicar transcricao1`):

```javascript
const rot = $('Rotear operacao1').first().json || {};
const extraida = $('Extrair1').first().json;
const origem = extraida.ehAudio ? $('Aplicar transcricao1').first().json : extraida;
const acao = rot.acao || null;
if (acao === 'cliente' || acao === 'cadastro') {
  return [{ json: { ...origem, acao } }];
}
if (acao === 'cadastro_controle') {
  return [{ json: { ...origem, acao, resposta_controle: rot.resposta } }];
}
return []; // ignorar
```

Encaminhar `cadastro_controle` para um nó que responde direto via Evolution (`/message/sendText/__INSTANCE__`) usando `resposta_controle`, sem passar pelo AI Agent. `cliente`/`cadastro` seguem para `AI Agent1` (o prompt já tem a regra 6 de `cadastrar_veiculo`). `ignorar` encerra.

> Se separar os ramos com um `Switch` for mais limpo que um `if` no code node + branch, use `n8n-nodes-base.switch`. O essencial: `cadastro_controle` responde e para; `cliente`/`cadastro` vão ao agente; `ignorar` para.

- [ ] **Step 4: Fallback se o roteamento cair**

Como o nó usa `neverError: true`, tratar resposta vazia/erro no code node: se `rot.acao` for indefinido, aplicar o gate antigo — `origem`/`chat.isSaved === false` → tratar como `cliente`, senão `ignorar`:

```javascript
if (!acao) {
  const chat = $('Consultar contato na Evolution1').first().json || {};
  return chat.isSaved === false ? [{ json: { ...origem, acao: 'cliente' } }] : [];
}
```

Inserir esse bloco no início do code node do Step 3 (após montar `origem`).

- [ ] **Step 5: Atualizar o validador**

Em `n8n/validate_workflow.py`, adicionar asserts:

```python
ROTEAMENTO_URL = "http://chatbot-api:8000/v1/operacao/roteamento"
...
rota_node = next(
    (n for n in data.get("nodes", []) if n.get("parameters", {}).get("url") == ROTEAMENTO_URL),
    None,
)
assert rota_node is not None, "nó de roteamento ausente"
rheaders = {
    h.get("name"): h.get("value")
    for h in rota_node["parameters"].get("headerParameters", {}).get("parameters", [])
}
assert rheaders.get(WEBHOOK_HEADER) == WEBHOOK_TOKEN_PLACEHOLDER, "roteamento sem token"
body = rota_node["parameters"].get("jsonBody", "")
assert "is_saved" in body and "telefone" in body, "roteamento sem telefone/is_saved"
```

- [ ] **Step 6: Rodar o validador**

Run: `cd .. && motor-simulacao/.venv/Scripts/python.exe n8n/validate_workflow.py`
Expected: imprime a linha de workflow válido, incluindo os asserts novos, sem erro.

- [ ] **Step 7: Commit**

```bash
git add n8n/workflow-ai-nao-salvos.json n8n/validate_workflow.py
git commit -m "feat(n8n): roteamento de operacao (cadastro por numero autorizado)"
```

---

### Task 8: Verificação integrada e docs

**Files:**
- Modify: `docs/contexto-compacto.md` (nota curta do novo fluxo + head 0008)

- [ ] **Step 1: Rodar as suítes tocadas**

Run:
```bash
cd chatbot-api && ./.venv/Scripts/python.exe -m pytest tests -q
cd ../portal-gestao && ./.venv/Scripts/python.exe -m pytest -q
cd .. && motor-simulacao/.venv/Scripts/python.exe n8n/validate_workflow.py
```
Expected: tudo PASS; validador OK.

- [ ] **Step 2: Atualizar contexto**

Em `docs/contexto-compacto.md`: na linha de migrations do Chatbot, trocar `0007` por `0008`; na tabela "Estado por produto", nota curta em Chatbot: "cadastro por número autorizado via gatilho `cadastro` + roteamento `/v1/operacao/roteamento`".

- [ ] **Step 3: Commit**

```bash
git add docs/contexto-compacto.md
git commit -m "docs: registra fluxo de cadastro por numero autorizado (head 0008)"
```

---

## Self-Review

**Spec coverage:**
- Roteamento centralizado no Chatbot → Tasks 3, 4. ✅
- Sessão por gatilho `cadastro`, encerra `fim`/`sair`/timeout → Task 3. ✅
- Migration `nome` + `cadastro_expira_em` (0007→0008) → Task 1. ✅
- `nome` na API → Task 2. ✅
- Fail-safe no n8n → Task 7 Step 4. ✅
- Portal BFF + tela → Tasks 5, 6. ✅
- Caminho de foto inalterado (já autorizado) → nota nas Tasks 3/7 (ajuste consciente ao design: o design citava re-rotear a foto; na verificação de código o caminho de foto já é autorizado no Chatbot e tem sessão própria, então re-rotear é complexidade desnecessária — YAGNI). ✅
- Validador n8n atualizado → Task 7 Step 5. ✅

**Placeholder scan:** Tasks 5 e 6 pedem para o implementador confirmar o mecanismo de mock/login já usado no Portal antes de codar o teste — isso é intencional (não inventar um segundo padrão), não um placeholder de lógica. Todo o código de produção está completo.

**Type consistency:** `decidir_roteamento(db, loja_id, telefone, texto, is_saved) -> {"acao","resposta"}` usado igual nas Tasks 3, 4 e 7. `adicionar_numero(..., nome=None)` e saída com `"nome"` consistentes entre Tasks 2, 5, 6.
