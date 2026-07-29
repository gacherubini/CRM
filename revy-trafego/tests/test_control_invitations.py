import hashlib
from dataclasses import replace

from app.config import settings
from app.db import SessionLocal
from app.models import ConviteAcessoControl
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


def test_admin_convida_pessoa_que_ativa_senha_e_entra_no_control(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    person = client.post(
        "/control/v1/pessoas",
        json={
            "nome": "Gestora Convidada",
            "email": "gestora.convidada@example.com",
        },
    ).json()

    issued = client.post(
        "/control/v1/convites",
        json={"pessoa_id": person["id"], "papel": "gestor"},
    )

    assert issued.status_code == 201
    invitation = issued.json()
    assert set(invitation) == {
        "acesso_id",
        "pessoa_email",
        "token",
        "expira_em",
    }
    assert invitation["pessoa_email"] == "gestora.convidada@example.com"
    assert len(invitation["token"]) >= 32

    client.cookies.clear()
    activated = client.post(
        "/control/v1/convites/ativar",
        json={
            "token": invitation["token"],
            "senha": "senha-nova-segura",
        },
    )

    assert activated.status_code == 200
    assert activated.json() == {
        "acesso_id": invitation["acesso_id"],
        "pessoa_email": "gestora.convidada@example.com",
        "papel": "gestor",
        "estado": "ativo",
    }

    _login(client, "gestora.convidada@example.com", "senha-nova-segura")
    reused = client.post(
        "/control/v1/convites/ativar",
        json={
            "token": invitation["token"],
            "senha": "outra-senha-segura",
        },
    )

    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "control_invitation_invalid"


def test_convite_persiste_so_hash_rejeita_senha_fraca_e_expiracao(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    person = client.post(
        "/control/v1/pessoas",
        json={
            "nome": "Pessoa Segura",
            "email": "pessoa.segura@example.com",
        },
    ).json()
    invitation = client.post(
        "/control/v1/convites",
        json={"pessoa_id": person["id"], "papel": "gestor"},
    ).json()

    with SessionLocal() as db:
        stored = db.query(ConviteAcessoControl).one()
        assert stored.token_hash == hashlib.sha256(
            invitation["token"].encode("utf-8")
        ).hexdigest()
        assert stored.token_hash != invitation["token"]
        stored.expira_em = stored.criado_em
        db.commit()

    weak = client.post(
        "/control/v1/convites/ativar",
        json={"token": invitation["token"], "senha": "curta"},
    )
    expired = client.post(
        "/control/v1/convites/ativar",
        json={
            "token": invitation["token"],
            "senha": "senha-forte-expirada",
        },
    )

    assert weak.status_code == 400
    assert weak.json()["detail"]["code"] == "weak_control_password"
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "control_invitation_invalid"
