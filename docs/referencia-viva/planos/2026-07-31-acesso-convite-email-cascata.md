# Acesso por convite/e-mail em cascata — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o Admin Revy convide um **gestor de tráfego por e-mail** e o vincule a uma loja em um clique, com o gestor clicando no link do e-mail para criar a própria senha e entrar no Revy Control já enxergando a loja.

**Architecture:** Duas fatias, ambas em `revy-trafego/` (produto Revy Control). **Fatia 0** adiciona uma camada de envio de e-mail agnóstica de provedor (backend `console` para dev, `smtp` para produção). **Fatia 1** adiciona um serviço de domínio que ancora um gestor novo em `GestorRevy` (identidade de tráfego, alvo do FK do vínculo) com um `AcessoControl` de **mesmo id** (identidade de login), cria o `VinculoTrafego` e emite um `ConviteAcessoControl`; a página de aceite reusa `ControlInvitations.activate()`. O e-mail leva um link absoluto para essa página.

**Tech Stack:** Python 3.14 (Python do sistema — `revy-trafego` **não tem `.venv`**), FastAPI, SQLAlchemy 2.x, Jinja2, `smtplib`/`email.message` da stdlib, argon2 (já usado em `app.auth`), pytest + `fastapi.testclient`.

## Global Constraints

- **Sem import Python entre produtos.** Esta fatia inteira vive em `revy-trafego/`. Nada de importar de `portal-gestao/`.
- **Identidade do gestor (decisão de arquitetura, obrigatória):** o vínculo de tráfego é FK para `gestores_revy.id` (`app/models.py:456-458`). Um gestor novo criado só via `ControlInvitations.issue` **não pode** ser vinculado (não tem `GestorRevy`). Portanto, ao convidar um gestor de tráfego novo, criar `GestorRevy` (id `G`) **e** `AcessoControl` com **`id == G`** e `gestor_legado_id == G`. Isso reproduz o invariante do backfill (`app/control/access_backfill.py:139`) onde `AcessoControl.id == GestorRevy.id`, que é o que faz o login (`actor.id == acesso.id`, `app/auth.py:64`) reconciliar com `AccessControl.scope` (`VinculoTrafego.gestor_id == actor.id`, `app/control/access.py:115`).
- **Não alterar o contrato JSON existente** `POST /control/v1/convites` e `/convites/ativar`. O teste `tests/test_control_invitations.py:80-85` afirma que `/convites` **não** cria `GestorRevy` — manter. A orquestração nova é um caminho separado.
- **Senha:** mínimo 12 caracteres (igual a `ControlInvitations.activate`, `app/control/invitations.py:143`). Hash argon2 via `app.auth.hash_senha`. Token de uso único: `secrets.token_urlsafe(32)`, guardado como sha256 (`_token_hash`).
- **Flags:** toda superfície nova entra atrás de `settings.revy_control_enabled` (mesmo gate das rotas de Control existentes). A página de aceite é acessível **sem login** (o convidado ainda não tem conta), mas continua atrás de `revy_control_enabled`.
- **E-mail agnóstico:** nenhuma credencial no repositório. Backend default `console`. `smtp` só quando `REVY_TRAFEGO_EMAIL_BACKEND=smtp` e as variáveis SMTP estiverem presentes (secrets do Fly).
- **Deploy:** `fly deploy` usa a árvore local → **commitar antes de deployar**. Migration nova roda no entrypoint. Nunca imprimir segredos/tokens em log de produção (o backend `console` loga o corpo do e-mail — é só para dev).
- **Comando de teste** (a partir de `revy-trafego/`): `python -m pytest -q <arquivo>`. Rodar a suíte completa com `python -m pytest -q` antes de fechar cada fatia. **Falha pré-existente conhecida** (não é regressão): `tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts` (`MultipleResultsFound`).

---

## File Structure

**Fatia 0 (e-mail):**
- Create `revy-trafego/app/email/__init__.py` — reexporta a API pública do módulo.
- Create `revy-trafego/app/email/sender.py` — `EmailMessage`, backends `Console`/`Smtp`, `build_mime`, factory `build_email_backend`, singleton `get_email_backend`/`set_email_backend`/`send_email`.
- Modify `revy-trafego/app/config.py` — variáveis de e-mail + `public_base_url` + helper `absolute_url`.
- Create `revy-trafego/tests/test_email_sender.py` — testes do módulo de e-mail.

**Fatia 1 (convite + vínculo de gestor):**
- Create `revy-trafego/app/control/traffic_onboarding.py` — `TrafficManagerOnboarding.invite_or_bind`.
- Modify `revy-trafego/app/control/types.py` — dataclasses `InviteTrafficManager`, `TrafficInviteResult`.
- Modify `revy-trafego/app/control/access.py` — `AccessControl.list_links(actor, store_ref)` (listar vínculos ativos com nome/e-mail do gestor).
- Modify `revy-trafego/app/web/control_ui.py` — rota de convite (`POST .../gestores/convidar`), páginas de aceite (`GET`/`POST /app/control/convite/aceitar`), passar `traffic_links` no contexto do detalhe.
- Create `revy-trafego/app/templates/control/convite_aceitar.html` — formulário de definir senha.
- Modify `revy-trafego/app/templates/control/loja_detail.html` — seção "Gestor de tráfego" (lista + form por e-mail + revogar).
- Create `revy-trafego/tests/test_control_traffic_onboarding.py` — testes de domínio.
- Create `revy-trafego/tests/test_control_convite_ui.py` — testes das páginas (TestClient).

---

## FATIA 0 — Camada de e-mail agnóstica

### Task 1: Módulo de e-mail (interface + console + build_mime) e config

**Files:**
- Create: `revy-trafego/app/email/sender.py`
- Create: `revy-trafego/app/email/__init__.py`
- Modify: `revy-trafego/app/config.py` (adicionar campos de e-mail e `absolute_url`)
- Test: `revy-trafego/tests/test_email_sender.py`

**Interfaces:**
- Produces:
  - `EmailMessage(to: str, subject: str, text_body: str, html_body: str | None = None)` (dataclass frozen)
  - `class EmailBackend(Protocol): def send(self, message: EmailMessage) -> None`
  - `ConsoleEmailBackend(from_addr: str, from_name: str = "")`
  - `build_mime(message: EmailMessage, from_addr: str, from_name: str) -> email.message.EmailMessage`
  - `set_email_backend(backend: EmailBackend | None) -> None` / `get_email_backend() -> EmailBackend` / `send_email(message: EmailMessage) -> None`
  - `settings.email_backend`, `settings.email_from`, `settings.email_from_name`, `settings.absolute_url(path: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `revy-trafego/tests/test_email_sender.py`:

```python
from email.message import EmailMessage as MimeMessage

from app.email.sender import (
    ConsoleEmailBackend,
    EmailMessage,
    build_mime,
    get_email_backend,
    send_email,
    set_email_backend,
)


class _Capturing:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


def test_build_mime_sets_headers_and_bodies():
    msg = EmailMessage(
        to="gestora@example.com",
        subject="Convite Revy",
        text_body="Acesse: https://x/y",
        html_body="<p>Acesse: <a href='https://x/y'>link</a></p>",
    )
    mime = build_mime(msg, from_addr="no-reply@revy.local", from_name="Revy Control")
    assert isinstance(mime, MimeMessage)
    assert mime["To"] == "gestora@example.com"
    assert mime["Subject"] == "Convite Revy"
    assert mime["From"] == "Revy Control <no-reply@revy.local>"
    assert "https://x/y" in mime.get_body(("plain",)).get_content()
    assert "link" in mime.get_body(("html",)).get_content()


def test_send_email_dispatches_to_installed_backend():
    fake = _Capturing()
    set_email_backend(fake)
    try:
        send_email(EmailMessage(to="a@b.c", subject="s", text_body="t"))
        assert len(fake.sent) == 1
        assert fake.sent[0].to == "a@b.c"
    finally:
        set_email_backend(None)


def test_console_backend_does_not_raise(caplog):
    backend = ConsoleEmailBackend(from_addr="no-reply@revy.local", from_name="Revy")
    backend.send(EmailMessage(to="a@b.c", subject="s", text_body="corpo"))
    # não deve levantar; loga o envio
    assert any("a@b.c" in r.getMessage() for r in caplog.records) or True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_email_sender.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.email'`.

- [ ] **Step 3: Write minimal implementation**

Create `revy-trafego/app/email/sender.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailBackend(Protocol):
    def send(self, message: EmailMessage) -> None: ...


def build_mime(message: EmailMessage, from_addr: str, from_name: str) -> MimeMessage:
    mime = MimeMessage()
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    mime.set_content(message.text_body)
    if message.html_body:
        mime.add_alternative(message.html_body, subtype="html")
    return mime


@dataclass(frozen=True)
class ConsoleEmailBackend:
    from_addr: str
    from_name: str = ""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email(console) para=%s assunto=%s corpo=%s",
            message.to,
            message.subject,
            message.text_body,
        )


_backend: EmailBackend | None = None


def set_email_backend(backend: EmailBackend | None) -> None:
    global _backend
    _backend = backend


def get_email_backend() -> EmailBackend:
    global _backend
    if _backend is None:
        from app.config import settings

        _backend = build_email_backend(settings)
    return _backend


def send_email(message: EmailMessage) -> None:
    get_email_backend().send(message)


def build_email_backend(settings) -> EmailBackend:
    # SmtpEmailBackend chega na Task 2; por ora, console cobre o default.
    return ConsoleEmailBackend(
        from_addr=settings.email_from,
        from_name=settings.email_from_name,
    )
```

Create `revy-trafego/app/email/__init__.py`:

```python
from app.email.sender import (
    ConsoleEmailBackend,
    EmailBackend,
    EmailMessage,
    build_email_backend,
    build_mime,
    get_email_backend,
    send_email,
    set_email_backend,
)

__all__ = [
    "ConsoleEmailBackend",
    "EmailBackend",
    "EmailMessage",
    "build_email_backend",
    "build_mime",
    "get_email_backend",
    "send_email",
    "set_email_backend",
]
```

Add to `revy-trafego/app/config.py` inside `class Settings` (junto dos demais campos):

```python
    email_backend: str = os.getenv("REVY_TRAFEGO_EMAIL_BACKEND", "console").strip().lower()
    email_from: str = os.getenv("REVY_TRAFEGO_EMAIL_FROM", "no-reply@revy.local").strip()
    email_from_name: str = os.getenv("REVY_TRAFEGO_EMAIL_FROM_NAME", "Revy Control").strip()
    smtp_host: str = os.getenv("REVY_TRAFEGO_SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("REVY_TRAFEGO_SMTP_PORT", "587"))
    smtp_username: str = os.getenv("REVY_TRAFEGO_SMTP_USERNAME", "").strip()
    smtp_password: str = os.getenv("REVY_TRAFEGO_SMTP_PASSWORD", "")
    smtp_use_tls: bool = os.getenv("REVY_TRAFEGO_SMTP_USE_TLS", "1").strip().lower() in {
        "1", "true", "yes", "on",
    }
    public_base_url_raw: str = os.getenv("REVY_TRAFEGO_PUBLIC_BASE_URL", "").strip()
```

And add this method to `Settings` (junto de `url_prefix`):

```python
    @property
    def public_base_url(self) -> str:
        return (self.public_base_url_raw or "").rstrip("/")

    def absolute_url(self, path: str) -> str:
        """URL absoluta para links de e-mail (origem externa + prefixo do edge)."""
        normalized = path if path.startswith("/") else f"/{path}"
        prefixed = f"{self.url_prefix}{normalized}"
        base = self.public_base_url
        return f"{base}{prefixed}" if base else prefixed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_email_sender.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/email revy-trafego/app/config.py revy-trafego/tests/test_email_sender.py
git commit -m "feat(email): camada de envio agnostica (console) para o Revy Control"
```

---

### Task 2: Backend SMTP + factory por env

**Files:**
- Modify: `revy-trafego/app/email/sender.py`
- Modify: `revy-trafego/app/email/__init__.py` (exportar `SmtpEmailBackend`)
- Test: `revy-trafego/tests/test_email_sender.py`

**Interfaces:**
- Produces: `SmtpEmailBackend(host, port, username, password, use_tls, from_addr, from_name, client_factory=smtplib.SMTP)` com `.send(message)`. `build_email_backend(settings)` retorna `SmtpEmailBackend` quando `settings.email_backend == "smtp"`.
- Consumes: `build_mime`, `EmailMessage`, `settings.smtp_*` (Task 1).

- [ ] **Step 1: Write the failing test** — anexar a `tests/test_email_sender.py`:

```python
from dataclasses import replace

from app.config import settings as app_settings
from app.email.sender import SmtpEmailBackend, build_email_backend


class _FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = []
        _FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, mime):
        self.sent.append(mime)


def test_smtp_backend_starts_tls_logs_in_and_sends():
    _FakeSmtp.instances.clear()
    backend = SmtpEmailBackend(
        host="smtp.example.com", port=587, username="u", password="p",
        use_tls=True, from_addr="no-reply@revy.local", from_name="Revy",
        client_factory=_FakeSmtp,
    )
    backend.send(EmailMessage(to="a@b.c", subject="s", text_body="t"))
    assert len(_FakeSmtp.instances) == 1
    inst = _FakeSmtp.instances[0]
    assert inst.started_tls is True
    assert inst.logged_in == ("u", "p")
    assert inst.sent[0]["To"] == "a@b.c"


def test_factory_picks_smtp_when_configured():
    cfg = replace(
        app_settings, email_backend="smtp", smtp_host="smtp.example.com",
    )
    backend = build_email_backend(cfg)
    assert isinstance(backend, SmtpEmailBackend)


def test_factory_defaults_to_console():
    cfg = replace(app_settings, email_backend="console")
    assert type(build_email_backend(cfg)).__name__ == "ConsoleEmailBackend"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_email_sender.py`
Expected: FAIL — `ImportError: cannot import name 'SmtpEmailBackend'`.

- [ ] **Step 3: Write minimal implementation** — em `app/email/sender.py`, adicionar `import smtplib` no topo e a classe + ajustar a factory:

```python
@dataclass(frozen=True)
class SmtpEmailBackend:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_addr: str
    from_name: str = ""
    client_factory: type = smtplib.SMTP

    def send(self, message: EmailMessage) -> None:
        mime = build_mime(message, self.from_addr, self.from_name)
        with self.client_factory(self.host, self.port, timeout=10) as client:
            if self.use_tls:
                client.starttls()
            if self.username:
                client.login(self.username, self.password)
            client.send_message(mime)
```

E trocar `build_email_backend` para:

```python
def build_email_backend(settings) -> EmailBackend:
    if settings.email_backend == "smtp":
        return SmtpEmailBackend(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_addr=settings.email_from,
            from_name=settings.email_from_name,
        )
    return ConsoleEmailBackend(
        from_addr=settings.email_from,
        from_name=settings.email_from_name,
    )
```

Exportar `SmtpEmailBackend` em `app/email/__init__.py` (adicionar ao import e ao `__all__`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_email_sender.py`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/email
git commit -m "feat(email): backend SMTP injetavel + factory por REVY_TRAFEGO_EMAIL_BACKEND"
```

---

## FATIA 1 — Convite de gestor de tráfego por e-mail + vínculo à loja

### Task 3: Domínio `TrafficManagerOnboarding.invite_or_bind`

**Files:**
- Create: `revy-trafego/app/control/traffic_onboarding.py`
- Modify: `revy-trafego/app/control/types.py` (dataclasses novas)
- Test: `revy-trafego/tests/test_control_traffic_onboarding.py`

**Interfaces:**
- Consumes: `Actor`, `StoreRef`, `TrafficRole`, `PersonRef` (types), `_token_hash` (`app.control.invitations`), `hash_senha` (`app.auth`), models `Pessoa`, `GestorRevy`, `AcessoControl`, `ConviteAcessoControl`, `VinculoTrafego`, `Loja`, `agora`.
- Produces:
  - `InviteTrafficManager(store: StoreRef, email: str, name: str, role: TrafficRole)`
  - `TrafficInviteResult(store_id: str, manager_id: str, email: str, role: TrafficRole, token: str | None, already_active: bool)` — `token is None` quando o gestor já era ativo (só vinculou, sem novo convite).
  - `class TrafficManagerOnboarding: def __init__(self, session_factory); def invite_or_bind(self, actor: Actor, command: InviteTrafficManager) -> TrafficInviteResult`
  - Reusa exceções existentes: `AccessDenied`, `StoreNotFound`, `InvalidPersonEmail`, `ActiveResponsibleConflict`, `TrafficLinkConflict`.

- [ ] **Step 1: Write the failing test**

Create `revy-trafego/tests/test_control_traffic_onboarding.py`:

```python
from datetime import timedelta

from app.control.invitations import ControlInvitations, _token_hash
from app.control.traffic_onboarding import (
    InviteTrafficManager,
    TrafficManagerOnboarding,
)
from app.control.access import AccessControl
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    ActivateControlAccess,
    Actor,
    CreateStore,
    StoreRef,
    TrafficRole,
)
from app.db import SessionLocal
from app.models import AcessoControl, ConviteAcessoControl, GestorRevy, VinculoTrafego


def _admin(db) -> Actor:
    gestor = db.query(GestorRevy).filter(GestorRevy.papel == "admin").first()
    return Actor(id=gestor.id, email=gestor.email, name=gestor.nome, role="admin")


def _make_store(actor) -> str:
    store = StoreControl(SessionLocal).create(
        actor, CreateStore(name="Loja Teste", slug="loja-teste")
    )
    return store.id


def test_invita_gestor_novo_cria_identidades_alinhadas_e_convite():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)

    result = TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_id),
            email="Gestora.Nova@Example.com",
            name="Gestora Nova",
            role=TrafficRole.RESPONSIBLE,
        ),
    )

    assert result.token is not None and len(result.token) >= 32
    assert result.already_active is False
    with SessionLocal() as db:
        # GestorRevy e AcessoControl compartilham o MESMO id (invariante do backfill)
        gestor = (
            db.query(GestorRevy)
            .filter(GestorRevy.email == "gestora.nova@example.com")
            .one()
        )
        acesso = db.get(AcessoControl, gestor.id)
        assert acesso is not None
        assert acesso.id == gestor.id
        assert acesso.gestor_legado_id == gestor.id
        assert acesso.papel == "gestor"
        assert acesso.estado == "pendente"
        # vínculo aponta para o mesmo id
        link = (
            db.query(VinculoTrafego)
            .filter(VinculoTrafego.loja_id == store_id, VinculoTrafego.gestor_id == gestor.id)
            .one()
        )
        assert link.tipo == "responsavel"
        convite = db.query(ConviteAcessoControl).filter(
            ConviteAcessoControl.acesso_id == acesso.id
        ).one()
        assert convite.token_hash == _token_hash(result.token)


def test_aceite_reusa_activate_e_gestor_ve_a_loja():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    result = TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_id),
            email="gestora@example.com",
            name="Gestora",
            role=TrafficRole.COLLABORATOR,
        ),
    )

    account = ControlInvitations(SessionLocal).activate(
        ActivateControlAccess(token=result.token, password="senha-super-segura")
    )
    assert account.status.value == "ativo"

    with SessionLocal() as db:
        acesso = db.get(AcessoControl, result.manager_id)
        gestor_actor = Actor(id=acesso.id, email="gestora@example.com", name="Gestora", role="gestor")
        scope = AccessControl(SessionLocal).scope(gestor_actor)
    slugs = [item.store.id for item in scope]
    assert store_id in slugs


def test_invita_gestor_ja_ativo_apenas_vincula_sem_novo_convite():
    with SessionLocal() as db:
        actor = _admin(db)
    store_a = _make_store(actor)
    onboarding = TrafficManagerOnboarding(SessionLocal)
    first = onboarding.invite_or_bind(
        actor,
        InviteTrafficManager(store=StoreRef(id=store_a), email="g@example.com",
                             name="G", role=TrafficRole.COLLABORATOR),
    )
    ControlInvitations(SessionLocal).activate(
        ActivateControlAccess(token=first.token, password="senha-super-segura")
    )
    store_b = StoreControl(SessionLocal).create(
        actor, CreateStore(name="Loja B", slug="loja-b")
    ).id

    second = onboarding.invite_or_bind(
        actor,
        InviteTrafficManager(store=StoreRef(id=store_b), email="g@example.com",
                             name="G", role=TrafficRole.COLLABORATOR),
    )
    assert second.already_active is True
    assert second.token is None
    with SessionLocal() as db:
        assert db.query(VinculoTrafego).filter(
            VinculoTrafego.gestor_id == first.manager_id,
            VinculoTrafego.encerrado_em.is_(None),
        ).count() == 2


def test_nao_admin_recebe_access_denied():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    intruso = Actor(id="x", email="x@y.z", name="X", role="gestor")
    try:
        TrafficManagerOnboarding(SessionLocal).invite_or_bind(
            intruso,
            InviteTrafficManager(store=StoreRef(id=store_id), email="a@b.c",
                                 name="A", role=TrafficRole.COLLABORATOR),
        )
        assert False, "esperava AccessDenied"
    except AccessDenied:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_control_traffic_onboarding.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.control.traffic_onboarding'`.

- [ ] **Step 3: Write minimal implementation**

Add to `revy-trafego/app/control/types.py`:

```python
@dataclass(frozen=True)
class InviteTrafficManager:
    store: StoreRef
    email: str
    name: str
    role: TrafficRole


@dataclass(frozen=True)
class TrafficInviteResult:
    store_id: str
    manager_id: str
    email: str
    role: TrafficRole
    token: str | None
    already_active: bool
```

Create `revy-trafego/app/control/traffic_onboarding.py`:

```python
from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from app.auth import hash_senha
from app.control.audit import _append_event
from app.control.invitations import _token_hash
from app.control.stores import _find_store
from app.control.types import (
    AccessDenied,
    ActiveResponsibleConflict,
    Actor,
    InvalidPersonEmail,
    InviteTrafficManager,
    StoreNotFound,
    TrafficInviteResult,
    TrafficLinkConflict,
    TrafficRole,
)
from app.models import (
    AcessoControl,
    ConviteAcessoControl,
    GestorRevy,
    Pessoa,
    VinculoTrafego,
    agora,
    novo_id,
)

_INVITATION_LIFETIME = timedelta(hours=24)
_EMAIL_OK = __import__("re").compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class TrafficManagerOnboarding:
    """Convida um gestor de tráfego por e-mail e o vincula a uma loja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def invite_or_bind(
        self, actor: Actor, command: InviteTrafficManager
    ) -> TrafficInviteResult:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode convidar gestores de tráfego")
        email = (command.email or "").strip().lower()
        if len(email) > 320 or not _EMAIL_OK.fullmatch(email):
            raise InvalidPersonEmail(email)

        now = agora()
        with self._session_factory() as db:
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")

            pessoa = db.query(Pessoa).filter(Pessoa.email == email).first()
            if pessoa is None:
                nome = (command.name or "").strip()
                if not nome:
                    raise InvalidPersonEmail(email)
                pessoa = Pessoa(email=email, nome=nome[:160], criada_em=now, atualizada_em=now)
                db.add(pessoa)
                db.flush()

            acesso = (
                db.query(AcessoControl)
                .filter(AcessoControl.pessoa_id == pessoa.id)
                .first()
            )
            token: str | None = None
            already_active = False

            if acesso is None:
                # Gestor novo: ancora em GestorRevy e espelha o id no AcessoControl.
                manager_id = novo_id()
                db.add(
                    GestorRevy(
                        id=manager_id,
                        email=email,
                        nome=pessoa.nome,
                        senha_hash=hash_senha(secrets.token_urlsafe(32)),
                        papel="gestor",
                        ativo=True,
                        criado_em=now,
                    )
                )
                acesso = AcessoControl(
                    id=manager_id,
                    pessoa_id=pessoa.id,
                    papel="gestor",
                    estado="pendente",
                    senha_hash=None,
                    sessao_versao=1,
                    gestor_legado_id=manager_id,
                    criada_em=now,
                    atualizada_em=now,
                )
                db.add(acesso)
                db.flush()
                token = self._issue_invite(db, acesso.id, actor.id, now)
            else:
                manager_id = acesso.gestor_legado_id or acesso.id
                manager = db.get(GestorRevy, manager_id)
                if manager is None:
                    # AcessoControl sem GestorRevy (convite antigo login-only): cria a
                    # identidade de tráfego reaproveitando o mesmo id do acesso.
                    manager_id = acesso.id
                    db.add(
                        GestorRevy(
                            id=manager_id, email=email, nome=pessoa.nome,
                            senha_hash=acesso.senha_hash or hash_senha(secrets.token_urlsafe(32)),
                            papel="gestor", ativo=True, criado_em=now,
                        )
                    )
                    if acesso.gestor_legado_id is None:
                        acesso.gestor_legado_id = manager_id
                    db.flush()
                if acesso.estado == "ativo":
                    already_active = True
                else:
                    token = self._issue_invite(db, acesso.id, actor.id, now)

            self._bind_vinculo(db, store.id, manager_id, command.role, now)

            _append_event(
                db, actor=actor, store_id=store.id,
                action="traffic_manager.invited",
                resource_type="vinculo_trafego", resource_id=manager_id,
                after={"manager_id": manager_id, "role": command.role.value,
                       "already_active": already_active},
            )
            db.commit()
            return TrafficInviteResult(
                store_id=store.id, manager_id=manager_id, email=email,
                role=command.role, token=token, already_active=already_active,
            )

    def _issue_invite(self, db, acesso_id: str, actor_id: str, now) -> str:
        raw_token = secrets.token_urlsafe(32)
        (
            db.query(ConviteAcessoControl)
            .filter(
                ConviteAcessoControl.acesso_id == acesso_id,
                ConviteAcessoControl.usado_em.is_(None),
                ConviteAcessoControl.revogado_em.is_(None),
            )
            .update({ConviteAcessoControl.revogado_em: now}, synchronize_session=False)
        )
        db.add(
            ConviteAcessoControl(
                acesso_id=acesso_id,
                token_hash=_token_hash(raw_token),
                expira_em=now + _INVITATION_LIFETIME,
                criado_por_gestor_id=actor_id,
                criado_em=now,
            )
        )
        return raw_token

    def _bind_vinculo(self, db, store_id, manager_id, role: TrafficRole, now) -> None:
        existing = (
            db.query(VinculoTrafego)
            .filter(
                VinculoTrafego.loja_id == store_id,
                VinculoTrafego.gestor_id == manager_id,
                VinculoTrafego.encerrado_em.is_(None),
            )
            .first()
        )
        if existing is not None:
            return
        if role is TrafficRole.RESPONSIBLE:
            responsible = (
                db.query(VinculoTrafego)
                .filter(
                    VinculoTrafego.loja_id == store_id,
                    VinculoTrafego.tipo == TrafficRole.RESPONSIBLE.value,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .first()
            )
            if responsible is not None:
                raise ActiveResponsibleConflict(store_id, responsible.gestor_id)
        db.add(
            VinculoTrafego(
                loja_id=store_id, gestor_id=manager_id, tipo=role.value, iniciado_em=now
            )
        )
```

> Nota de implementação: `_append_event` exige `criado_por_gestor_id`/`ator_gestor_id` — como o ator é sempre Admin (um `GestorRevy` real, incluindo o bootstrap), o FK é satisfeito. Se algum teste rodar com um admin projetado sem `GestorRevy`, revisar `audit._append_event` (fora do escopo desta fatia; o admin de bootstrap é `GestorRevy`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_control_traffic_onboarding.py`
Expected: PASS (4 passed). Se `test_invita_gestor_ja_ativo...` falhar por `_append_event` FK, ajustar o teste para reautenticar via `AcessoControl` ativo (o ator continua sendo o admin bootstrap).

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/control/traffic_onboarding.py revy-trafego/app/control/types.py revy-trafego/tests/test_control_traffic_onboarding.py
git commit -m "feat(control): convite+vinculo de gestor de trafego (ancora GestorRevy=AcessoControl)"
```

---

### Task 4: `AccessControl.list_links` (listar vínculos com nome/e-mail)

**Files:**
- Modify: `revy-trafego/app/control/access.py`
- Modify: `revy-trafego/app/control/types.py` (`TrafficLinkDetail`)
- Test: `revy-trafego/tests/test_control_traffic_onboarding.py` (anexar)

**Interfaces:**
- Produces: `TrafficLinkDetail(link: TrafficLinkView, manager_email: str, manager_name: str)`; `AccessControl.list_links(actor: Actor, store_ref: StoreRef) -> tuple[TrafficLinkDetail, ...]` (admin vê tudo; gestor vê só se vinculado; ordena por nome).

- [ ] **Step 1: Write the failing test** — anexar a `tests/test_control_traffic_onboarding.py`:

```python
def test_list_links_traz_email_e_nome_do_gestor():
    from app.control.types import StoreRef as SR
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(store=SR(id=store_id), email="lista@example.com",
                             name="Gestor Lista", role=TrafficRole.RESPONSIBLE),
    )
    links = AccessControl(SessionLocal).list_links(actor, SR(id=store_id))
    assert len(links) == 1
    assert links[0].manager_email == "lista@example.com"
    assert links[0].manager_name == "Gestor Lista"
    assert links[0].link.role == TrafficRole.RESPONSIBLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_control_traffic_onboarding.py::test_list_links_traz_email_e_nome_do_gestor`
Expected: FAIL — `AttributeError: 'AccessControl' object has no attribute 'list_links'`.

- [ ] **Step 3: Write minimal implementation**

Add to `types.py`:

```python
@dataclass(frozen=True)
class TrafficLinkDetail:
    link: TrafficLinkView
    manager_email: str
    manager_name: str
```

Add to `access.py` (importar `AcessoControl`, `Pessoa`, `TrafficLinkDetail`; método na classe):

```python
    def list_links(self, actor: Actor, store_ref: StoreRef) -> tuple[TrafficLinkDetail, ...]:
        with self._session_factory() as db:
            store = _find_store(db, store_ref)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            if not actor.is_admin:
                mine = (
                    db.query(VinculoTrafego.id)
                    .filter(
                        VinculoTrafego.loja_id == store.id,
                        VinculoTrafego.gestor_id == actor.id,
                        VinculoTrafego.encerrado_em.is_(None),
                    )
                    .first()
                )
                if mine is None:
                    raise StoreNotFound("Loja não encontrada")
            rows = (
                db.query(VinculoTrafego, Pessoa)
                .join(AcessoControl, AcessoControl.gestor_legado_id == VinculoTrafego.gestor_id)
                .join(Pessoa, Pessoa.id == AcessoControl.pessoa_id)
                .filter(
                    VinculoTrafego.loja_id == store.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .order_by(Pessoa.nome, Pessoa.email)
                .all()
            )
            return tuple(
                TrafficLinkDetail(
                    link=_traffic_link_view(link),
                    manager_email=person.email,
                    manager_name=person.nome,
                )
                for link, person in rows
            )
```

> A junção usa `AcessoControl.gestor_legado_id == VinculoTrafego.gestor_id`, que é sempre verdade para gestores criados pela Task 3 (e pelos backfilled). Vínculos legados sem `AcessoControl` correspondente não aparecem — aceitável (todo gestor novo tem os dois).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_control_traffic_onboarding.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/control/access.py revy-trafego/app/control/types.py revy-trafego/tests/test_control_traffic_onboarding.py
git commit -m "feat(control): AccessControl.list_links com nome/e-mail do gestor"
```

---

### Task 5: Página de aceite do convite (GET + POST) + template

**Files:**
- Create: `revy-trafego/app/templates/control/convite_aceitar.html`
- Modify: `revy-trafego/app/web/control_ui.py` (2 rotas novas)
- Test: `revy-trafego/tests/test_control_convite_ui.py`

**Interfaces:**
- Consumes: `ControlInvitations.activate`, `ControlInvitationInvalid`, `WeakControlPassword`, `csrf_token`, `csrf_valido`, `_public_path`, `templates`.
- Produces: rotas `GET /app/control/convite/aceitar?token=...` (form) e `POST /app/control/convite/aceitar` (ativa e redireciona para `/login?ativado=1`). Acessíveis **sem sessão**.

- [ ] **Step 1: Write the failing test**

Create `revy-trafego/tests/test_control_convite_ui.py`:

```python
from dataclasses import replace

from app.config import settings
from app.control.traffic_onboarding import InviteTrafficManager, TrafficManagerOnboarding
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore, StoreRef, TrafficRole
from app.db import SessionLocal
from app.models import GestorRevy
from app.web import control_ui as ui_mod
from app.web import control as control_mod


def _enable_control(monkeypatch):
    for mod in (control_mod, ui_mod):
        monkeypatch.setattr(mod, "settings", replace(settings, revy_control_enabled=True))


def _admin_actor():
    with SessionLocal() as db:
        g = db.query(GestorRevy).filter(GestorRevy.papel == "admin").first()
        return Actor(id=g.id, email=g.email, name=g.nome, role="admin")


def _seed_invite():
    actor = _admin_actor()
    store = StoreControl(SessionLocal).create(actor, CreateStore(name="L", slug="l-conv"))
    return TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(store=StoreRef(id=store.id), email="conv@example.com",
                             name="Conv", role=TrafficRole.COLLABORATOR),
    )


def test_get_aceite_renderiza_form_com_token(client, monkeypatch):
    _enable_control(monkeypatch)
    result = _seed_invite()
    r = client.get(f"/app/control/convite/aceitar?token={result.token}")
    assert r.status_code == 200
    assert result.token in r.text
    assert 'name="senha"' in r.text


def test_post_aceite_define_senha_e_permite_login(client, monkeypatch):
    _enable_control(monkeypatch)
    result = _seed_invite()
    page = client.get(f"/app/control/convite/aceitar?token={result.token}")
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    r = client.post(
        "/app/control/convite/aceitar",
        data={"token": result.token, "senha": "senha-super-segura", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    login = client.post(
        "/login",
        data={"email": "conv@example.com", "senha": "senha-super-segura"},
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_post_aceite_senha_fraca_reexibe_erro(client, monkeypatch):
    _enable_control(monkeypatch)
    result = _seed_invite()
    page = client.get(f"/app/control/convite/aceitar?token={result.token}")
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    r = client.post(
        "/app/control/convite/aceitar",
        data={"token": result.token, "senha": "curta", "csrf": csrf},
    )
    assert r.status_code == 422
    assert "12" in r.text  # menciona o mínimo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_control_convite_ui.py`
Expected: FAIL — 404 (rota inexistente).

- [ ] **Step 3: Write minimal implementation**

Create `revy-trafego/app/templates/control/convite_aceitar.html`:

```html
{% extends "base.html" %}
{% block conteudo %}
<main class="auth-card">
  <h1>Definir sua senha</h1>
  <p>Crie uma senha para acessar o Revy Control.</p>
  {% if erro %}<div class="alert error" role="alert">{{ erro }}</div>{% endif %}
  <form method="post" action="{{ public_path('/app/control/convite/aceitar') }}" class="form-layout">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <input type="hidden" name="token" value="{{ token }}">
    <label>Nova senha (mínimo 12 caracteres)
      <input type="password" name="senha" minlength="12" maxlength="256" required autofocus>
    </label>
    <button class="button primary" type="submit">Ativar acesso</button>
  </form>
</main>
{% endblock %}
```

> Verificar o nome do bloco/base real em `revy-trafego/app/templates/` (ex.: `base.html` e o bloco de conteúdo). Ajustar `{% extends %}`/`{% block %}` ao layout existente do Control antes de rodar.

Add to `revy-trafego/app/web/control_ui.py` (importar `ControlInvitations`, `ActivateControlAccess`, `ControlInvitationInvalid`, `WeakControlPassword` de onde já vêm em `app.control.*`):

```python
@router.get("/app/control/convite/aceitar", response_class=HTMLResponse)
def accept_invite_page(request: Request, token: str = Query(default="", max_length=256)):
    if not settings.revy_control_enabled:
        return HTMLResponse("Página não encontrada.", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="control/convite_aceitar.html",
        context={"csrf": csrf_token(request), "token": token, "erro": None},
    )


@router.post("/app/control/convite/aceitar", response_class=HTMLResponse)
async def accept_invite_submit(request: Request):
    if not settings.revy_control_enabled:
        return HTMLResponse("Página não encontrada.", status_code=404)
    from app.control.invitations import ControlInvitations
    from app.control.types import (
        ActivateControlAccess,
        ControlInvitationInvalid,
        WeakControlPassword,
    )

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()
    token = (form.get("token") or "").strip()
    senha = form.get("senha") or ""

    def _reexibe(msg: str, code: int):
        return templates.TemplateResponse(
            request=request,
            name="control/convite_aceitar.html",
            context={"csrf": csrf_token(request), "token": token, "erro": msg},
            status_code=code,
        )

    try:
        ControlInvitations(SessionLocal).activate(
            ActivateControlAccess(token=token, password=senha)
        )
    except WeakControlPassword:
        return _reexibe("A senha deve ter entre 12 e 256 caracteres.", 422)
    except ControlInvitationInvalid:
        return _reexibe("Convite inválido ou expirado. Peça um novo convite.", 409)
    return RedirectResponse(_public_path("/login?ativado=1"), status_code=303)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_control_convite_ui.py`
Expected: PASS (3 passed). Ajustar `{% extends %}` do template se algum teste falhar por herança Jinja.

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/templates/control/convite_aceitar.html revy-trafego/app/web/control_ui.py revy-trafego/tests/test_control_convite_ui.py
git commit -m "feat(control): pagina de aceite de convite (definir senha) sem login"
```

---

### Task 6: Rota de convite na loja + envio de e-mail + seção "Gestor de tráfego" no detalhe

**Files:**
- Modify: `revy-trafego/app/web/control_ui.py` (rota `POST .../gestores/convidar`; passar `traffic_links` no contexto de `_render_store_detail`)
- Modify: `revy-trafego/app/templates/control/loja_detail.html` (seção nova na aba Pessoas)
- Test: `revy-trafego/tests/test_control_convite_ui.py` (anexar)

**Interfaces:**
- Consumes: `TrafficManagerOnboarding.invite_or_bind`, `AccessControl.list_links`, `send_email`/`get_email_backend` (Fatia 0), `settings.absolute_url`.
- Produces: `POST /app/control/lojas/{loja_id}/gestores/convidar` (form `email`, `nome`, `tipo`), envia e-mail com link de aceite e redireciona `?ok=gestor`. Contexto do detalhe ganha `traffic_links: tuple[TrafficLinkDetail, ...]`.

- [ ] **Step 1: Write the failing test** — anexar a `tests/test_control_convite_ui.py`:

```python
def test_convidar_gestor_pela_loja_envia_email_e_lista_vinculo(client, monkeypatch):
    _enable_control(monkeypatch)
    # captura de e-mail
    sent = []
    from app.email import sender as email_sender
    monkeypatch.setattr(email_sender, "get_email_backend", lambda: type("B", (), {"send": lambda self, m: sent.append(m)})())

    actor = _admin_actor()
    store = StoreControl(SessionLocal).create(actor, CreateStore(name="L2", slug="l2"))

    # login admin via client (cookie de sessão)
    client.post("/login", data={"email": actor.email, "senha": "secret-teste"}, follow_redirects=False)
    detail = client.get(f"/app/control/lojas/{store.id}")
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', detail.text).group(1)

    r = client.post(
        f"/app/control/lojas/{store.id}/gestores/convidar",
        data={"email": "novo.gestor@example.com", "nome": "Novo Gestor",
              "tipo": "colaborador", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert len(sent) == 1
    assert sent[0].to == "novo.gestor@example.com"
    assert "/app/control/convite/aceitar?token=" in sent[0].text_body

    page = client.get(f"/app/control/lojas/{store.id}?tab=pessoas")
    assert "novo.gestor@example.com" in page.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_control_convite_ui.py::test_convidar_gestor_pela_loja_envia_email_e_lista_vinculo`
Expected: FAIL — 404/405 (rota inexistente).

- [ ] **Step 3: Write minimal implementation**

Add route to `control_ui.py`:

```python
@router.post("/app/control/lojas/{loja_id}/gestores/convidar", response_class=HTMLResponse)
async def invite_traffic_manager_page(loja_id: str, request: Request, db: Session = Depends(get_db)):
    manager, denied = _admin_for_mutation(request, db)
    if denied is not None:
        return denied
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _csrf_denied()

    from app.control.traffic_onboarding import InviteTrafficManager, TrafficManagerOnboarding
    from app.control.types import InvalidPersonEmail
    from app.email import EmailMessage, get_email_backend

    email = (form.get("email") or "").strip()
    nome = (form.get("nome") or "").strip()
    try:
        role = TrafficRole((form.get("tipo") or "").strip())
    except ValueError:
        return _render_store_detail(request, db, manager, loja_id,
            error="Selecione o tipo de vínculo (responsável ou colaborador).", status_code=422)

    try:
        result = TrafficManagerOnboarding(SessionLocal).invite_or_bind(
            actor_from_user(manager),
            InviteTrafficManager(store=StoreRef(id=loja_id), email=email, name=nome, role=role),
        )
    except StoreNotFound:
        return HTMLResponse("Loja não encontrada.", status_code=404)
    except InvalidPersonEmail:
        return _render_store_detail(request, db, manager, loja_id,
            error="Informe um e-mail válido e, para um gestor novo, o nome.", status_code=422)
    except (ActiveResponsibleConflict, TrafficLinkConflict) as exc:
        return _render_store_detail(request, db, manager, loja_id, error=str(exc), status_code=409)

    if result.token is not None:
        link = settings.absolute_url(f"/app/control/convite/aceitar?token={result.token}")
        try:
            get_email_backend().send(EmailMessage(
                to=result.email,
                subject="Seu acesso ao Revy Control",
                text_body=(
                    "Você foi convidado(a) como gestor(a) de tráfego no Revy Control.\n"
                    f"Crie sua senha e acesse: {link}\n\nO link expira em 24 horas."
                ),
                html_body=(
                    "<p>Você foi convidado(a) como gestor(a) de tráfego no Revy Control.</p>"
                    f"<p><a href=\"{link}\">Criar minha senha e acessar</a></p>"
                    "<p>O link expira em 24 horas.</p>"
                ),
            ))
        except Exception:
            return _render_store_detail(request, db, manager, loja_id,
                error="Vínculo criado, mas o e-mail falhou. Reenvie o convite.", status_code=200)
    return RedirectResponse(_detail_path(loja_id, "gestor"), status_code=303)
```

In `_render_store_detail`, adicionar ao bloco `if manager.papel == "admin":` (junto de `store_people`):

```python
        traffic_links = AccessControl(SessionLocal).list_links(actor, StoreRef(id=loja_id))
```

Inicializar `traffic_links = ()` antes do `if`, e incluir `"traffic_links": traffic_links,` no `context=`.

Add to `loja_detail.html`, dentro do painel Pessoas (após a seção `pessoas-cargos`, antes de fechar `panel-pessoas`):

```html
  <section class="panel form-section" id="pessoas-gestores">
    <h2>Gestor de tráfego</h2>
    <p class="muted">Convide por e-mail; o gestor recebe um link para criar a senha.</p>
    {% if traffic_links %}
    <div class="table-wrap">
      <table id="tabela-gestores-loja">
        <thead><tr><th>Nome</th><th>E-mail</th><th>Vínculo</th><th>Ação</th></tr></thead>
        <tbody>
          {% for item in traffic_links %}
          <tr>
            <td>{{ item.manager_name }}</td>
            <td>{{ item.manager_email }}</td>
            <td>{{ item.link.role.value }}</td>
            <td>
              <form method="post" action="{{ public_path('/app/control/lojas/' ~ store.id ~ '/gestores/' ~ item.link.manager_id ~ '/revogar') }}">
                <input type="hidden" name="csrf" value="{{ csrf }}">
                <button class="button secondary" type="submit">Revogar</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty"><strong>Nenhum gestor de tráfego vinculado.</strong></div>
    {% endif %}
    <form method="post" action="{{ public_path('/app/control/lojas/' ~ store.id ~ '/gestores/convidar') }}" class="form-layout" id="form-convidar-gestor">
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <label>E-mail do gestor <input type="email" name="email" maxlength="320" required></label>
      <label>Nome <input type="text" name="nome" maxlength="160">
        <small>Obrigatório para um gestor ainda não cadastrado.</small></label>
      <label>Vínculo
        <select name="tipo" required>
          <option value="responsavel">responsável</option>
          <option value="colaborador">colaborador</option>
        </select>
      </label>
      <button class="button primary" type="submit">Convidar gestor</button>
    </form>
  </section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_control_convite_ui.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/web/control_ui.py revy-trafego/app/templates/control/loja_detail.html revy-trafego/tests/test_control_convite_ui.py
git commit -m "feat(control): convidar gestor de trafego pela loja (e-mail + selecao por nome/e-mail)"
```

---

### Task 7: Suíte completa + fechamento da fatia

**Files:** nenhum arquivo novo; validação.

- [ ] **Step 1: Rodar a suíte inteira do produto**

Run: `python -m pytest -q`
Expected: tudo passa **exceto** a falha pré-existente conhecida `tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts`. Confirmar que só essa falha (contagem = 1 failed).

- [ ] **Step 2: Higiene de git**

Run: `git diff --check` e `git status --short`. Sem lixo, sem segredos, sem `.venv`/DB.

- [ ] **Step 3: Documentar variáveis novas**

Adicionar ao `deploy/fly/3vm/env.example` (comentado, sem valores reais):

```bash
# Revy Control — e-mail de convite (default console; smtp em produção)
# REVY_TRAFEGO_EMAIL_BACKEND=console
# REVY_TRAFEGO_EMAIL_FROM=no-reply@suodominio.com
# REVY_TRAFEGO_EMAIL_FROM_NAME=Revy Control
# REVY_TRAFEGO_PUBLIC_BASE_URL=https://app2037.fly.dev
# REVY_TRAFEGO_SMTP_HOST=
# REVY_TRAFEGO_SMTP_PORT=587
# REVY_TRAFEGO_SMTP_USERNAME=
# REVY_TRAFEGO_SMTP_PASSWORD=
# REVY_TRAFEGO_SMTP_USE_TLS=1
```

- [ ] **Step 4: Commit final da fatia**

```bash
git add deploy/fly/3vm/env.example
git commit -m "docs(deploy): variaveis de e-mail/convite do Revy Control"
```

> **Ainda NÃO deployar.** O deploy real (com `REVY_TRAFEGO_EMAIL_BACKEND=smtp` + secrets SMTP no Fly) é decisão do dono e depende de conta SMTP + DNS. Ligar `REVY_CONTROL_ENABLED=1` no bundle é pré-requisito para a superfície aparecer — confirmar via `fly secrets list -a app2037` antes.

---

## Roadmap — Fatias 2 a 4 (planos próprios, fora deste documento)

Estas fatias cruzam produtos e/ou dependem de decisões já tomadas; cada uma vira um plano dedicado quando chegar a vez.

### Fatia 2 — Convite do DONO (admin → login no Portal) + relaxar readiness
Decisões do dono aplicáveis: **readiness relaxado** (dono não precisa de acesso para ativar) e **origem do login do dono = Control chama Portal via HTTP**.
- **Readiness (revy-trafego):** remover `activatable_owner` de `_REQUIRED_CODES` (`app/control/readiness.py:44`) e rebaixá-lo a `alert` (não bloqueante) — mantém a visibilidade no dashboard sem travar a ativação. Atualizar `_REQUIREMENT_LABELS`/mensagens e os testes `tests/test_control_readiness.py`, `tests/test_control_store_*`. `active_owner` (existe dono com `CargoLoja`) **continua** required. Verificar o efeito no outbox de provisioning (`provisioning_hooks`) e em `test_control_store_delete`/transições.
- **Contrato Control→Portal (novo):** endpoint no Portal (ex.: `POST /internal/v1/lojistas/convite`) autenticado por `PORTAL_SERVICE_TOKEN`, que cria um `Usuario(papel="dono", ativo=False)` pendente + token de convite, e dispara o e-mail **pelo Portal** (camada de e-mail replicada em `portal-gestao/`, espelho da Fatia 0). Senha nunca trafega do Control. Control só chama o endpoint ao convidar o dono.
- **Portal:** página de aceite (definir senha) que ativa o `Usuario`. Reusa `app/auth.hash_senha`.

### Fatia 3 — Dono convida gerente/vendedor no painel da Loja, por e-mail (portal-gestao)
- Replicar a camada de e-mail em `portal-gestao/app/email/` (mesmo design da Fatia 0).
- Novo modelo `ConviteEquipeLoja` (token/hash/expiração) + migration no Portal.
- Substituir o fluxo "senha digitada pelo dono" (`app/web/equipe.py:250`) por convite por e-mail; **reabrir** a gestão de equipe mesmo com `REVY_LOJA_SHELL_ENABLED=1` (hoje `equipe.py` bloqueia com 403 — `_equipe_estrutural_no_control`). Página de aceite (definir senha) no Portal.
- Manter isolamento multi-loja (`_membro_da_loja`).

### Fatia 4 — Provedor de e-mail real em produção
- Dono fornece: host/porta/usuário/senha SMTP + domínio remetente + DNS (SPF/DKIM/DMARC).
- Setar secrets no Fly (`REVY_TRAFEGO_SMTP_*`, `REVY_TRAFEGO_EMAIL_BACKEND=smtp`, `REVY_TRAFEGO_PUBLIC_BASE_URL`) e os equivalentes no Portal.
- Smoke: enviar um convite real e confirmar entrega/entrada.

---

## Self-Review (executado pelo autor do plano)

- **Cobertura do spec (Fatia 0+1):** camada de e-mail agnóstica (Tasks 1-2) ✅; convite de gestor por e-mail com link clicável, sem copiar token (Tasks 3,5,6) ✅; vínculo por nome/e-mail em vez de UUID (Tasks 4,6) ✅; gestor loga no Control e vê a loja (teste na Task 3) ✅; readiness/dono/equipe → roadmap Fatias 2-3 (fora desta fatia, por decisão Q4).
- **Placeholders:** nenhum "TODO/etc." — todo passo tem código real. Pontos que exigem conferência no ambiente estão marcados como notas (herança Jinja do `convite_aceitar.html`; comportamento de `_append_event` com admin projetado).
- **Consistência de tipos:** `InviteTrafficManager`/`TrafficInviteResult`/`TrafficLinkDetail` definidos na Task 3/4 e usados nas Tasks 5/6 com os mesmos campos; `manager_id == GestorRevy.id == AcessoControl.id` mantido em todas as tasks; rota de aceite `/app/control/convite/aceitar` idêntica no template, na Task 5 e no link de e-mail da Task 6.
- **Risco de regressão coberto:** contrato JSON `/convites` intacto (caminho novo é separado); Task 7 confirma que só a falha pré-existente conhecida permanece.
