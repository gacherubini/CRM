# Autogestão de senha do lojista — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao lojista autogestão de senha no Portal: "esqueci minha senha" (reset por e-mail, deslogado) e troca de senha logado em Ajustes.

**Architecture:** Espelha o padrão de token single-use do convite do dono (`owner_invitations.py`). Uma tabela dedicada `RedefinicaoSenha`, um domínio `password_reset.py` (issue/consume), um router deslogado com templates standalone e a troca logada em `main.py` reusando o shell. Helpers de token e de validação de senha extraídos para módulos compartilhados.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, Jinja2, pytest. Tudo em `portal-gestao`.

## Global Constraints

- Rodar comandos a partir de `portal-gestao/` com `.venv/bin/python` (não importar o pacote `app` de outro produto).
- Senha: mínimo **12**, máximo **256** caracteres (unifica com o fluxo do dono). Não alterar o `SENHA_EQUIPE_MINIMA=10` do `equipe.py`.
- Token: `secrets.token_urlsafe(32)`, armazenado só como hash sha256; uso único; expira em **24h**. Nunca logar token/link.
- `POST /senha/esqueci` responde **sempre** neutro (anti-enumeração). Rate limit: não reemite se há token pendente criado há < 2 min.
- CSRF em todo POST (`csrf_valido`). Migrations: conferir `alembic upgrade head` e head correto do Portal (atual: `0017_vinculo_loja_pessoa`).
- Testes por produto: `.venv/bin/python -m pytest -q`. Falhas pré-existentes em `tests/test_funil.py` não são desta entrega.

---

### Task 1: Util de token compartilhado + refactor do convite

**Files:**
- Create: `portal-gestao/app/tokens.py`
- Modify: `portal-gestao/app/owner_invitations.py` (trocar `_token_hash`/`_as_utc` por import)
- Test: `portal-gestao/tests/test_tokens.py`

**Interfaces:**
- Produces: `app.tokens.token_hash(token: str) -> str` (sha256 hex), `app.tokens.as_utc(value: datetime) -> datetime`.

- [ ] **Step 1: Write the failing test**

```python
# portal-gestao/tests/test_tokens.py
from datetime import datetime, timezone

from app.tokens import as_utc, token_hash


def test_token_hash_is_sha256_hex_and_stable():
    h = token_hash("abc")
    assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert token_hash("abc") == h


def test_as_utc_assumes_utc_for_naive_and_converts_aware():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert as_utc(naive).tzinfo == timezone.utc
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert as_utc(aware) == aware
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_tokens.py`
Expected: FAIL (`ModuleNotFoundError: app.tokens`)

- [ ] **Step 3: Create the module**

```python
# portal-gestao/app/tokens.py
from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
```

- [ ] **Step 4: Refactor owner_invitations to reuse it**

Em `portal-gestao/app/owner_invitations.py`: adicione o import e remova as definições locais `_token_hash`/`_as_utc`, mantendo os nomes usados internamente via alias.

Adicionar após os imports existentes:
```python
from app.tokens import as_utc as _as_utc, token_hash as _token_hash
```
Remover as funções locais no fim do arquivo:
```python
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
```
Se após remover não sobrar uso de `hashlib`/`timezone` no arquivo, remova esses imports para não deixar import morto (confirme com `.venv/bin/python -m pyflakes app/owner_invitations.py` se disponível, senão inspeção visual).

- [ ] **Step 5: Run tests (novos + convite não regride)**

Run: `.venv/bin/python -m pytest -q tests/test_tokens.py tests/test_owner_invitation_endpoint.py tests/test_owner_invitations.py tests/test_owner_invitation_fixes.py tests/test_owner_invitation_multiloja.py`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/tokens.py portal-gestao/app/owner_invitations.py portal-gestao/tests/test_tokens.py
git commit -m "refactor(portal): extrai util de token (hash/as_utc) e reusa no convite"
```

---

### Task 2: Regras de senha compartilhadas

**Files:**
- Create: `portal-gestao/app/password_rules.py`
- Test: `portal-gestao/tests/test_password_rules.py`

**Interfaces:**
- Produces: `SENHA_MINIMA = 12`, `SENHA_MAXIMA = 256`, `class SenhaInvalida(ValueError)`, `validar_nova_senha(senha: str | None, confirmacao: str | None) -> str` (retorna a senha; levanta `SenhaInvalida`).

- [ ] **Step 1: Write the failing test**

```python
# portal-gestao/tests/test_password_rules.py
import pytest

from app.password_rules import SENHA_MINIMA, SenhaInvalida, validar_nova_senha


def test_valida_senha_ok():
    assert validar_nova_senha("senha-super-segura", "senha-super-segura") == "senha-super-segura"


def test_senha_curta_rejeitada():
    curta = "a" * (SENHA_MINIMA - 1)
    with pytest.raises(SenhaInvalida):
        validar_nova_senha(curta, curta)


def test_confirmacao_diferente_rejeitada():
    with pytest.raises(SenhaInvalida):
        validar_nova_senha("senha-super-segura", "outra-coisa-diferente")


def test_senha_none_rejeitada():
    with pytest.raises(SenhaInvalida):
        validar_nova_senha(None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_password_rules.py`
Expected: FAIL (`ModuleNotFoundError: app.password_rules`)

- [ ] **Step 3: Create the module**

```python
# portal-gestao/app/password_rules.py
from __future__ import annotations

SENHA_MINIMA = 12
SENHA_MAXIMA = 256


class SenhaInvalida(ValueError):
    pass


def validar_nova_senha(senha: str | None, confirmacao: str | None) -> str:
    senha = senha or ""
    if len(senha) < SENHA_MINIMA:
        raise SenhaInvalida(f"A senha deve ter pelo menos {SENHA_MINIMA} caracteres.")
    if len(senha) > SENHA_MAXIMA:
        raise SenhaInvalida("A senha deve ter no máximo 256 caracteres.")
    if senha != (confirmacao or ""):
        raise SenhaInvalida("A confirmação da senha não confere.")
    return senha
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_password_rules.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/password_rules.py portal-gestao/tests/test_password_rules.py
git commit -m "feat(portal): validador de senha compartilhado (min 12)"
```

---

### Task 3: Modelo RedefinicaoSenha + migration 0018

**Files:**
- Modify: `portal-gestao/app/models.py` (novo modelo, junto de `ConviteAcessoLoja`)
- Create: `portal-gestao/alembic/versions/0018_redefinicoes_senha.py`
- Test: `portal-gestao/tests/test_redefinicao_senha_model.py`

**Interfaces:**
- Produces: `app.models.RedefinicaoSenha` com colunas `id, usuario_id, token_hash, expira_em, usado_em, revogado_em, criado_em`. Tabela `redefinicoes_senha`.

- [ ] **Step 1: Write the failing test**

```python
# portal-gestao/tests/test_redefinicao_senha_model.py
from app.db import SessionLocal
from app.models import RedefinicaoSenha, Usuario, agora
from app.auth import hash_senha


def test_persistir_redefinicao_senha():
    with SessionLocal() as db:
        user = Usuario(
            email="reset@x.com", nome="Reset", senha_hash=hash_senha("x" * 12),
            papel="dono", loja_slug="loja-a", ativo=True,
        )
        db.add(user)
        db.flush()
        reg = RedefinicaoSenha(
            usuario_id=user.id, token_hash="h" * 64, expira_em=agora(), criado_em=agora(),
        )
        db.add(reg)
        db.commit()
        assert reg.id is not None
        assert reg.usado_em is None and reg.revogado_em is None
```

(O `conftest.py` recria as tabelas por teste via `Base.metadata.create_all`, então o modelo já vale nos testes.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_redefinicao_senha_model.py`
Expected: FAIL (`ImportError: cannot import name 'RedefinicaoSenha'`)

- [ ] **Step 3: Add the model**

Em `portal-gestao/app/models.py`, logo após a classe `ConviteAcessoLoja`:
```python
class RedefinicaoSenha(Base):
    __tablename__ = "redefinicoes_senha"
    __table_args__ = (
        Index("ix_redefinicoes_senha_usuario_id", "usuario_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    usuario_id: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revogado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
```

- [ ] **Step 4: Run model test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_redefinicao_senha_model.py`
Expected: PASS

- [ ] **Step 5: Create the migration**

```python
# portal-gestao/alembic/versions/0018_redefinicoes_senha.py
"""cria redefinicoes de senha

Revision ID: 0018_redefinicoes_senha
Revises: 0017_vinculo_loja_pessoa
"""

import sqlalchemy as sa
from alembic import op


revision = "0018_redefinicoes_senha"
down_revision = "0017_vinculo_loja_pessoa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redefinicoes_senha",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_redefinicoes_senha_usuario_id",
        "redefinicoes_senha",
        ["usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_redefinicoes_senha_usuario_id", table_name="redefinicoes_senha"
    )
    op.drop_table("redefinicoes_senha")
```

- [ ] **Step 6: Verify migration applies to head**

Run: `.venv/bin/python -m alembic upgrade head`
Expected: aplica `0018_redefinicoes_senha` sem erro. Confirme com `.venv/bin/python -m alembic current` → head `0018_redefinicoes_senha`.

- [ ] **Step 7: Commit**

```bash
git add portal-gestao/app/models.py portal-gestao/alembic/versions/0018_redefinicoes_senha.py portal-gestao/tests/test_redefinicao_senha_model.py
git commit -m "feat(portal): tabela redefinicoes_senha (modelo + migration 0018)"
```

---

### Task 4: Domínio password_reset (issue/consume)

**Files:**
- Create: `portal-gestao/app/password_reset.py`
- Test: `portal-gestao/tests/test_password_reset.py`

**Interfaces:**
- Consumes: `app.tokens.token_hash/as_utc`, `app.password_rules.validar_nova_senha/SenhaInvalida`, `app.auth.hash_senha`, `app.models.RedefinicaoSenha/Usuario/agora`.
- Produces:
  - `class PasswordResetInvalid(ValueError)`
  - `@dataclass(frozen=True) IssuedReset(usuario_id: str, email: str, nome: str, token: str, expira_em: datetime)`
  - `issue_reset(db, *, email: str) -> IssuedReset | None` (None se usuário inexistente/inativo ou rate-limited)
  - `consume_reset(db, *, token: str, senha: str, confirmacao: str) -> Usuario`

- [ ] **Step 1: Write the failing tests**

```python
# portal-gestao/tests/test_password_reset.py
from datetime import timedelta

import pytest

from app.auth import hash_senha, verifica_senha
from app.db import SessionLocal
from app.models import RedefinicaoSenha, Usuario, agora
from app.password_reset import (
    IssuedReset,
    PasswordResetInvalid,
    consume_reset,
    issue_reset,
)
from app.password_rules import SenhaInvalida
from app.tokens import token_hash


def _dono(db, email="dono@x.com", *, ativo=True):
    user = Usuario(
        email=email, nome="Dono", senha_hash=hash_senha("senha-antiga-1"),
        papel="dono", loja_slug="loja-a", ativo=ativo,
    )
    db.add(user)
    db.commit()
    return user


def test_issue_reset_usuario_ativo_gera_token():
    with SessionLocal() as db:
        _dono(db)
        issued = issue_reset(db, email="dono@x.com")
        assert isinstance(issued, IssuedReset)
        assert issued.email == "dono@x.com"
        reg = db.query(RedefinicaoSenha).one()
        assert reg.token_hash == token_hash(issued.token)


def test_issue_reset_inexistente_ou_inativo_retorna_none():
    with SessionLocal() as db:
        _dono(db, email="inativo@x.com", ativo=False)
        assert issue_reset(db, email="inativo@x.com") is None
        assert issue_reset(db, email="naoexiste@x.com") is None


def test_issue_reset_reemite_revoga_pendente_anterior():
    with SessionLocal() as db:
        _dono(db)
        primeiro = issue_reset(db, email="dono@x.com")
        # burla o rate limit recuando o criado_em do primeiro token
        reg = db.query(RedefinicaoSenha).one()
        reg.criado_em = agora() - timedelta(minutes=5)
        db.commit()
        segundo = issue_reset(db, email="dono@x.com")
        assert segundo is not None and segundo.token != primeiro.token
        pendentes = db.query(RedefinicaoSenha).filter(
            RedefinicaoSenha.usado_em.is_(None),
            RedefinicaoSenha.revogado_em.is_(None),
        ).all()
        assert len(pendentes) == 1
        assert pendentes[0].token_hash == token_hash(segundo.token)


def test_issue_reset_rate_limit_bloqueia_reemissao_rapida():
    with SessionLocal() as db:
        _dono(db)
        assert issue_reset(db, email="dono@x.com") is not None
        # token pendente recém-criado → segunda tentativa não gera novo
        assert issue_reset(db, email="dono@x.com") is None
        assert db.query(RedefinicaoSenha).count() == 1


def test_consume_reset_troca_a_senha_e_marca_usado():
    with SessionLocal() as db:
        user = _dono(db)
        issued = issue_reset(db, email="dono@x.com")
        consume_reset(
            db, token=issued.token,
            senha="senha-nova-segura", confirmacao="senha-nova-segura",
        )
        db.refresh(user)
        assert verifica_senha(user.senha_hash, "senha-nova-segura")
        reg = db.query(RedefinicaoSenha).one()
        assert reg.usado_em is not None


def test_consume_reset_token_ruim_ou_expirado_levanta_invalid():
    with SessionLocal() as db:
        _dono(db)
        with pytest.raises(PasswordResetInvalid):
            consume_reset(db, token="nao-existe", senha="senha-nova-segura", confirmacao="senha-nova-segura")
        issued = issue_reset(db, email="dono@x.com")
        reg = db.query(RedefinicaoSenha).one()
        reg.expira_em = agora() - timedelta(hours=1)
        db.commit()
        with pytest.raises(PasswordResetInvalid):
            consume_reset(db, token=issued.token, senha="senha-nova-segura", confirmacao="senha-nova-segura")


def test_consume_reset_senha_invalida_nao_consome_token():
    with SessionLocal() as db:
        _dono(db)
        issued = issue_reset(db, email="dono@x.com")
        with pytest.raises(SenhaInvalida):
            consume_reset(db, token=issued.token, senha="curta", confirmacao="curta")
        reg = db.query(RedefinicaoSenha).one()
        assert reg.usado_em is None  # token continua utilizável
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_password_reset.py`
Expected: FAIL (`ModuleNotFoundError: app.password_reset`)

- [ ] **Step 3: Create the domain module**

```python
# portal-gestao/app/password_reset.py
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models import RedefinicaoSenha, Usuario, agora
from app.password_rules import validar_nova_senha
from app.tokens import as_utc, token_hash

logger = logging.getLogger(__name__)

_LIFETIME = timedelta(hours=24)
_REEMISSAO_MINIMA = timedelta(minutes=2)


class PasswordResetInvalid(ValueError):
    pass


@dataclass(frozen=True)
class IssuedReset:
    usuario_id: str
    email: str
    nome: str
    token: str
    expira_em: datetime


def issue_reset(db: Session, *, email: str) -> IssuedReset | None:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    user = db.query(Usuario).filter(Usuario.email == normalized).first()
    if user is None or not user.ativo:
        return None

    now = agora()
    recente = (
        db.query(RedefinicaoSenha)
        .filter(
            RedefinicaoSenha.usuario_id == user.id,
            RedefinicaoSenha.usado_em.is_(None),
            RedefinicaoSenha.revogado_em.is_(None),
            RedefinicaoSenha.criado_em > now - _REEMISSAO_MINIMA,
        )
        .first()
    )
    if recente is not None:
        return None  # rate limit: já há token pendente recente

    db.query(RedefinicaoSenha).filter(
        RedefinicaoSenha.usuario_id == user.id,
        RedefinicaoSenha.usado_em.is_(None),
        RedefinicaoSenha.revogado_em.is_(None),
    ).update({RedefinicaoSenha.revogado_em: now}, synchronize_session=False)

    token = secrets.token_urlsafe(32)
    expira_em = now + _LIFETIME
    db.add(
        RedefinicaoSenha(
            usuario_id=user.id,
            token_hash=token_hash(token),
            expira_em=expira_em,
            criado_em=now,
        )
    )
    db.commit()
    return IssuedReset(
        usuario_id=user.id,
        email=user.email,
        nome=user.nome,
        token=token,
        expira_em=expira_em,
    )


def consume_reset(db: Session, *, token: str, senha: str, confirmacao: str) -> Usuario:
    normalized_token = (token or "").strip()
    if not normalized_token or len(normalized_token) > 256:
        raise PasswordResetInvalid("link inválido ou expirado")
    now = agora()
    registro = (
        db.query(RedefinicaoSenha)
        .filter(
            RedefinicaoSenha.token_hash == token_hash(normalized_token),
            RedefinicaoSenha.usado_em.is_(None),
            RedefinicaoSenha.revogado_em.is_(None),
        )
        .first()
    )
    if registro is None or as_utc(registro.expira_em) <= now:
        raise PasswordResetInvalid("link inválido ou expirado")
    user = db.get(Usuario, registro.usuario_id)
    if user is None or not user.ativo:
        raise PasswordResetInvalid("link inválido ou expirado")
    # Levanta SenhaInvalida ANTES de consumir o token (form pode ser reenviado).
    senha_validada = validar_nova_senha(senha, confirmacao)
    user.senha_hash = hash_senha(senha_validada)
    registro.usado_em = now
    db.commit()
    db.refresh(user)
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_password_reset.py`
Expected: PASS (7 testes)

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/password_reset.py portal-gestao/tests/test_password_reset.py
git commit -m "feat(portal): dominio de redefinicao de senha (issue/consume)"
```

---

### Task 5: Fluxo web "Esqueci minha senha" (deslogado)

**Files:**
- Create: `portal-gestao/app/web/password_reset.py`
- Create: `portal-gestao/app/templates/senha_esqueci.html`
- Create: `portal-gestao/app/templates/senha_redefinir.html`
- Modify: `portal-gestao/app/main.py` (registrar router)
- Modify: `portal-gestao/app/templates/login.html` (link "Esqueci minha senha" + flash `senha_redefinida`)
- Test: `portal-gestao/tests/test_password_reset_endpoint.py`

**Interfaces:**
- Consumes: `issue_reset`, `consume_reset`, `PasswordResetInvalid` (Task 4); `SenhaInvalida` (Task 2); `send_email`, `EmailMessage`; `settings.absolute_url`; `csrf_token`, `csrf_valido`.
- Produces: rotas `GET/POST /senha/esqueci`, `GET/POST /senha/redefinir`.

- [ ] **Step 1: Write the failing tests**

```python
# portal-gestao/tests/test_password_reset_endpoint.py
import os

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_senha, verifica_senha
from app.db import SessionLocal
from app.email import set_email_backend
from app.email.sender import ConsoleEmailBackend
from app.main import app
from app.models import RedefinicaoSenha, Usuario


@pytest.fixture
def client():
    set_email_backend(ConsoleEmailBackend("no-reply@revy.local"))
    yield TestClient(app)
    set_email_backend(None)


def _dono(email="dono@x.com", *, ativo=True):
    with SessionLocal() as db:
        db.add(Usuario(
            email=email, nome="Dono", senha_hash=hash_senha("senha-antiga-1"),
            papel="dono", loja_slug="loja-a", ativo=ativo,
        ))
        db.commit()


def _csrf(html: str) -> str:
    import re
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, "csrf não encontrado no HTML"
    return m.group(1)


def test_esqueci_responde_neutro_para_existente_e_inexistente(client):
    _dono()
    page = client.get("/senha/esqueci")
    csrf = _csrf(page.text)
    r_existe = client.post("/senha/esqueci", data={"csrf": csrf, "email": "dono@x.com"})
    r_nao = client.post("/senha/esqueci", data={"csrf": csrf, "email": "naoexiste@x.com"})
    assert r_existe.status_code == 200 and r_nao.status_code == 200
    assert "enviamos um link" in r_existe.text.lower()
    assert r_existe.text == r_nao.text  # resposta indistinguível


def test_reset_fluxo_feliz_troca_a_senha(client):
    _dono()
    page = client.get("/senha/esqueci")
    client.post("/senha/esqueci", data={"csrf": _csrf(page.text), "email": "dono@x.com"})
    with SessionLocal() as db:
        # o token cru não é persistido; para o teste, emitimos direto pelo domínio
        pass
    from app.password_reset import issue_reset
    with SessionLocal() as db:
        # revoga o do POST e cria um conhecido, recuando criado_em para burlar rate limit
        from datetime import timedelta
        from app.models import agora
        reg = db.query(RedefinicaoSenha).first()
        reg.criado_em = agora() - timedelta(minutes=5)
        db.commit()
        issued = issue_reset(db, email="dono@x.com")
        token = issued.token
    form = client.get(f"/senha/redefinir?token={token}")
    resp = client.post(
        "/senha/redefinir",
        data={
            "csrf": _csrf(form.text), "token": token,
            "senha": "senha-nova-segura", "senha_confirmacao": "senha-nova-segura",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?senha_redefinida=1"
    with SessionLocal() as db:
        user = db.query(Usuario).filter(Usuario.email == "dono@x.com").one()
        assert verifica_senha(user.senha_hash, "senha-nova-segura")


def test_redefinir_token_invalido_mostra_erro(client):
    form = client.get("/senha/redefinir?token=xxx")
    resp = client.post(
        "/senha/redefinir",
        data={
            "csrf": _csrf(form.text), "token": "xxx",
            "senha": "senha-nova-segura", "senha_confirmacao": "senha-nova-segura",
        },
    )
    assert resp.status_code == 422
    assert "inválido ou expirado" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_password_reset_endpoint.py`
Expected: FAIL (rotas 404 / router inexistente)

- [ ] **Step 3: Create the router**

```python
# portal-gestao/app/web/password_reset.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import csrf_token, csrf_valido
from app.config import settings
from app.db import get_db
from app.email import EmailMessage, send_email
from app.password_reset import PasswordResetInvalid, consume_reset, issue_reset
from app.password_rules import SenhaInvalida

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)

_NEUTRO = "Se houver uma conta com esse e-mail, enviamos um link para redefinir a senha."


@router.get("/senha/esqueci", response_class=HTMLResponse)
def esqueci_pagina(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="senha_esqueci.html",
        context={"csrf": csrf_token(request), "erro": None, "mensagem": None},
    )


@router.post("/senha/esqueci", response_class=HTMLResponse)
def esqueci_enviar(
    request: Request,
    email: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    if not csrf_valido(request, csrf):
        return templates.TemplateResponse(
            request=request,
            name="senha_esqueci.html",
            context={
                "csrf": csrf_token(request),
                "erro": "Sessão expirada. Recarregue a página.",
                "mensagem": None,
            },
            status_code=400,
        )
    resultado = issue_reset(db, email=email)
    if resultado is not None:
        link = settings.absolute_url(f"/senha/redefinir?token={resultado.token}")
        try:
            send_email(
                EmailMessage(
                    to=resultado.email,
                    subject="Redefinir sua senha da Revy",
                    text_body=(
                        "Recebemos um pedido para redefinir sua senha.\n"
                        f"Crie uma nova senha: {link}\n\n"
                        "O link expira em 24 horas. Se não foi você, ignore este e-mail."
                    ),
                    html_body=(
                        "<p>Recebemos um pedido para redefinir sua senha.</p>"
                        f"<p><a href=\"{link}\">Criar uma nova senha</a></p>"
                        "<p>O link expira em 24 horas. Se não foi você, ignore este e-mail.</p>"
                    ),
                )
            )
        except Exception:
            logger.exception(
                "falha ao enviar e-mail de redefinição de senha para %s",
                resultado.email,
            )
    # Resposta sempre neutra (anti-enumeração), com ou sem envio.
    return templates.TemplateResponse(
        request=request,
        name="senha_esqueci.html",
        context={"csrf": csrf_token(request), "erro": None, "mensagem": _NEUTRO},
    )


@router.get("/senha/redefinir", response_class=HTMLResponse)
def redefinir_pagina(
    request: Request, token: str = Query(default="", max_length=256)
):
    return templates.TemplateResponse(
        request=request,
        name="senha_redefinir.html",
        context={"csrf": csrf_token(request), "token": token, "erro": None},
    )


@router.post("/senha/redefinir", response_class=HTMLResponse)
def redefinir_enviar(
    request: Request,
    token: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    senha_confirmacao: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    def erro(msg: str, code: int):
        return templates.TemplateResponse(
            request=request,
            name="senha_redefinir.html",
            context={"csrf": csrf_token(request), "token": token, "erro": msg},
            status_code=code,
        )

    if not csrf_valido(request, csrf):
        return erro("Sessão expirada. Recarregue a página.", 403)
    try:
        consume_reset(db, token=token, senha=senha, confirmacao=senha_confirmacao)
    except SenhaInvalida as exc:
        return erro(str(exc), 422)
    except PasswordResetInvalid as exc:
        return erro(str(exc), 422)
    return RedirectResponse("/login?senha_redefinida=1", status_code=303)
```

- [ ] **Step 4: Create the templates**

```html
<!-- portal-gestao/app/templates/senha_esqueci.html -->
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>Esqueci minha senha — Revy</title>
  <link rel="stylesheet" href="/static/css/app.css">
</head>
<body class="login-page">
  <main class="login-layout">
    <section class="login-story">
      <span class="eyebrow">Revy</span>
      <h1>Recuperar acesso.</h1>
      <p>Informe seu e-mail e enviamos um link para criar uma nova senha.</p>
    </section>
    <section class="login-panel">
      <div class="login-card">
        <span class="brand-mark" style="display:inline-grid;margin-bottom:16px">R</span>
        <div><h2>Esqueci minha senha</h2></div>
        {% if erro %}<div class="alert error" role="alert">{{ erro }}</div>{% endif %}
        {% if mensagem %}<div class="alert success" role="status">{{ mensagem }}</div>{% endif %}
        {% if not mensagem %}
        <form method="post" action="/senha/esqueci" class="stack-form">
          <input type="hidden" name="csrf" value="{{ csrf }}">
          <label>E-mail<input type="email" name="email" autocomplete="email" required></label>
          <button class="button primary" type="submit">Enviar link</button>
        </form>
        {% endif %}
        <p><a href="/login">Voltar ao login</a></p>
      </div>
    </section>
  </main>
</body>
</html>
```

```html
<!-- portal-gestao/app/templates/senha_redefinir.html -->
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>Nova senha — Revy</title>
  <link rel="stylesheet" href="/static/css/app.css">
</head>
<body class="login-page">
  <main class="login-layout">
    <section class="login-story">
      <span class="eyebrow">Revy</span>
      <h1>Definir nova senha.</h1>
      <p>Escolha uma senha com pelo menos 12 caracteres.</p>
    </section>
    <section class="login-panel">
      <div class="login-card">
        <span class="brand-mark" style="display:inline-grid;margin-bottom:16px">R</span>
        <div><h2>Criar nova senha</h2></div>
        {% if erro %}<div class="alert error" role="alert">{{ erro }}</div>{% endif %}
        <form method="post" action="/senha/redefinir" class="stack-form">
          <input type="hidden" name="csrf" value="{{ csrf }}">
          <input type="hidden" name="token" value="{{ token }}">
          <label>Nova senha<input type="password" name="senha" minlength="12" maxlength="256" autocomplete="new-password" required></label>
          <label>Confirmar senha<input type="password" name="senha_confirmacao" minlength="12" maxlength="256" autocomplete="new-password" required></label>
          <button class="button primary" type="submit">Salvar nova senha</button>
        </form>
        <p><a href="/login">Voltar ao login</a></p>
      </div>
    </section>
  </main>
</body>
</html>
```

- [ ] **Step 5: Register the router in main.py**

Em `portal-gestao/app/main.py`, junto dos outros `app.include_router(...)` (perto da linha 313):
```python
from app.web.password_reset import router as password_reset_router
app.include_router(password_reset_router)
```
(Coloque o `import` junto dos demais imports de routers no topo, e o `include_router` junto dos outros.)

- [ ] **Step 6: Add link + flash in login.html**

Em `portal-gestao/app/templates/login.html`, logo após o `</form>` do login (após a linha do botão "Entrar"):
```html
        <p><a href="/senha/esqueci">Esqueci minha senha</a></p>
```
E acima do bloco `{% if erro %}` do login, adicione o aviso de senha redefinida:
```html
        {% if request.query_params.get('senha_redefinida') == '1' %}<div class="alert success" role="status">Senha redefinida. Faça login com a nova senha.</div>{% endif %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_password_reset_endpoint.py`
Expected: PASS (4 testes)

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/web/password_reset.py portal-gestao/app/templates/senha_esqueci.html portal-gestao/app/templates/senha_redefinir.html portal-gestao/app/main.py portal-gestao/app/templates/login.html portal-gestao/tests/test_password_reset_endpoint.py
git commit -m "feat(portal): fluxo 'esqueci minha senha' (reset por e-mail)"
```

---

### Task 6: Trocar senha logado (Ajustes)

**Files:**
- Modify: `portal-gestao/app/main.py` (rotas `GET/POST /conta/senha`, reusando `contexto()`)
- Create: `portal-gestao/app/templates/conta_senha.html`
- Modify: `portal-gestao/app/loja/navigation.py` (item "Senha" em Ajustes)
- Test: `portal-gestao/tests/test_conta_senha.py`

**Interfaces:**
- Consumes: `usuario_atual`, `verifica_senha`, `hash_senha`, `csrf_valido` (auth); `validar_nova_senha`, `SenhaInvalida` (Task 2); `contexto()`, `templates` (main.py).
- Produces: rotas `GET/POST /conta/senha`; item de nav "Senha" → `/conta/senha`.

- [ ] **Step 1: Write the failing tests**

```python
# portal-gestao/tests/test_conta_senha.py
import pytest
from fastapi.testclient import TestClient

from app.auth import hash_senha, verifica_senha
from app.db import SessionLocal
from app.main import app
from app.models import Usuario


@pytest.fixture
def client():
    return TestClient(app)


def _login(client, email="dono@x.com", senha="senha-antiga-1"):
    with SessionLocal() as db:
        db.add(Usuario(
            email=email, nome="Dono", senha_hash=hash_senha(senha),
            papel="dono", loja_slug="loja-a", ativo=True,
        ))
        db.commit()
    page = client.get("/login")
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    client.post("/login", data={"csrf": csrf, "email": email, "senha": senha}, follow_redirects=False)


def _csrf(html):
    import re
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_conta_senha_troca_com_sucesso(client):
    _login(client)
    page = client.get("/conta/senha")
    assert page.status_code == 200
    resp = client.post("/conta/senha", data={
        "csrf": _csrf(page.text),
        "senha_atual": "senha-antiga-1",
        "senha": "senha-nova-segura",
        "senha_confirmacao": "senha-nova-segura",
    })
    assert resp.status_code == 200
    with SessionLocal() as db:
        user = db.query(Usuario).filter(Usuario.email == "dono@x.com").one()
        assert verifica_senha(user.senha_hash, "senha-nova-segura")


def test_conta_senha_atual_errada_nao_troca(client):
    _login(client)
    page = client.get("/conta/senha")
    resp = client.post("/conta/senha", data={
        "csrf": _csrf(page.text),
        "senha_atual": "errada-demais",
        "senha": "senha-nova-segura",
        "senha_confirmacao": "senha-nova-segura",
    })
    assert resp.status_code == 400
    assert "senha atual" in resp.text.lower()
    with SessionLocal() as db:
        user = db.query(Usuario).filter(Usuario.email == "dono@x.com").one()
        assert verifica_senha(user.senha_hash, "senha-antiga-1")  # inalterada


def test_conta_senha_deslogado_redireciona_login(client):
    resp = client.get("/conta/senha", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_conta_senha.py`
Expected: FAIL (rota `/conta/senha` 404)

- [ ] **Step 3: Add the routes in main.py**

Confirme que estes nomes já estão importados no topo de `app/main.py` (a maioria já está: `usuario_atual`, `csrf_valido`, `hash_senha`; adicione o que faltar). Adicione também:
```python
from app.auth import verifica_senha
from app.password_rules import SenhaInvalida, validar_nova_senha
```
Adicione as rotas (perto das outras rotas autenticadas, ex.: após o bloco de `/logout`):
```python
@app.get("/conta/senha", response_class=HTMLResponse)
def conta_senha_pagina(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "conta_senha.html",
        contexto(request, usuario=usuario, db=db, erro=None, mensagem=None),
    )


@app.post("/conta/senha", response_class=HTMLResponse)
def conta_senha_salvar(
    request: Request,
    senha_atual: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    senha_confirmacao: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)

    def render(erro=None, mensagem=None, code=200):
        return templates.TemplateResponse(
            "conta_senha.html",
            contexto(request, usuario=usuario, db=db, erro=erro, mensagem=mensagem),
            status_code=code,
        )

    if not csrf_valido(request, csrf):
        return render(erro="Sessão expirada. Recarregue a página.", code=400)
    if not verifica_senha(usuario.senha_hash, senha_atual):
        return render(erro="Senha atual incorreta.", code=400)
    try:
        senha_validada = validar_nova_senha(senha, senha_confirmacao)
    except SenhaInvalida as exc:
        return render(erro=str(exc), code=400)
    usuario.senha_hash = hash_senha(senha_validada)
    db.commit()
    return render(mensagem="Senha alterada com sucesso.")
```

- [ ] **Step 4: Create the template**

```html
<!-- portal-gestao/app/templates/conta_senha.html -->
{% extends "base.html" %}
{% block conteudo %}
<section class="card">
  <h1>Trocar senha</h1>
  {% if erro %}<div class="alert error" role="alert">{{ erro }}</div>{% endif %}
  {% if mensagem %}<div class="alert success" role="status">{{ mensagem }}</div>{% endif %}
  <form method="post" action="/conta/senha" class="stack-form">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <label>Senha atual<input type="password" name="senha_atual" autocomplete="current-password" required></label>
    <label>Nova senha<input type="password" name="senha" minlength="12" maxlength="256" autocomplete="new-password" required></label>
    <label>Confirmar nova senha<input type="password" name="senha_confirmacao" minlength="12" maxlength="256" autocomplete="new-password" required></label>
    <button class="button primary" type="submit">Salvar</button>
  </form>
</section>
{% endblock %}
```

Nota de verificação: abra `portal-gestao/app/templates/base.html` e confirme o nome do bloco de conteúdo (`{% block conteudo %}`). Se o bloco tiver outro nome (ex.: `content`/`main`), ajuste o `{% block %}` do `conta_senha.html` para bater.

- [ ] **Step 5: Add the Ajustes nav item**

Em `portal-gestao/app/loja/navigation.py`, dentro do bloco que monta `ajustes` (antes do `sections.append(NavSection(title="Ajustes", ...))`, na altura do item "Equipe"):
```python
        ajustes.append(
            NavItem(
                label="Senha",
                href="/conta/senha",
                section="Ajustes",
                module=None,
                active_prefix="/conta/senha",
            )
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_conta_senha.py`
Expected: PASS (3 testes)

- [ ] **Step 7: Full suite + commit**

Run: `.venv/bin/python -m pytest -q`
Expected: verde, exceto as 3 falhas pré-existentes de `tests/test_funil.py`.

```bash
git add portal-gestao/app/main.py portal-gestao/app/templates/conta_senha.html portal-gestao/app/loja/navigation.py portal-gestao/tests/test_conta_senha.py
git commit -m "feat(portal): trocar senha logado em Ajustes"
```

---

## Self-review (cobertura do spec)

- Reset deslogado (form, e-mail, link 24h, uso único, resposta neutra, rate limit): Tasks 3–5. ✓
- Troca logado com senha atual: Task 6. ✓
- Tabela dedicada `RedefinicaoSenha` + migration: Task 3. ✓
- Validador de senha unificado (12): Task 2, usado em 4 e 6. ✓
- Util de token compartilhado (D1/reuso do convite): Task 1. ✓
- Anti-enumeração + neutralidade testadas: Task 5 (`test_esqueci_responde_neutro...`). ✓
- Link no login + flash: Task 5, steps 6. ✓
- Ajustes nav: Task 6, step 5. ✓
- Nunca logar token; logging de falha de e-mail: Task 5 (router usa `logger.exception` sem token). ✓
- Fora de escopo (Control, invalidar sessões, complexidade): não há tasks — correto. ✓
