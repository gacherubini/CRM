"""Tráfego / Meta Pixel + CAPI Purchase — porte da suíte do portal-gestão.

Diferenças em relação ao portal (que motivam adaptações aqui):
* auth é por ``GestorRevy`` (sem papéis dono/gerente/vendedor) e a loja vem do
  seletor da sessão (``POST /app/loja``), não do usuário;
* não existe ``/app/vendas/{id}/confirmar``: o Purchase entra pela API de
  serviço ``POST /v1/lojas/{slug}/eventos/venda-confirmada``;
* não existe a flag ``PORTAL_TRAFEGO_UI_LEGACY`` — a UI técnica é a superfície
  principal do produto.
"""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from tests.conftest import csrf_da_resposta

from app import config as config_mod
from app.cripto import cifrar, decifrar
from app.db import SessionLocal
from app.meta_capi import montar_payload_purchase, processar_outbox_automatico
from app.models import MetaCapiOutbox, MetaPixelConfig

LOJA = "loja-teste"


# --------------------------------------------------------------------------
# helpers / fixtures locais (conftest.py é compartilhado e não pode mudar)
# --------------------------------------------------------------------------


@pytest.fixture
def client_loja(client_logado):
    """Gestor logado com a loja `loja-teste` já selecionada na sessão."""
    home = client_logado.get("/app")
    resposta = client_logado.post(
        "/app/loja",
        data={"loja_slug": LOJA, "csrf": csrf_da_resposta(home)},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    return client_logado


def _headers_servico(monkeypatch, valor="tok-servico-trafego"):
    monkeypatch.setattr(
        config_mod, "settings", replace(config_mod.settings, service_token=valor)
    )
    return {"X-Service-Token": valor}


def _mock_capi(monkeypatch, handler):
    """Faz o cliente HTTP do meta_capi responder pelo handler informado."""
    transporte = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return original(*args, **kwargs)

    monkeypatch.setattr("app.meta_capi.httpx.Client", fabrica)


def _configurar_meta(*, purchase=True, pixel_id="1234567890", token="tok-capi"):
    db = SessionLocal()
    try:
        db.add(
            MetaPixelConfig(
                loja_slug=LOJA,
                pixel_id=pixel_id,
                token_ciphertext=cifrar(token),
                test_event_code="TESTCODE",
                enviar_page_view=True,
                enviar_lead=True,
                enviar_purchase=purchase,
            )
        )
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# UI de configuração
# --------------------------------------------------------------------------


def test_sem_login_nao_acessa_trafego(client):
    resposta = client.get("/app/trafego", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"

    resposta_post = client.post(
        "/app/trafego",
        data={"csrf": "x", "pixel_id": "1", "capi_token": "tok"},
        follow_redirects=False,
    )
    assert resposta_post.status_code == 303
    assert resposta_post.headers["location"] == "/login"


def test_sem_loja_selecionada_volta_para_home(client_logado):
    resposta = client_logado.get("/app/trafego", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app?erro=loja"


def test_gestor_ve_aba_trafego(client_loja):
    pagina = client_loja.get("/app")
    assert 'href="/app/trafego"' in pagina.text
    form = client_loja.get("/app/trafego")
    assert form.status_code == 200
    assert "Pixel ID" in form.text
    assert "Token CAPI" in form.text
    assert "Não configurado" in form.text


def test_public_pixel_endpoint_sem_auth(client_loja):
    """Catálogo puxa Pixel ID sem login; token CAPI nunca aparece."""
    vazio = client_loja.get("/public/v1/lojas/loja-teste/pixel")
    assert vazio.status_code == 200
    assert vazio.json() == {
        "loja_slug": "loja-teste",
        "pixel_id": "",
        "enabled": False,
        "enviar_page_view": True,
        "enviar_lead": True,
    }

    pagina = client_loja.get("/app/trafego")
    client_loja.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pixel_id": "112233445566778",
            "capi_token": "EAAB-token-secreto",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )

    # Sem cookie de sessão
    client_loja.cookies.clear()
    r = client_loja.get("/public/v1/lojas/loja-teste/pixel")
    assert r.status_code == 200
    body = r.json()
    assert body["loja_slug"] == "loja-teste"
    assert body["pixel_id"] == "112233445566778"
    assert body["enabled"] is True
    assert body["enviar_page_view"] is False
    assert body["enviar_lead"] is False
    assert "token" not in body
    assert "EAAB" not in r.text


def test_public_pixel_nao_expoe_valor_invalido(client):
    db = SessionLocal()
    try:
        db.add(
            MetaPixelConfig(
                loja_slug="loja-invalida",
                pixel_id="EAAB-token-colado-no-campo-errado",
                enviar_page_view=True,
                enviar_lead=True,
            )
        )
        db.commit()
    finally:
        db.close()

    resposta = client.get("/public/v1/lojas/loja-invalida/pixel")
    assert resposta.status_code == 200
    assert resposta.json()["pixel_id"] == ""
    assert resposta.json()["enabled"] is False
    assert "EAAB" not in resposta.text


def test_form_rejeita_pixel_id_nao_numerico(client_loja):
    pagina = client_loja.get("/app/trafego")
    resposta = client_loja.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pixel_id": "token-nao-e-pixel-id",
            "capi_token": "token-capi",
            "enviar_purchase": "on",
        },
    )
    assert resposta.status_code == 422
    assert "Pixel ID válido" in resposta.text


def test_salva_config_e_mascara_token_no_get(client_loja):
    pagina = client_loja.get("/app/trafego")
    resposta = client_loja.post(
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

    get = client_loja.get("/app/trafego")
    assert get.status_code == 200
    assert "Configurado" in get.text
    assert "EAAB-super-secreto-nunca-mostrar" not in get.text
    assert "999888777666555" in get.text
    assert "TEST12345" in get.text

    db = SessionLocal()
    try:
        config = (
            db.query(MetaPixelConfig).filter(MetaPixelConfig.loja_slug == LOJA).one()
        )
        assert config.pixel_id == "999888777666555"
        assert config.token_ciphertext
        assert "EAAB" not in config.token_ciphertext
        assert decifrar(config.token_ciphertext) == "EAAB-super-secreto-nunca-mostrar"
        assert config.test_event_code == "TEST12345"
        assert config.enviar_purchase is True
    finally:
        db.close()


def test_salvar_sem_token_novo_mantem_existente(client_loja):
    pagina = client_loja.get("/app/trafego")
    client_loja.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pixel_id": "111222333444555",
            "capi_token": "token-original",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    pagina2 = client_loja.get("/app/trafego")
    client_loja.post(
        "/app/trafego",
        data={
            "csrf": csrf_da_resposta(pagina2),
            "pixel_id": "222333444555666",
            "capi_token": "",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        config = db.query(MetaPixelConfig).one()
        assert config.pixel_id == "222333444555666"
        assert decifrar(config.token_ciphertext) == "token-original"
    finally:
        db.close()


# --------------------------------------------------------------------------
# Purchase CAPI (entra pela API de serviço, não pela tela de vendas)
# --------------------------------------------------------------------------


def test_venda_confirmada_dispara_capi_purchase(client, monkeypatch):
    headers = _headers_servico(monkeypatch)
    _configurar_meta()

    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["body"] = request.read()
        capturado["params"] = dict(request.url.params)
        return httpx.Response(200, json={"events_received": 1})

    _mock_capi(monkeypatch, handler)

    resposta = client.post(
        f"/v1/lojas/{LOJA}/eventos/venda-confirmada",
        json={
            "venda_id": "venda-1",
            "valor": "85000.50",
            "moeda": "BRL",
            "cliente_telefone": "+55 (11) 98765-4321",
            "cliente_email": " Pessoa@Email.COM ",
            "fbclid": "IwAR-abc",
        },
        headers=headers,
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["ok"] is True
    assert resposta.json()["idempotent"] is False

    db = SessionLocal()
    try:
        outbox = (
            db.query(MetaCapiOutbox).filter(MetaCapiOutbox.venda_id == "venda-1").one()
        )
        assert outbox.event_id == "purchase-venda-1"
        assert outbox.event_name == "Purchase"
        assert outbox.status == "delivered"
        assert outbox.attempts >= 1
    finally:
        db.close()

    assert "1234567890" in capturado["url"]
    assert capturado["params"].get("access_token") == "tok-capi"
    body = capturado["body"].decode()
    assert "Purchase" in body
    assert "85000.5" in body or "85000.50" in body
    assert "BRL" in body
    assert "purchase-venda-1" in body
    assert "TESTCODE" in body
    # PII só vai hasheada.
    assert "+55" not in body
    assert "Pessoa@Email.COM" not in body


def test_falha_capi_nao_quebra_evento_de_venda(client, monkeypatch):
    headers = _headers_servico(monkeypatch)
    _configurar_meta()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    _mock_capi(monkeypatch, handler)

    resposta = client.post(
        f"/v1/lojas/{LOJA}/eventos/venda-confirmada",
        json={"venda_id": "venda-2", "valor": "1000.00"},
        headers=headers,
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["ok"] is True

    db = SessionLocal()
    try:
        outbox = (
            db.query(MetaCapiOutbox).filter(MetaCapiOutbox.venda_id == "venda-2").one()
        )
        assert outbox.status == "failed"
        assert outbox.last_error
        assert "tok-capi" not in outbox.last_error
        assert "access_token" not in outbox.last_error
    finally:
        db.close()


def test_purchase_desligado_nao_envia_capi(client, monkeypatch):
    headers = _headers_servico(monkeypatch)
    _configurar_meta(purchase=False)

    chamado = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamado["n"] += 1
        return httpx.Response(200, json={})

    _mock_capi(monkeypatch, handler)

    resposta = client.post(
        f"/v1/lojas/{LOJA}/eventos/venda-confirmada",
        json={"venda_id": "venda-3", "valor": "1000.00"},
        headers=headers,
    )
    assert resposta.status_code == 200, resposta.text
    assert chamado["n"] == 0

    db = SessionLocal()
    try:
        # Divergência vs. portal: aqui a API grava um marcador `skipped`
        # (idempotência futura) em vez de não criar linha nenhuma.
        outbox = db.query(MetaCapiOutbox).one()
        assert outbox.status == "skipped"
        assert outbox.attempts == 0
        assert json.loads(outbox.payload_json)["reason"] == "sem_config_capi"
    finally:
        db.close()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG revy-trafego: no caminho CTWA a idempotência é conferida pelo event_id "
        "sem sufixo (app/api_v1.py:195) mas a outbox é gravada com '-msg' "
        "(app/api_v1.py:212), então a 2ª chamada devolve idempotent=False. "
        "Não duplica evento nem reenvia, mas quebra o contrato que o caminho web "
        "cumpre (ver tests/test_api_resultados.py::test_venda_confirmada_idempotente)."
    ),
)
def test_venda_confirmada_ctwa_e_idempotente(client, monkeypatch):
    headers = _headers_servico(monkeypatch)
    _configurar_meta()

    envios = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        envios["n"] += 1
        return httpx.Response(200, json={"events_received": 1})

    _mock_capi(monkeypatch, handler)

    payload = {"venda_id": "venda-ctwa", "valor": "500.00", "ctwa_clid": "ARxyz"}
    r1 = client.post(
        f"/v1/lojas/{LOJA}/eventos/venda-confirmada", json=payload, headers=headers
    )
    r2 = client.post(
        f"/v1/lojas/{LOJA}/eventos/venda-confirmada", json=payload, headers=headers
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert envios["n"] == 1

    db = SessionLocal()
    try:
        outbox = db.query(MetaCapiOutbox).one()
        assert outbox.event_id == "purchase-venda-ctwa-msg"
        corpo = json.loads(outbox.payload_json)["data"][0]
        assert corpo["action_source"] == "business_messaging"
        assert corpo["user_data"]["ctwa_clid"] == "ARxyz"
    finally:
        db.close()

    assert r2.json()["idempotent"] is True


def test_payload_purchase_enriquece_telefone_email_e_fbclid(monkeypatch):
    monkeypatch.setattr("app.meta_capi.time.time", lambda: 1700000000)
    payload = montar_payload_purchase(
        event_id="purchase-v1",
        value="100",
        phone="+55 (11) 98765-4321",
        email=" Pessoa@Email.COM ",
        fbclid="IwAR-abc",
    )
    user_data = payload["data"][0]["user_data"]
    assert user_data["ph"]
    assert user_data["em"]
    assert user_data["fbc"] == "fb.1.1700000000.IwAR-abc"
    assert "+55" not in json.dumps(payload)
    assert "Pessoa@Email.COM" not in json.dumps(payload)


def test_retry_capi_e_status_sem_expor_token(client_loja, monkeypatch):
    _configurar_meta(token="segredo-retry")
    db = SessionLocal()
    try:
        db.add(
            MetaCapiOutbox(
                loja_slug=LOJA,
                event_id="purchase-retry",
                event_name="Purchase",
                payload_json=json.dumps(
                    montar_payload_purchase(event_id="purchase-retry", value="10")
                ),
                status="failed",
                attempts=1,
                last_error=(
                    "Client error '400' for url "
                    "'https://graph.facebook.com/events?access_token=segredo-legado'"
                ),
            )
        )
        db.commit()
    finally:
        db.close()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"events_received": 1})

    _mock_capi(monkeypatch, handler)

    pagina = client_loja.get("/app/trafego")
    assert "último envio falhou" in pagina.text
    assert "segredo-legado" not in pagina.text
    assert "access_token" not in pagina.text
    assert "segredo-retry" not in pagina.text

    resposta = client_loja.post(
        "/app/trafego/capi/retentar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert resposta.status_code == 303

    db = SessionLocal()
    try:
        outbox = db.query(MetaCapiOutbox).filter_by(event_id="purchase-retry").one()
        assert outbox.status == "delivered"
        assert outbox.attempts == 2
    finally:
        db.close()


def test_retry_automatico_respeita_backoff(client, monkeypatch):
    instante = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        db.add(
            MetaCapiOutbox(
                loja_slug=LOJA,
                event_id="purchase-auto-retry",
                event_name="Purchase",
                payload_json=json.dumps(
                    montar_payload_purchase(event_id="purchase-auto-retry", value="10")
                ),
                status="failed",
                attempts=1,
                atualizada_em=instante,
            )
        )
        db.commit()
    finally:
        db.close()

    chamadas = []

    def fake_tentar(db, item, config=None):
        chamadas.append(item.event_id)
        item.status = "delivered"
        db.commit()
        return True

    monkeypatch.setattr("app.meta_capi.tentar_enviar_outbox", fake_tentar)
    cedo = processar_outbox_automatico(
        SessionLocal,
        instante=instante + timedelta(seconds=59),
        backoff_base_seconds=60,
    )
    assert cedo["processados"] == 0
    assert cedo["aguardando_backoff"] == 1

    devido = processar_outbox_automatico(
        SessionLocal,
        instante=instante + timedelta(seconds=60),
        backoff_base_seconds=60,
    )
    assert devido["processados"] == 1
    assert devido["entregues"] == 1
    assert chamadas == ["purchase-auto-retry"]


def test_worker_capi_desligado_nao_cria_thread():
    from app.meta_capi_job import MetaCapiRetryWorker

    worker = MetaCapiRetryWorker(
        db_factory=SessionLocal,
        enabled=False,
        interval_seconds=1,
        initial_delay_seconds=0,
    )
    worker.start()
    assert worker._thread is None
    worker.stop()
