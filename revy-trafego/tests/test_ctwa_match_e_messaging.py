"""Match CTWA de campanha + Meta CAPI Business Messaging (Purchase com ctwa_clid).

Porte da suíte equivalente do portal-gestão. O revy-trafego não tem o pacote
``app.conversions`` (bus/adapters): aqui o caminho de produção é
``api_v1.api_venda_confirmada`` -> ``meta_capi_messaging.enfileirar_purchase_messaging``,
então os testes de adapter viram testes diretos do enfileiramento + integração HTTP.

Nenhuma chamada real ao Meta: ``app.meta_capi.enviar_eventos_capi`` é sempre
substituído por um fake (fixture autouse ``capi_http``).
"""

import json
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app import config as config_mod
from app.campanhas import lead_casa_campanha
from app.cripto import cifrar
from app.db import SessionLocal
from app.meta_capi import processar_outbox_pendentes
from app.meta_capi_messaging import (
    enfileirar_purchase_messaging,
    montar_payload_purchase_messaging,
)
from app.models import (
    Campanha,
    MetaCapiOutbox,
    MetaPixelConfig,
    PixelCapiAuditoria,
    novo_id,
)

SERVICE_TOKEN = "tok-ctwa-teste"


class _RespostaFake:
    status_code = 200


@pytest.fixture(autouse=True)
def capi_http(monkeypatch):
    """Intercepta o POST Graph. Devolve a lista de chamadas feitas."""
    chamadas: list[dict] = []

    def fake_enviar(*, pixel_id, access_token, body, timeout=None):
        chamadas.append(
            {"pixel_id": pixel_id, "access_token": access_token, "body": body}
        )
        return _RespostaFake()

    monkeypatch.setattr("app.meta_capi.enviar_eventos_capi", fake_enviar)
    return chamadas


@pytest.fixture
def headers_servico(monkeypatch):
    monkeypatch.setattr(
        config_mod,
        "settings",
        replace(config_mod.settings, service_token=SERVICE_TOKEN),
    )
    return {"X-Service-Token": SERVICE_TOKEN}


def _configurar_pixel(
    loja_slug: str = "loja-demo",
    *,
    enviar_purchase: bool = True,
    test_event_code: str | None = None,
    com_token: bool = True,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            MetaPixelConfig(
                loja_slug=loja_slug,
                pixel_id="123456789012345",
                token_ciphertext=cifrar("token-capi-fake") if com_token else None,
                test_event_code=test_event_code,
                enviar_purchase=enviar_purchase,
            )
        )
        db.commit()
    finally:
        db.close()


def _outbox(event_id: str) -> MetaCapiOutbox | None:
    db = SessionLocal()
    try:
        return (
            db.query(MetaCapiOutbox)
            .filter(MetaCapiOutbox.event_id == event_id)
            .first()
        )
    finally:
        db.close()


def _processar(loja_slug: str = "loja-demo") -> None:
    db = SessionLocal()
    try:
        processar_outbox_pendentes(db, loja_slug)
    finally:
        db.close()


# --------------------------------------------------------------------------
# Match de campanha (CTWA / meta_campaign_id / UTM)
# --------------------------------------------------------------------------


def test_lead_casa_por_codigo_ctwa_e_meta_id():
    c = Campanha(
        id=novo_id(),
        loja_slug="loja-teste",
        nome="CTWA",
        canal="meta",
        status="ativa",
        utm_campaign="outra-utm",
        utm_campaign_norm="outra-utm",
        meta_campaign_id="12033001",
        codigo_ctwa="RV-JUL",
        criada_por_email="x@y.z",
    )
    lead_cod = {"ctwa_codigo": "RV-JUL", "origem": "meta_ctwa"}
    assert lead_casa_campanha(lead_cod, c, modo="last") is True

    lead_meta = {"meta_campaign_id": "12033001"}
    assert lead_casa_campanha(lead_meta, c, modo="last") is True

    lead_utm = {"utm_campaign": "outra-utm"}
    assert lead_casa_campanha(lead_utm, c, modo="last") is True

    assert lead_casa_campanha({"utm_campaign": "x"}, c, modo="last") is False


# --------------------------------------------------------------------------
# Payload messaging
# --------------------------------------------------------------------------


def test_payload_messaging_tem_ctwa_clid():
    body = montar_payload_purchase_messaging(
        event_id="purchase-msg-v1",
        value=Decimal("19900.00"),
        ctwa_clid="ARAabc",
        phone="5511999999999",
    )
    ev = body["data"][0]
    assert ev["action_source"] == "business_messaging"
    assert ev["messaging_channel"] == "whatsapp"
    assert ev["user_data"]["ctwa_clid"] == "ARAabc"
    assert "ph" in ev["user_data"]


def test_payload_messaging_sem_pii_usa_external_id_e_test_event_code():
    body = montar_payload_purchase_messaging(
        event_id="purchase-msg-v2",
        value="150.5",
        ctwa_clid="  ARAxyz  ",
        test_event_code="TEST123",
    )
    ev = body["data"][0]
    assert ev["user_data"]["ctwa_clid"] == "ARAxyz"
    assert "ph" not in ev["user_data"]
    assert "em" not in ev["user_data"]
    assert ev["user_data"]["external_id"]
    assert ev["custom_data"] == {"value": 150.5, "currency": "BRL"}
    assert body["test_event_code"] == "TEST123"


# --------------------------------------------------------------------------
# enfileirar_purchase_messaging: no-ops
# --------------------------------------------------------------------------


def test_enfileirar_messaging_noop_sem_ctwa_clid(client, capi_http):
    _configurar_pixel()
    db = SessionLocal()
    try:
        assert (
            enfileirar_purchase_messaging(
                db,
                loja_slug="loja-demo",
                venda_id="v-sem-clid",
                event_id="purchase-v-sem-clid-msg",
                value=Decimal("100"),
                ctwa_clid=None,
                phone="5511999999999",
            )
            is None
        )
        assert (
            enfileirar_purchase_messaging(
                db,
                loja_slug="loja-demo",
                venda_id="v-clid-vazio",
                event_id="purchase-v-clid-vazio-msg",
                value=Decimal("100"),
                ctwa_clid="   ",
            )
            is None
        )
        assert db.query(MetaCapiOutbox).count() == 0
    finally:
        db.close()
    assert capi_http == []


def test_enfileirar_messaging_noop_sem_config_capi(client, capi_http):
    db = SessionLocal()
    try:
        outbox = enfileirar_purchase_messaging(
            db,
            loja_slug="loja-sem-pixel",
            venda_id="v1",
            event_id="purchase-v1-msg",
            value=Decimal("100"),
            ctwa_clid="ARA1",
        )
        assert outbox is not None
        assert outbox.status == "blocked_config"
        assert db.query(MetaCapiOutbox).count() == 1
    finally:
        db.close()
    assert capi_http == []


def test_enfileirar_messaging_noop_com_purchase_desligado(client, capi_http):
    _configurar_pixel(enviar_purchase=False)
    db = SessionLocal()
    try:
        outbox = enfileirar_purchase_messaging(
            db,
            loja_slug="loja-demo",
            venda_id="v1",
            event_id="purchase-v1-msg",
            value=Decimal("100"),
            ctwa_clid="ARA1",
        )
        assert outbox is not None
        assert outbox.status == "blocked_config"
        assert db.query(MetaCapiOutbox).count() == 1
    finally:
        db.close()
    assert capi_http == []


# --------------------------------------------------------------------------
# enfileirar_purchase_messaging: caminho feliz, idempotência e falha de envio
# --------------------------------------------------------------------------


def test_enfileirar_messaging_grava_outbox_envia_e_audita(client, capi_http):
    _configurar_pixel(test_event_code="TESTE9")
    db = SessionLocal()
    try:
        outbox = enfileirar_purchase_messaging(
            db,
            loja_slug="loja-demo",
            venda_id="venda-ctwa",
            event_id="purchase-venda-ctwa-msg",
            value=Decimal("25000"),
            ctwa_clid="ARA-click",
            phone="5511999999999",
            email="Cliente@Exemplo.COM",
        )
        assert outbox is not None
        _processar()
        db.refresh(outbox)
        assert outbox.status == "delivered"
        assert outbox.last_http_status == 200

        body = json.loads(outbox.payload_json)
        ev = body["data"][0]
        assert ev["action_source"] == "business_messaging"
        assert ev["messaging_channel"] == "whatsapp"
        assert ev["user_data"]["ctwa_clid"] == "ARA-click"
        assert ev["user_data"]["ph"] and ev["user_data"]["em"]
        assert body["test_event_code"] == "TESTE9"

        auditorias = (
            db.query(PixelCapiAuditoria)
            .filter(PixelCapiAuditoria.event_id == "purchase-venda-ctwa-msg")
            .all()
        )
        assert {a.origem for a in auditorias} == {"purchase_messaging", "envio_outbox"}
        assert all(a.modo == "messaging" for a in auditorias)
        assert all(a.tem_ctwa_clid for a in auditorias)
    finally:
        db.close()

    assert len(capi_http) == 1
    assert capi_http[0]["pixel_id"] == "123456789012345"
    assert capi_http[0]["access_token"] == "token-capi-fake"
    assert capi_http[0]["body"]["data"][0]["user_data"]["ctwa_clid"] == "ARA-click"


def test_enfileirar_messaging_idempotente_por_event_id(client, capi_http):
    _configurar_pixel()
    db = SessionLocal()
    try:
        kwargs = dict(
            loja_slug="loja-demo",
            venda_id="venda-dup",
            event_id="purchase-venda-dup-msg",
            value=Decimal("100"),
            ctwa_clid="ARA1",
        )
        primeiro = enfileirar_purchase_messaging(db, **kwargs)
        segundo = enfileirar_purchase_messaging(db, **kwargs)
        assert primeiro is not None and segundo is not None
        assert primeiro.id == segundo.id
        assert db.query(MetaCapiOutbox).count() == 1
    finally:
        db.close()
    _processar()
    assert len(capi_http) == 1


def test_enfileirar_messaging_nao_propaga_falha_de_envio(client, monkeypatch):
    _configurar_pixel()

    def explode(**kwargs):
        raise httpx.RequestError("sem rede", request=None)

    monkeypatch.setattr("app.meta_capi.enviar_eventos_capi", explode)

    db = SessionLocal()
    try:
        outbox = enfileirar_purchase_messaging(
            db,
            loja_slug="loja-demo",
            venda_id="venda-falha",
            event_id="purchase-venda-falha-msg",
            value=Decimal("100"),
            ctwa_clid="ARA1",
        )
        assert outbox is not None
        _processar()
        db.refresh(outbox)
        assert outbox.status == "failed"
        assert outbox.attempts == 1
        assert outbox.last_error == "Falha de rede ao contatar a Meta."
    finally:
        db.close()


# --------------------------------------------------------------------------
# Integração: POST /v1/lojas/{slug}/eventos/venda-confirmada
# --------------------------------------------------------------------------


def test_venda_confirmada_com_ctwa_clid_usa_messaging(
    client, headers_servico, capi_http
):
    _configurar_pixel()
    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json={
            "venda_id": "venda-1",
            "valor": "19900.00",
            "moeda": "BRL",
            "ctwa_clid": "ARA-clique",
            "cliente_telefone": "5511999999999",
        },
        headers=headers_servico,
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    _processar()

    outbox = _outbox("purchase-venda-1-msg")
    assert outbox is not None, "messaging deve usar event_id com sufixo -msg"
    ev = json.loads(outbox.payload_json)["data"][0]
    assert ev["action_source"] == "business_messaging"
    assert ev["user_data"]["ctwa_clid"] == "ARA-clique"
    assert ev["custom_data"]["value"] == 19900.0
    assert len(capi_http) == 1


def test_venda_confirmada_sem_ctwa_clid_usa_web(client, headers_servico, capi_http):
    _configurar_pixel()
    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json={
            "venda_id": "venda-2",
            "valor": "500.00",
            "fbclid": "IwAR-abc",
            "cliente_telefone": "5511988887777",
        },
        headers=headers_servico,
    )
    assert r.status_code == 200, r.text
    _processar()

    assert _outbox("purchase-venda-2-msg") is None
    outbox = _outbox("purchase-venda-2")
    assert outbox is not None
    ev = json.loads(outbox.payload_json)["data"][0]
    assert ev["action_source"] == "system_generated"
    assert "ctwa_clid" not in ev["user_data"]
    assert ev["user_data"]["fbc"].endswith("IwAR-abc")
    assert len(capi_http) == 1


def test_venda_confirmada_ctwa_sem_config_fica_bloqueada(
    client, headers_servico, capi_http
):
    r = client.post(
        "/v1/lojas/loja-sem-pixel/eventos/venda-confirmada",
        json={
            "venda_id": "venda-3",
            "valor": "100.00",
            "ctwa_clid": "ARA-x",
        },
        headers=headers_servico,
    )
    assert r.status_code == 200, r.text

    outbox = _outbox("purchase-venda-3-msg")
    assert outbox is not None
    assert outbox.status == "blocked_config"
    assert json.loads(outbox.payload_json)["data"][0]["user_data"]["ctwa_clid"] == "ARA-x"
    assert capi_http == []


def test_venda_confirmada_com_ctwa_nao_duplica_outbox(
    client, headers_servico, capi_http
):
    """Reenvio do mesmo evento não pode gerar segundo Purchase messaging."""
    _configurar_pixel()
    payload = {
        "venda_id": "venda-4",
        "valor": "1000.00",
        "ctwa_clid": "ARA-dup",
    }
    r1 = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json=payload,
        headers=headers_servico,
    )
    r2 = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json=payload,
        headers=headers_servico,
    )
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["outbox_id"] == r2.json()["outbox_id"]
    _processar()

    db = SessionLocal()
    try:
        assert db.query(MetaCapiOutbox).count() == 1
    finally:
        db.close()
    assert len(capi_http) == 1


def test_venda_confirmada_exige_service_token(client):
    r = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json={"venda_id": "venda-5", "valor": "10.00", "ctwa_clid": "ARA-y"},
    )
    assert r.status_code in (401, 503)
    assert _outbox("purchase-venda-5") is None
