from dataclasses import replace

from app.config import settings
from app.web import control as control_mod


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
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


def _create_active_manager(client) -> tuple[str, str]:
    person = client.post(
        "/control/v1/pessoas",
        json={
            "nome": "Gestora Revogável",
            "email": "gestora.revogavel@example.com",
        },
    ).json()
    invitation = client.post(
        "/control/v1/convites",
        json={"pessoa_id": person["id"], "papel": "gestor"},
    ).json()
    client.cookies.clear()
    activated = client.post(
        "/control/v1/convites/ativar",
        json={
            "token": invitation["token"],
            "senha": "senha-segura-inicial",
        },
    )
    assert activated.status_code == 200
    return invitation["acesso_id"], person["email"]


def test_admin_desativa_e_reativa_acesso_revogando_a_sessao_atual(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    access_id, email = _create_active_manager(client)
    _login(client, email, "senha-segura-inicial")
    manager_cookie = client.cookies.get("revy_trafego_session")
    assert manager_cookie

    _login(client, "trafego@revy.local", "secret-teste")
    disabled = client.post(f"/control/v1/acessos/{access_id}/desativar")

    assert disabled.status_code == 200
    assert disabled.json()["estado"] == "desativado"

    client.cookies.clear()
    client.cookies.set("revy_trafego_session", manager_cookie)
    blocked = client.get("/app", follow_redirects=False)
    assert blocked.status_code == 303
    assert blocked.headers["location"].endswith("/login")

    client.cookies.clear()
    _login(client, "trafego@revy.local", "secret-teste")
    enabled = client.post(f"/control/v1/acessos/{access_id}/reativar")

    assert enabled.status_code == 200
    assert enabled.json()["estado"] == "ativo"

    client.cookies.clear()
    client.cookies.set("revy_trafego_session", manager_cookie)
    stale = client.get("/app", follow_redirects=False)
    assert stale.status_code == 303
    assert stale.headers["location"].endswith("/login")

    client.cookies.clear()
    _login(client, email, "senha-segura-inicial")
