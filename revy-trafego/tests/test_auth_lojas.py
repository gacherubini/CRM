from app.db import SessionLocal
from app.lojas import listar_loja_slugs
from app.models import Campanha, MetaPixelConfig, novo_id
from tests.conftest import csrf_da_resposta


def test_home_redireciona_sem_login(client):
    r = client.get("/app", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_login_ok(client):
    r = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] in {"/app", "/app/"}


def test_lista_lojas_uniao():
    db = SessionLocal()
    try:
        db.add(
            Campanha(
                id=novo_id(),
                loja_slug="loja-a",
                nome="A",
                utm_campaign="a",
                utm_campaign_norm="a",
                criada_por_email="t@t.com",
            )
        )
        db.add(MetaPixelConfig(loja_slug="loja-b", pixel_id="12345678901"))
        db.commit()
        assert listar_loja_slugs(db) == ["loja-a", "loja-b"]
    finally:
        db.close()


def test_selecionar_loja_e_abrir_trafego(client_logado):
    home = client_logado.get("/app")
    assert home.status_code == 200
    csrf = csrf_da_resposta(home)
    r = client_logado.post(
        "/app/loja",
        data={"loja_slug": "loja-demo", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client_logado.get("/app/trafego")
    assert page.status_code == 200
    assert "Pixel ID" in page.text


def test_salvar_pixel(client_logado):
    home = client_logado.get("/app")
    csrf = csrf_da_resposta(home)
    client_logado.post(
        "/app/loja",
        data={"loja_slug": "loja-demo", "csrf": csrf},
        follow_redirects=False,
    )
    form = client_logado.get("/app/trafego")
    csrf2 = csrf_da_resposta(form)
    r = client_logado.post(
        "/app/trafego",
        data={
            "csrf": csrf2,
            "pixel_id": "112233445566778",
            "capi_token": "EAAB-token-secreto",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    pub = client_logado.get("/public/v1/lojas/loja-demo/pixel")
    assert pub.status_code == 200
    assert pub.json()["pixel_id"] == "112233445566778"
    assert pub.json()["enabled"] is True
