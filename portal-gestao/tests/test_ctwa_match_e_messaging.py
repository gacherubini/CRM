from decimal import Decimal
from unittest.mock import MagicMock

from app.campanhas import lead_casa_campanha
from app.conversions.bus import publish_conversion
from app.conversions.meta import MetaAdapter
from app.conversions.meta_messaging import MetaMessagingAdapter
from app.conversions.types import ConversionKind, PurchaseConversion
from app.meta_capi_messaging import montar_payload_purchase_messaging
from app.models import Campanha, novo_id


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


def test_messaging_adapter_noop_sem_clid():
    calls = []

    def fake_enq(*a, **k):
        calls.append(k)
        return MagicMock()

    import app.conversions.meta_messaging as mm

    mm.meta_capi_messaging.enfileirar_purchase_messaging = fake_enq  # type: ignore
    adapter = MetaMessagingAdapter()
    payload = PurchaseConversion(
        loja_slug="loja",
        venda_id="v1",
        event_id="purchase-v1",
        value=Decimal("100"),
        ctwa_clid=None,
        phone="5511",
    )
    assert adapter.handle(ConversionKind.PURCHASE, payload, object()) is None
    assert calls == []

    payload2 = PurchaseConversion(
        loja_slug="loja",
        venda_id="v1",
        event_id="purchase-v1",
        value=Decimal("100"),
        ctwa_clid="ARA1",
        phone="5511",
    )
    adapter.handle(ConversionKind.PURCHASE, payload2, object())
    assert len(calls) == 1
    assert calls[0]["ctwa_clid"] == "ARA1"
    assert calls[0]["event_id"] == "purchase-msg-v1"


def test_bus_chama_web_e_messaging(monkeypatch):
    seen = []

    class A:
        name = "web"

        def handle(self, kind, payload, db):
            seen.append("web")

    class B:
        name = "msg"

        def handle(self, kind, payload, db):
            seen.append("msg")

    p = PurchaseConversion(
        loja_slug="l",
        venda_id="1",
        event_id="purchase-1",
        value=Decimal("1"),
        ctwa_clid="x",
    )
    publish_conversion(ConversionKind.PURCHASE, p, object(), adapters=[A(), B()])
    assert seen == ["web", "msg"]


def test_adapters_meta_enfileiram_um_unico_purchase_ctwa(monkeypatch):
    web = []
    messaging = []

    monkeypatch.setattr(
        "app.conversions.meta.meta_capi.enfileirar_purchase",
        lambda *args, **kwargs: web.append(kwargs),
    )
    monkeypatch.setattr(
        "app.conversions.meta_messaging.meta_capi_messaging.enfileirar_purchase_messaging",
        lambda *args, **kwargs: messaging.append(kwargs),
    )

    payload = PurchaseConversion(
        loja_slug="loja",
        venda_id="venda-ctwa",
        event_id="purchase-venda-ctwa",
        value=Decimal("25000"),
        ctwa_clid="ARA-click",
        phone="5511999999999",
    )
    MetaAdapter().handle(ConversionKind.PURCHASE, payload, object())
    MetaMessagingAdapter().handle(ConversionKind.PURCHASE, payload, object())

    assert web == []
    assert len(messaging) == 1
    assert messaging[0]["event_id"] == "purchase-msg-venda-ctwa"


def test_from_sale_carrega_ctwa_clid():
    class V:
        id = "venda-9"
        loja_slug = "loja"
        preco_venda = Decimal("5000")
        lead_ref = "lead-1"

    p = PurchaseConversion.from_sale(V(), {"telefone": "55", "ctwa_clid": "ARAx"})
    assert p.ctwa_clid == "ARAx"
    assert p.event_id == "purchase-venda-9"
