from decimal import Decimal

import pytest

from app.cripto import cifrar
from app.db import SessionLocal
from app.meta_capi import (
    enfileirar_purchase,
    montar_payload_purchase,
    processar_outbox_pendentes,
)
from app.models import MetaPixelConfig, PixelCapiAuditoria, agora
from app.pixel_capi_auditoria import flags_do_payload_capi, listar_auditoria_pixel
from tests.conftest import csrf_da_resposta

LOJA = "loja-teste"


@pytest.fixture
def client_com_loja(client_logado):
    """Gestor Revy logado com uma loja selecionada na sessão."""
    home = client_logado.get("/app")
    assert home.status_code == 200
    r = client_logado.post(
        "/app/loja",
        data={"loja_slug": LOJA, "csrf": csrf_da_resposta(home)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client_logado


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


def test_enfileirar_purchase_gera_auditoria(monkeypatch):
    db = SessionLocal()
    try:
        db.add(
            MetaPixelConfig(
                loja_slug=LOJA,
                pixel_id="112233445566778",
                token_ciphertext=cifrar("tok-capi"),
                enviar_purchase=True,
                atualizada_em=agora(),
            )
        )
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "app.meta_capi.enviar_eventos_capi",
        lambda **k: type("R", (), {"status_code": 200})(),
    )

    db = SessionLocal()
    try:
        out = enfileirar_purchase(
            db,
            loja_slug=LOJA,
            venda_id="venda-aud-1",
            event_id="purchase-venda-aud-1",
            value=Decimal("15000"),
            lead={"telefone": "551188887777", "fbclid": "fbclidXYZ"},
        )
        assert out is not None
        processar_outbox_pendentes(db, LOJA)
        rows = listar_auditoria_pixel(db, LOJA)
        origens = {r.origem for r in rows}
        assert "purchase_web" in origens
        web = next(r for r in rows if r.origem == "purchase_web")
        assert web.tem_ph is True
        assert web.tem_fbclid is True
        assert web.tem_fbc is True
        assert web.pixel_id_sufixo == "566778"
        assert "envio_outbox" in origens
        outbox_row = next(r for r in rows if r.origem == "envio_outbox")
        assert outbox_row.status == "delivered"
        assert outbox_row.http_status == 200
        # O filtro por origem devolve só a fatia pedida.
        so_web = listar_auditoria_pixel(db, LOJA, origem="purchase_web")
        assert {r.origem for r in so_web} == {"purchase_web"}
    finally:
        db.close()


def test_ui_pixel_auditoria_e_config_salva(client_com_loja):
    p = client_com_loja.get("/app/trafego")
    assert p.status_code == 200
    # Rotulos casam com o menu: "Auditoria Pixel" virou "Conferir Pixel".
    assert "Conferir Pixel" in p.text
    csrf = csrf_da_resposta(p)
    r = client_com_loja.post(
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

    page = client_com_loja.get("/app/trafego/pixel-auditoria")
    assert page.status_code == 200
    assert "Conferir Pixel" in page.text
    assert "config_salva" in page.text

    db = SessionLocal()
    try:
        cfg_rows = (
            db.query(PixelCapiAuditoria)
            .filter(
                PixelCapiAuditoria.loja_slug == LOJA,
                PixelCapiAuditoria.origem == "config_salva",
            )
            .all()
        )
        assert len(cfg_rows) >= 1
        assert cfg_rows[0].enviar_purchase is True
        assert cfg_rows[0].pixel_id_sufixo == "544332"
        assert cfg_rows[0].detalhe == "token_atualizado"
    finally:
        db.close()
