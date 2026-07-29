from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.control.access_backfill import backfill_acessos_control
from app.db import SessionLocal
from app.models import GestorRevy
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )
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


def _create_manager_and_project_accounts() -> None:
    with SessionLocal() as db:
        db.add(
            GestorRevy(
                email="gestor.acesso@revy.local",
                nome="Gestor com Acesso",
                senha_hash=hash_senha("senha-gestor-acesso"),
                papel="gestor",
                ativo=True,
            )
        )
        db.flush()
        backfill_acessos_control(db.connection())
        db.commit()


def test_admin_lista_acessos_sem_expor_credenciais_ou_legado(
    client,
    monkeypatch,
):
    _create_manager_and_project_accounts()
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    response = client.get("/control/v1/acessos")

    assert response.status_code == 200
    assert [
        (item["pessoa"]["email"], item["papel"], item["estado"])
        for item in response.json()["items"]
    ] == [
        ("gestor.acesso@revy.local", "gestor", "ativo"),
        ("trafego@revy.local", "admin", "ativo"),
    ]
    assert set(response.json()["items"][0]) == {
        "id",
        "pessoa",
        "papel",
        "estado",
        "criado_em",
        "atualizado_em",
    }
    assert set(response.json()["items"][0]["pessoa"]) == {
        "id",
        "nome",
        "email",
    }
    serialized = response.text.lower()
    for forbidden in (
        "senha",
        "hash",
        "gestor_legado",
        "sessao_versao",
    ):
        assert forbidden not in serialized

    client.cookies.clear()
    _login(client, "gestor.acesso@revy.local", "senha-gestor-acesso")
    forbidden = client.get("/control/v1/acessos")

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "access_denied"


def test_painel_de_acessos_e_visivel_somente_para_admin(
    client,
    monkeypatch,
):
    _create_manager_and_project_accounts()
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    response = client.get("/app/control/acessos")

    assert response.status_code == 200
    assert 'id="nav-control-acessos"' in response.text
    assert 'id="tabela-acessos-control"' in response.text
    assert "Gestor com Acesso" in response.text
    assert "gestor.acesso@revy.local" in response.text
    assert "Equipe Teste" in response.text
    assert "trafego@revy.local" in response.text
    for forbidden in (
        "senha_hash",
        "gestor_legado_id",
        "sessao_versao",
    ):
        assert forbidden not in response.text

    client.cookies.clear()
    _login(client, "gestor.acesso@revy.local", "senha-gestor-acesso")
    forbidden = client.get("/app/control/acessos")

    assert forbidden.status_code == 403
    assert "Acesso negado" in forbidden.text
