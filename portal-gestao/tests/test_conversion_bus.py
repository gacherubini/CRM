"""Fase F — bus de conversões e adapter Meta."""

from decimal import Decimal
from types import SimpleNamespace

from app.conversions.bus import publish_conversion
from app.conversions.meta import MetaAdapter
from app.conversions.types import ConversionKind, PurchaseConversion


def _purchase(**overrides):
    data = {
        "loja_slug": "loja-teste",
        "venda_id": "venda-1",
        "event_id": "purchase-venda-1",
        "value": Decimal("85000.50"),
        "lead_ref": "lead-1",
        "phone": "+55 11 99999-0000",
        "email": "pessoa@example.com",
        "fbclid": "fb-click",
        "fbc": "fb.1.123.fb-click",
        "gclid": "google-click",
        "gbraid": "gbraid-click",
        "wbraid": "wbraid-click",
    }
    data.update(overrides)
    return PurchaseConversion(**data)


class _Adapter:
    def __init__(self, name, calls, *, error=None):
        self.name = name
        self.calls = calls
        self.error = error

    def handle(self, kind, payload, db):
        self.calls.append((self.name, kind, payload, db))
        if self.error:
            raise self.error


def test_purchase_conversion_from_sale_cria_event_id_estavel_e_snapshot():
    sale = SimpleNamespace(
        id="v-42",
        loja_slug="loja-a",
        preco_venda=Decimal("123.45"),
        lead_ref="l-9",
    )
    evento = PurchaseConversion.from_sale(
        sale,
        {
            "telefone": "5511999",
            "fbclid": "fb-1",
            "gclid": "g-1",
            "gbraid": "gb-1",
            "wbraid": "wb-1",
        },
    )

    assert evento.event_id == "purchase-v-42"
    assert evento.value == Decimal("123.45")
    assert evento.currency == "BRL"
    assert evento.lead_ref == "l-9"
    assert evento.phone == "5511999"
    assert evento.fbclid == "fb-1"
    assert evento.gclid == "g-1"
    assert evento.gbraid == "gb-1"
    assert evento.wbraid == "wb-1"


def test_bus_publica_em_multiplos_adapters_sem_rede():
    calls = []
    db = object()
    adapters = [_Adapter("meta", calls), _Adapter("auditoria", calls)]

    result = publish_conversion(
        ConversionKind.PURCHASE,
        _purchase(),
        db,
        adapters=adapters,
    )

    assert [call[0] for call in calls] == ["meta", "auditoria"]
    assert all(call[1] is ConversionKind.PURCHASE for call in calls)
    assert result.attempted == 2
    assert result.accepted == 2
    assert result.failed == 0


def test_bus_aceita_kind_string_do_contrato_publico():
    calls = []
    result = publish_conversion("purchase", _purchase(), object(), adapters=[_Adapter("meta", calls)])

    assert calls[0][1] is ConversionKind.PURCHASE
    assert result.accepted == 1


def test_bus_isola_falha_e_continua_nos_demais_adapters():
    calls = []
    db = SimpleNamespace(rollbacks=0)
    db.rollback = lambda: setattr(db, "rollbacks", db.rollbacks + 1)
    adapters = [
        _Adapter("quebrado", calls, error=RuntimeError("token-secreto")),
        _Adapter("saudavel", calls),
    ]

    result = publish_conversion(
        ConversionKind.PURCHASE,
        _purchase(),
        db,
        adapters=adapters,
    )

    assert [call[0] for call in calls] == ["quebrado", "saudavel"]
    assert result.accepted == 1
    assert result.failed == 1
    assert result.adapters[0].accepted is False
    assert result.adapters[1].accepted is True
    assert db.rollbacks == 1


def test_meta_adapter_traduz_evento_para_outbox_existente(monkeypatch):
    captured = {}

    def fake_enqueue(db, **kwargs):
        captured["db"] = db
        captured.update(kwargs)
        return "outbox"

    monkeypatch.setattr("app.conversions.meta.meta_capi.enfileirar_purchase", fake_enqueue)
    db = object()
    result = MetaAdapter().handle(ConversionKind.PURCHASE, _purchase(), db)

    assert result == "outbox"
    assert captured["db"] is db
    assert captured["loja_slug"] == "loja-teste"
    assert captured["venda_id"] == "venda-1"
    assert captured["event_id"] == "purchase-venda-1"
    assert captured["value"] == Decimal("85000.50")
    assert captured["currency"] == "BRL"
    assert captured["lead"] == {
        "telefone": "+55 11 99999-0000",
        "email": "pessoa@example.com",
        "fbclid": "fb-click",
        "fbc": "fb.1.123.fb-click",
    }


def test_meta_web_nao_enfileira_purchase_ctwa(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        "app.conversions.meta.meta_capi.enfileirar_purchase",
        lambda *args, **kwargs: chamadas.append(kwargs),
    )

    resultado = MetaAdapter().handle(
        ConversionKind.PURCHASE,
        _purchase(ctwa_clid="ARA-click-whatsapp"),
        object(),
    )

    assert resultado is None
    assert chamadas == []


def test_bus_padrao_usa_meta_adapter(monkeypatch):
    calls = []

    def fake_handle(self, kind, payload, db):
        calls.append((self.name, kind, payload.event_id, db))

    monkeypatch.setattr(MetaAdapter, "handle", fake_handle)
    from app.conversions.meta_messaging import MetaMessagingAdapter

    monkeypatch.setattr(MetaMessagingAdapter, "handle", fake_handle)
    db = object()
    result = publish_conversion(ConversionKind.PURCHASE, _purchase(), db)

    assert ("meta", ConversionKind.PURCHASE, "purchase-venda-1", db) in calls
    assert ("meta_messaging", ConversionKind.PURCHASE, "purchase-venda-1", db) in calls
    assert result.accepted == 2
