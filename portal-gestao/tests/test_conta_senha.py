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
