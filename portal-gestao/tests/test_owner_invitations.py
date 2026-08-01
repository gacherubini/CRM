import re

from app.auth import autenticar, hash_senha
from app.db import SessionLocal
from app.email import set_email_backend
from app.models import ConviteAcessoLoja, Usuario
from app.owner_invitations import _token_hash
from conftest import csrf_da_resposta


class _CapturingEmail:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


def _issue(client, *, email="novo.dono@example.com", name="Novo Dono"):
    return client.post(
        "/internal/v1/lojistas/convite",
        headers={"X-Service-Token": "token-interno"},
        json={"email": email, "nome": name, "loja_slug": "loja-nova"},
    )


def _token(message) -> str:
    match = re.search(r"[?&]token=([^\s<]+)", message.text_body)
    assert match is not None
    return match.group(1)


def test_endpoint_interno_convida_dono_e_aceite_ativa_login(client, monkeypatch):
    monkeypatch.setenv("PORTAL_SERVICE_TOKEN", "token-interno")
    capture = _CapturingEmail()
    set_email_backend(capture)
    try:
        response = _issue(client)
        assert response.status_code == 200
        assert "token" not in response.text
        assert response.json()["email"] == "novo.dono@example.com"
        assert len(capture.sent) == 1
        token = _token(capture.sent[0])

        with SessionLocal() as db:
            user = db.query(Usuario).filter(Usuario.email == "novo.dono@example.com").one()
            assert user.papel == "dono"
            assert user.loja_slug == "loja-nova"
            assert user.ativo is False
            invitation = db.query(ConviteAcessoLoja).filter_by(usuario_id=user.id).one()
            assert invitation.token_hash == _token_hash(token)
            assert token not in invitation.token_hash

        page = client.get(f"/convite/aceitar?token={token}")
        accepted = client.post(
            "/convite/aceitar",
            data={
                "csrf": csrf_da_resposta(page),
                "token": token,
                "senha": "senha-nova-segura",
                "senha_confirmacao": "senha-nova-segura",
            },
            follow_redirects=False,
        )
        assert accepted.status_code == 303
        assert accepted.headers["location"] == "/login?ativado=1"
        with SessionLocal() as db:
            assert autenticar(db, "novo.dono@example.com", "senha-nova-segura") is not None
    finally:
        set_email_backend(None)


def test_reenvio_reutiliza_usuario_revoga_token_anterior(client, monkeypatch):
    monkeypatch.setenv("PORTAL_SERVICE_TOKEN", "token-interno")
    capture = _CapturingEmail()
    set_email_backend(capture)
    try:
        assert _issue(client).status_code == 200
        assert _issue(client, name="Novo Dono Atualizado").status_code == 200
        old_token, new_token = (_token(message) for message in capture.sent)
        assert old_token != new_token
        with SessionLocal() as db:
            users = db.query(Usuario).filter(Usuario.email == "novo.dono@example.com").all()
            invitations = db.query(ConviteAcessoLoja).filter_by(usuario_id=users[0].id).all()
            assert len(users) == 1
            assert users[0].nome == "Novo Dono Atualizado"
            assert len(invitations) == 2
            assert sum(item.revogado_em is None for item in invitations) == 1

        old_page = client.get(f"/convite/aceitar?token={old_token}")
        rejected = client.post(
            "/convite/aceitar",
            data={
                "csrf": csrf_da_resposta(old_page),
                "token": old_token,
                "senha": "senha-nova-segura",
                "senha_confirmacao": "senha-nova-segura",
            },
        )
        assert rejected.status_code == 422
        assert "inválido ou expirado" in rejected.text
    finally:
        set_email_backend(None)


def test_endpoint_exige_token_e_permite_reenvio_usuario_ativo(client, monkeypatch):
    monkeypatch.setenv("PORTAL_SERVICE_TOKEN", "token-interno")
    with SessionLocal() as db:
        db.add(
            Usuario(
                email="dono@loja.test",
                nome="Ana Loja",
                senha_hash=hash_senha("senha-atual-segura"),
                papel="dono",
                loja_slug="loja-nova",
                ativo=True,
            )
        )
        db.commit()
    missing = client.post(
        "/internal/v1/lojistas/convite",
        json={"email": "x@example.com", "nome": "X", "loja_slug": "loja-nova"},
    )
    wrong = client.post(
        "/internal/v1/lojistas/convite",
        headers={"X-Service-Token": "errado"},
        json={"email": "x@example.com", "nome": "X", "loja_slug": "loja-nova"},
    )
    active = _issue(client, email="dono@loja.test", name="Tentativa")
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert active.status_code == 200
    with SessionLocal() as db:
        user = db.query(Usuario).filter(Usuario.email == "dono@loja.test").one()
        assert user.nome == "Ana Loja"
        assert user.ativo is True
