from decimal import Decimal

from conftest import csrf_da_resposta, login
from app.cripto import cifrar
from app.db import SessionLocal
from app.meta_capi import enfileirar_purchase, montar_payload_purchase
from app.models import MetaPixelConfig, PixelCapiAuditoria, agora
from app.pixel_capi_auditoria import flags_do_payload_capi, listar_auditoria_pixel


def test_flags_do_payload():
    body = montar_payload_purchase(
        event_id="purchase-x",
        value=Decimal("10"),
        phone="5511999999999",
        fbclid="IwAR0abc",
    )
    flags = flags_do_payload_capi(body)
    assert flags["tem_ph"] is True
    assert flags["tem_fbc"] is True
    assert flags["tem_external_id"] is True


def test_enfileirar_purchase_gera_auditoria(client, monkeypatch):
    login(client)
    db = SessionLocal()
    db.add(
        MetaPixelConfig(
            loja_slug="loja-teste",
            pixel_id="112233445566778",
            token_ciphertext=cifrar("tok-capi"),
            enviar_purchase=True,
            atualizada_em=agora(),
        )
    )
    db.commit()
    db.close()

    monkeypatch.setattr(
        "app.meta_capi.enviar_eventos_capi",
        lambda **k: type("R", (), {"status_code": 200})(),
    )

    db = SessionLocal()
    out = enfileirar_purchase(
        db,
        loja_slug="loja-teste",
        venda_id="venda-aud-1",
        event_id="purchase-venda-aud-1",
        value=Decimal("15000"),
        lead={"telefone": "551188887777", "fbclid": "fbclidXYZ"},
    )
    assert out is not None
    rows = listar_auditoria_pixel(db, "loja-teste")
    origens = {r.origem for r in rows}
    assert "purchase_web" in origens
    web = next(r for r in rows if r.origem == "purchase_web")
    assert web.tem_ph is True
    assert web.tem_fbclid is True
    assert web.tem_fbc is True
    assert web.pixel_id_sufixo == "566778" or web.pixel_id_sufixo.endswith("778")
    assert "envio_outbox" in origens
    db.close()


def test_ui_pixel_auditoria_e_config_salva(client):
    login(client)
    p = client.get("/app/trafego")
    assert "Auditoria Pixel" in p.text
    csrf = csrf_da_resposta(p)
    r = client.post(
        "/app/trafego",
        data={
            "csrf": csrf,
            "pixel_id": "998877665544332",
            "capi_token": "token-novo-capi",
            "enviar_page_view": "on",
            "enviar_lead": "on",
            "enviar_purchase": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    page = client.get("/app/trafego/pixel-auditoria")
    assert page.status_code == 200
    assert "Auditoria Pixel" in page.text
    assert "config_salva" in page.text or "config" in page.text.lower()

    db = SessionLocal()
    cfg_rows = (
        db.query(PixelCapiAuditoria)
        .filter(
            PixelCapiAuditoria.loja_slug == "loja-teste",
            PixelCapiAuditoria.origem == "config_salva",
        )
        .all()
    )
    assert len(cfg_rows) >= 1
    assert cfg_rows[0].enviar_purchase is True
    db.close()
