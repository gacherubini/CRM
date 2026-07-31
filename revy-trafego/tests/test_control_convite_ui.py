from dataclasses import replace
import re

from app.config import settings
from app.control.invitations import ControlInvitations
from app.control.people import PeopleDirectory
from app.control.stores import StoreControl
from app.control.types import (
    Actor,
    ControlAccountRole,
    CreateStore,
    InviteControlAccess,
    PersonRef,
    RegisterPerson,
)
from app.db import SessionLocal
from app.models import GestorRevy
from app.web import control as control_mod
from app.web import control_ui as ui_mod


def _enable_control(monkeypatch):
    for mod in (control_mod, ui_mod):
        monkeypatch.setattr(mod, "settings", replace(settings, revy_control_enabled=True))


def _admin_actor():
    with SessionLocal() as db:
        manager = db.query(GestorRevy).filter(GestorRevy.papel == "admin").first()
        return Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role="admin",
        )


def _seed_invite():
    actor = _admin_actor()
    person = PeopleDirectory(SessionLocal).register(
        actor,
        RegisterPerson(name="Conv", email="conv@example.com"),
    )
    return ControlInvitations(SessionLocal).issue(
        actor,
        InviteControlAccess(
            person=PersonRef(id=person.id),
            role=ControlAccountRole.MANAGER,
        ),
    )


def _csrf(response) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match, "csrf não encontrado na página"
    return match.group(1)


def test_get_aceite_renderiza_form_com_token(client, monkeypatch):
    _enable_control(monkeypatch)
    result = _seed_invite()

    response = client.get(f"/app/control/convite/aceitar?token={result.token}")

    assert response.status_code == 200
    assert result.token in response.text
    assert 'name="senha"' in response.text


def test_post_aceite_define_senha_e_permite_login(client, monkeypatch):
    _enable_control(monkeypatch)
    result = _seed_invite()
    page = client.get(f"/app/control/convite/aceitar?token={result.token}")

    response = client.post(
        "/app/control/convite/aceitar",
        data={
            "token": result.token,
            "senha": "senha-super-segura",
            "csrf": _csrf(page),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login?ativado=1")
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

    response = client.post(
        "/app/control/convite/aceitar",
        data={"token": result.token, "senha": "curta", "csrf": _csrf(page)},
    )

    assert response.status_code == 422
    assert "12" in response.text


def test_convidar_gestor_pela_loja_envia_email_e_lista_vinculo(client, monkeypatch):
    _enable_control(monkeypatch)
    sent = []
    from app.email import sender as email_sender

    monkeypatch.setattr(
        email_sender,
        "get_email_backend",
        lambda: type("B", (), {"send": lambda self, message: sent.append(message)})(),
    )
    actor = _admin_actor()
    store = StoreControl(SessionLocal).create(
        actor, CreateStore(name="L2", slug="l2-convite")
    )
    client.post(
        "/login",
        data={"email": actor.email, "senha": "secret-teste"},
        follow_redirects=False,
    )
    detail = client.get(f"/app/control/lojas/{store.id}")
    response = client.post(
        f"/app/control/lojas/{store.id}/gestores/convidar",
        data={
            "email": "novo.gestor@example.com",
            "nome": "Novo Gestor",
            "tipo": "colaborador",
            "csrf": _csrf(detail),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert len(sent) == 1
    assert sent[0].to == "novo.gestor@example.com"
    assert "/app/control/convite/aceitar?token=" in sent[0].text_body
    page = client.get(f"/app/control/lojas/{store.id}?tab=pessoas")
    assert "novo.gestor@example.com" in page.text
