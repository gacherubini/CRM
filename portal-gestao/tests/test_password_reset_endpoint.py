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
