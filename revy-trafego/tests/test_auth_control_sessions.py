from app.control.access_backfill import backfill_acessos_control
from app.db import SessionLocal
from app.models import AcessoControl


def _project_control_access() -> None:
    with SessionLocal() as db:
        backfill_acessos_control(db.connection())
        db.commit()


def _bump_session_version() -> None:
    with SessionLocal() as db:
        access = db.query(AcessoControl).one()
        access.sessao_versao += 1
        db.commit()


def _disable_control_access() -> None:
    with SessionLocal() as db:
        access = db.query(AcessoControl).one()
        access.estado = "desativado"
        db.commit()


def _login(client):
    return client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )


def test_sem_acesso_projetado_preserva_login_e_sessao_legados(client):
    assert _login(client).status_code == 303
    assert client.get("/app", follow_redirects=False).status_code == 200


def test_bump_de_versao_invalida_cookie_e_novo_login_emite_versao_atual(client):
    _project_control_access()
    assert _login(client).status_code == 303
    assert client.get("/app", follow_redirects=False).status_code == 200

    _bump_session_version()

    expired = client.get("/app", follow_redirects=False)
    assert expired.status_code == 303
    assert expired.headers["location"].endswith("/login")

    assert _login(client).status_code == 303
    assert client.get("/app", follow_redirects=False).status_code == 200


def test_acesso_desativado_bloqueia_sessao_existente_e_novo_login(client):
    _project_control_access()
    assert _login(client).status_code == 303
    assert client.get("/app", follow_redirects=False).status_code == 200

    _disable_control_access()

    expired = client.get("/app", follow_redirects=False)
    assert expired.status_code == 303
    assert expired.headers["location"].endswith("/login")

    client.cookies.clear()
    denied = _login(client)
    assert denied.status_code == 401
    assert "E-mail ou senha inválidos." in denied.text


def test_cookie_legado_sem_versao_so_e_valido_na_projecao_ativa_versao_um(client):
    assert _login(client).status_code == 303
    assert client.get("/app", follow_redirects=False).status_code == 200

    _project_control_access()

    assert client.get("/app", follow_redirects=False).status_code == 200

    _bump_session_version()
    expired = client.get("/app", follow_redirects=False)
    assert expired.status_code == 303
    assert expired.headers["location"].endswith("/login")
