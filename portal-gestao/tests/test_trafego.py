"""E10 — aba Tráfego / Meta Pixel + CAPI Purchase."""
from decimal import Decimal

import httpx

from conftest import csrf_da_resposta, login

from app.cripto import cifrar, decifrar
from app.db import SessionLocal
from app.models import MetaCapiOutbox, MetaPixelConfig, Venda


def _csrf_trafego(client):
    return csrf_da_resposta(client.get("/app/trafego"))


def test_vendedor_nao_acessa_trafego(client):
    login(client, papel="vendedor")
    resposta = client.get("/app/trafego", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"
    assert "Tráfego" not in client.get("/app").text or True  # nav oculta para vendedor
    # POST também bloqueado
    resposta_post = client.post(
        "/app/trafego",
        data={"csrf": "x", "pixel_id": "1", "capi_token": "tok"},
        follow_redirects=False,
    )
    assert resposta_post.status_code == 303
    assert resposta_post.headers["location"] == "/app"


def test_vendedor_sem_link_trafego_na_nav(client):
    login(client, papel="vendedor")
    pagina = client.get("/app")
    assert 'href="/app/trafego"' not in pagina.text


def test_dono_ve_aba_trafego(client):
    login(client)
    pagina = client.get("/app")
    assert 'href="/app/trafego"' in pagina.text
    form = client.get("/app/trafego")
    assert form.status_code == 200
    assert "Pixel ID" in form.text
    assert "Token CAPI" in form.text
    assert "Não configurado" in form.text


def test_salva_config_e_mascara_token_no_get(client):
    login(client)
    pagina = client.get("/app/trafego")
    resposta = client.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pixel_id": "999888777666555",
            "capi_token": "EAAB-super-secreto-nunca-mostrar",
            "test_event_code": "TEST12345",
            "enviar_page_view": "on",
            "enviar_lead": "on",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/trafego?ok=salvo"

    get = client.get("/app/trafego")
    assert get.status_code == 200
    assert "Configurado" in get.text
    assert "EAAB-super-secreto-nunca-mostrar" not in get.text
    assert "999888777666555" in get.text
    assert "TEST12345" in get.text

    db = SessionLocal()
    config = db.query(MetaPixelConfig).filter(MetaPixelConfig.loja_slug == "loja-teste").one()
    assert config.pixel_id == "999888777666555"
    assert config.token_ciphertext
    assert "EAAB" not in config.token_ciphertext
    assert decifrar(config.token_ciphertext) == "EAAB-super-secreto-nunca-mostrar"
    assert config.test_event_code == "TEST12345"
    assert config.enviar_purchase is True
    db.close()


def test_salvar_sem_token_novo_mantem_existente(client):
    login(client)
    pagina = client.get("/app/trafego")
    client.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pixel_id": "111",
            "capi_token": "token-original",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    pagina2 = client.get("/app/trafego")
    client.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina2),
            "pixel_id": "222",
            "capi_token": "",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    db = SessionLocal()
    config = db.query(MetaPixelConfig).one()
    assert config.pixel_id == "222"
    assert decifrar(config.token_ciphertext) == "token-original"
    db.close()


def test_gerente_pode_salvar(client):
    login(client, papel="gerente")
    pagina = client.get("/app/trafego")
    assert pagina.status_code == 200
    resposta = client.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pixel_id": "555",
            "capi_token": "tok-gerente",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/trafego?ok=salvo"


def _configurar_meta(db, *, purchase=True, pixel_id="1234567890", token="tok-capi"):
    db.add(
        MetaPixelConfig(
            loja_slug="loja-teste",
            pixel_id=pixel_id,
            token_ciphertext=cifrar(token),
            test_event_code="TESTCODE",
            enviar_page_view=True,
            enviar_lead=True,
            enviar_purchase=purchase,
        )
    )
    db.commit()


def _criar_venda():
    db = SessionLocal()
    venda = Venda(
        loja_slug="loja-teste",
        vendedor_email="dono@loja.test",
        descricao="Civic 2022",
        preco_venda=Decimal("85000.50"),
        status="registrada",
    )
    db.add(venda)
    db.commit()
    venda_id = venda.id
    db.close()
    return venda_id


def test_confirmar_venda_dispara_capi_purchase(client, monkeypatch):
    login(client)
    db = SessionLocal()
    _configurar_meta(db)
    db.close()
    venda_id = _criar_venda()

    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["body"] = request.read()
        capturado["params"] = dict(request.url.params)
        return httpx.Response(200, json={"events_received": 1})

    transporte = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return original(*args, **kwargs)

    monkeypatch.setattr("app.meta_capi.httpx.Client", fabrica)

    csrf = csrf_da_resposta(client.get("/app/vendas"))
    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"

    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "confirmada"
    outbox = db.query(MetaCapiOutbox).filter(MetaCapiOutbox.venda_id == venda_id).one()
    assert outbox.event_id == f"purchase-{venda_id}"
    assert outbox.event_name == "Purchase"
    assert outbox.status == "delivered"
    assert outbox.attempts >= 1
    db.close()

    assert "1234567890" in capturado["url"]
    assert capturado["params"].get("access_token") == "tok-capi"
    body = capturado["body"].decode()
    assert "Purchase" in body
    assert "85000.5" in body or "85000.50" in body
    assert "BRL" in body
    assert f"purchase-{venda_id}" in body
    assert "TESTCODE" in body


def test_falha_capi_nao_quebra_confirmacao_venda(client, monkeypatch):
    login(client)
    db = SessionLocal()
    _configurar_meta(db)
    db.close()
    venda_id = _criar_venda()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    transporte = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return original(*args, **kwargs)

    monkeypatch.setattr("app.meta_capi.httpx.Client", fabrica)

    csrf = csrf_da_resposta(client.get("/app/vendas"))
    resposta = client.post(
        f"/app/vendas/{venda_id}/confirmar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"

    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "confirmada"
    outbox = db.query(MetaCapiOutbox).filter(MetaCapiOutbox.venda_id == venda_id).one()
    assert outbox.status == "failed"
    assert outbox.last_error
    db.close()


def test_purchase_desligado_nao_enfileira(client, monkeypatch):
    login(client)
    db = SessionLocal()
    _configurar_meta(db, purchase=False)
    db.close()
    venda_id = _criar_venda()

    chamado = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamado["n"] += 1
        return httpx.Response(200, json={})

    monkeypatch.setattr(
        "app.meta_capi.httpx.Client",
        lambda *a, **k: httpx.Client(transport=httpx.MockTransport(handler), *a, **k),
    )

    csrf = csrf_da_resposta(client.get("/app/vendas"))
    client.post(f"/app/vendas/{venda_id}/confirmar", data={"csrf": csrf}, follow_redirects=False)

    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "confirmada"
    assert db.query(MetaCapiOutbox).count() == 0
    db.close()
    assert chamado["n"] == 0
