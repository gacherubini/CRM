from datetime import date
from decimal import Decimal

from app.campanhas import (
    normalizar_utm,
    parse_brl_valor,
    parse_gastos_csv,
    validar_campanha_payload,
)
from app.db import SessionLocal
from app.models import Campanha, CampanhaGasto, novo_id


def test_normalizar_utm_strip_casefold():
    assert normalizar_utm("  Seminovos-Julho ") == "seminovos-julho"
    assert normalizar_utm("") is None
    assert normalizar_utm(None) is None


def test_validar_exige_utm_campaign():
    erros = validar_campanha_payload({
        "nome": "Meta jul",
        "canal": "meta",
        "utm_campaign": "",
    })
    assert any("utm_campaign" in e for e in erros)


def test_validar_ok():
    erros = validar_campanha_payload({
        "nome": "Meta jul",
        "canal": "meta",
        "utm_campaign": "seminovos-julho",
        "status": "ativa",
    })
    assert erros == []


def test_validar_canais_extras_e_rejeitar_desconhecido():
    for canal in ("tiktok", "olx", "marketplace", "facebook_marketplace"):
        assert validar_campanha_payload(
            {"nome": "Campanha", "canal": canal, "utm_campaign": f"utm-{canal}"}
        ) == []
    assert "canal inválido" in validar_campanha_payload(
        {"nome": "Campanha", "canal": "rede-x", "utm_campaign": "utm-x"}
    )


def test_parse_brl_valor_br():
    assert parse_brl_valor("350,50") == Decimal("350.50")
    assert parse_brl_valor("1.200,00") == Decimal("1200.00")
    assert parse_brl_valor("-1") is None


def test_persistir_campanha_e_gasto():
    db = SessionLocal()
    try:
        c = Campanha(
            id=novo_id(),
            loja_slug="loja-teste",
            nome="Seminovos Meta",
            canal="meta",
            status="ativa",
            utm_campaign="seminovos-julho",
            utm_campaign_norm="seminovos-julho",
            criada_por_email="trafego@revy.local",
        )
        db.add(c)
        db.add(
            CampanhaGasto(
                id=novo_id(),
                campanha_id=c.id,
                loja_slug="loja-teste",
                valor=Decimal("500.00"),
                referencia=date(2026, 7, 1),
                criada_por="trafego@revy.local",
            )
        )
        db.commit()
        assert db.query(Campanha).count() == 1
        assert db.query(CampanhaGasto).one().valor == Decimal("500.00")
    finally:
        db.close()


def test_parse_csv_gastos_mantem_linhas_validas_e_reporta_erros():
    campanha = Campanha(
        id=novo_id(), loja_slug="loja-teste", nome="Meta", canal="meta", status="ativa",
        utm_campaign="seminovos-julho", utm_campaign_norm="seminovos-julho",
        criada_por_email="trafego@revy.local",
    )
    csv = (
        "utm_campaign;valor;referencia;nota\n"
        "seminovos-julho;1.200,50;2026-07-14;semana 2\n"
        "nao-existe;800;2026-07-14;\n"
        "seminovos-julho;abc;data;ruim\n"
    ).encode()
    linhas, erros = parse_gastos_csv(csv, [campanha])
    assert len(linhas) == 1
    assert linhas[0].valor == Decimal("1200.50")
    assert linhas[0].referencia == date(2026, 7, 14)
    assert len(erros) == 2
    assert "não cadastrada" in erros[0]
    assert "valor inválido" in erros[1]
