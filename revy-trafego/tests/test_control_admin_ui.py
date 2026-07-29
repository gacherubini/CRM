from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VinculoTrafego
from app.web import control_ui as control_ui_mod
from tests.conftest import csrf_da_resposta


def _enable_control_ui(monkeypatch):
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _login(client, email: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"email": email, "senha": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_control_ui_fica_oculta_e_redireciona_sem_sessao(client, monkeypatch):
    hidden = client.get("/app/control/lojas", follow_redirects=False)

    assert hidden.status_code == 404

    _enable_control_ui(monkeypatch)
    unauthenticated = client.get(
        "/app/control/lojas",
        follow_redirects=False,
    )

    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"].endswith("/login")


def test_control_ui_lista_escopo_e_mostra_formulario_somente_para_admin(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.ui@revy.local",
            nome="Gestor UI",
            senha_hash=hash_senha("senha-gestor-ui"),
            papel="gestor",
            ativo=True,
        )
        allowed = Loja(nome="Loja UI Permitida", slug="loja-ui-permitida")
        other = Loja(nome="Loja UI Alheia", slug="loja-ui-alheia")
        db.add_all([manager, allowed, other])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=allowed.id,
                gestor_id=manager.id,
                tipo="colaborador",
            )
        )
        db.commit()

    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    admin_page = client.get("/app/control/lojas")

    assert admin_page.status_code == 200
    assert "Loja UI Permitida" in admin_page.text
    assert "Loja UI Alheia" in admin_page.text
    assert 'id="form-criar-loja"' in admin_page.text

    client.cookies.clear()
    _login(client, "gestor.ui@revy.local", "senha-gestor-ui")
    manager_page = client.get("/app/control/lojas")

    assert manager_page.status_code == 200
    assert "Loja UI Permitida" in manager_page.text
    assert "Loja UI Alheia" not in manager_page.text
    assert 'id="form-criar-loja"' not in manager_page.text


def test_admin_cria_loja_com_csrf_e_gestor_recebe_403(client, monkeypatch):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.post-ui@revy.local",
            nome="Gestor POST UI",
            senha_hash=hash_senha("senha-post-ui"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()

    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    admin_page = client.get("/app/control/lojas")

    invalid_csrf = client.post(
        "/app/control/lojas",
        data={"nome": "Loja Sem CSRF", "slug": "loja-sem-csrf"},
    )
    created = client.post(
        "/app/control/lojas",
        data={
            "csrf": csrf_da_resposta(admin_page),
            "nome": "Loja Criada na UI",
            "slug": "loja-criada-ui",
        },
        follow_redirects=False,
    )

    assert invalid_csrf.status_code == 403
    assert "CSRF" in invalid_csrf.text
    assert created.status_code == 303
    created_page = client.get(created.headers["location"])
    assert "Loja criada com sucesso" in created_page.text
    assert "Loja Criada na UI" in created_page.text

    client.cookies.clear()
    _login(client, "gestor.post-ui@revy.local", "senha-post-ui")
    manager_page = client.get("/app/control/lojas")
    forbidden = client.post(
        "/app/control/lojas",
        data={
            "csrf": csrf_da_resposta(manager_page),
            "nome": "Loja Proibida",
            "slug": "loja-proibida",
        },
    )

    assert forbidden.status_code == 403
    assert "permissão" in forbidden.text
