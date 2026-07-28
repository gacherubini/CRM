from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from app import config as config_mod
from app.db import SessionLocal
from app.models import Campanha, CampanhaGasto, Venda, novo_id


def _token(monkeypatch, valor: str = "tok-teste-svc"):
    config_mod.settings = replace(config_mod.settings, service_token=valor)
    return {"X-Service-Token": valor}


def test_resultados_exige_token(client):
    config_mod.settings = replace(config_mod.settings, service_token="tok-obrigatorio")
    r = client.get("/v1/lojas/loja-teste/resultados?periodo=7d")
    assert r.status_code == 401


def test_resultados_ok(client, monkeypatch):
    headers = _token(monkeypatch)
    db = SessionLocal()
    try:
        c = Campanha(
            id=novo_id(),
            loja_slug="loja-teste",
            nome="Seminovos",
            canal="meta",
            status="ativa",
            utm_campaign="seminovos-julho",
            utm_campaign_norm="seminovos-julho",
            criada_por_email="t@t.com",
        )
        db.add(c)
        db.add(
            CampanhaGasto(
                id=novo_id(),
                campanha_id=c.id,
                loja_slug="loja-teste",
                valor=Decimal("1000.00"),
                referencia=date.today(),
                criada_por="t@t.com",
            )
        )
        db.add(
            Venda(
                id=novo_id(),
                loja_slug="loja-teste",
                vendedor_email="v@t.com",
                descricao="moto",
                preco_venda=Decimal("5000.00"),
                status="confirmada",
                campanha_id_last=c.id,
                utm_campaign_last="seminovos-julho",
                criada_em=datetime.now(timezone.utc),
                confirmada_em=datetime.now(timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/v1/lojas/loja-teste/resultados?periodo=7d", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loja_slug"] == "loja-teste"
    assert body["totais"]["vendas"] >= 1
    assert body["totais"]["gasto"] == "1000.00"
    assert body["tem_campanhas"] is True


def test_venda_confirmada_idempotente(client, monkeypatch):
    headers = _token(monkeypatch)
    payload = {
        "venda_id": "venda-xyz",
        "valor": "1000.00",
        "moeda": "BRL",
        "event_id": "purchase-venda-xyz",
    }
    r1 = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json=payload,
        headers=headers,
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/v1/lojas/loja-demo/eventos/venda-confirmada",
        json=payload,
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json().get("idempotent") is True
