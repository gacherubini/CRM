from dataclasses import replace

from app.config import settings
from app.web import control as control_mod


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _login(client, email: str, password: str):
    return client.post(
        "/login",
        data={"email": email, "senha": password},
        follow_redirects=False,
    )


def _create_active_manager(client) -> tuple[str, str]:
    person = client.post(
        "/control/v1/pessoas",
        json={
            "nome": "Gestora Recuperável",
            "email": "gestora.recuperavel@example.com",
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
            "senha": "senha-segura-original",
        },
    )
    assert activated.status_code == 200
    return invitation["acesso_id"], person["email"]


def test_admin_emite_recuperacao_que_troca_senha_e_revoga_sessao(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    assert _login(client, "trafego@revy.local", "secret-teste").status_code == 303
    access_id, email = _create_active_manager(client)
    assert _login(client, email, "senha-segura-original").status_code == 303
    old_cookie = client.cookies.get("revy_trafego_session")
    assert old_cookie

    assert _login(client, "trafego@revy.local", "secret-teste").status_code == 303
    issued = client.post(
        "/control/v1/recuperacoes",
        json={"acesso_id": access_id},
    )

    assert issued.status_code == 201
    recovery = issued.json()
    assert set(recovery) == {
        "acesso_id",
        "pessoa_email",
        "token",
        "expira_em",
    }
    assert recovery["acesso_id"] == access_id
    assert recovery["pessoa_email"] == email

    client.cookies.clear()
    consumed = client.post(
        "/control/v1/recuperacoes/consumir",
        json={
            "token": recovery["token"],
            "senha": "senha-segura-recuperada",
        },
    )

    assert consumed.status_code == 200
    assert consumed.json() == {
        "acesso_id": access_id,
        "pessoa_email": email,
        "estado": "ativo",
    }
    assert _login(client, email, "senha-segura-original").status_code == 401
    assert _login(client, email, "senha-segura-recuperada").status_code == 303

    client.cookies.clear()
    client.cookies.set("revy_trafego_session", old_cookie)
    stale = client.get("/app", follow_redirects=False)
    assert stale.status_code == 303
    assert stale.headers["location"].endswith("/login")

    reused = client.post(
        "/control/v1/recuperacoes/consumir",
        json={
            "token": recovery["token"],
            "senha": "outra-senha-segura",
        },
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "control_recovery_invalid"
