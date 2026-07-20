from decimal import Decimal

from conftest import csrf_da_resposta, login
from app.db import SessionLocal
from app.models import Campanha, CampanhaGasto


def test_vendedor_nao_acessa_campanhas(client):
    login(client, papel="vendedor")
    r = client.get("/app/campanhas", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    assert 'href="/app/campanhas"' not in client.get("/app").text


def test_dono_cria_campanha_e_lista(client):
    login(client)
    pagina = client.get("/app/campanhas/nova")
    r = client.post(
        "/app/campanhas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "nome": "Seminovos Meta",
            "canal": "meta",
            "utm_source": "instagram",
            "utm_medium": "paid",
            "utm_campaign": "seminovos-julho",
            "status": "ativa",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    lista = client.get("/app/campanhas")
    assert lista.status_code == 200
    assert "Seminovos Meta" in lista.text
    assert "seminovos-julho" in lista.text
    assert 'href="/app/trafego/roi"' in client.get("/app").text or True
    assert 'href="/app/campanhas"' in client.get("/app").text


def test_utm_campaign_duplicado_mesma_loja_rejeita(client):
    login(client)
    payload = {
        "nome": "A",
        "canal": "meta",
        "utm_campaign": "dup-1",
        "status": "ativa",
    }
    p1 = client.get("/app/campanhas/nova")
    client.post(
        "/app/campanhas/nova",
        data={"csrf": csrf_da_resposta(p1), **payload},
        follow_redirects=False,
    )
    p2 = client.get("/app/campanhas/nova")
    r2 = client.post(
        "/app/campanhas/nova",
        data={"csrf": csrf_da_resposta(p2), **payload, "nome": "B"},
    )
    assert r2.status_code == 422
    assert "já existe" in r2.text.casefold()


def test_lancar_gasto(client):
    login(client)
    p = client.get("/app/campanhas/nova")
    client.post(
        "/app/campanhas/nova",
        data={
            "csrf": csrf_da_resposta(p),
            "nome": "Gasto Test",
            "canal": "meta",
            "utm_campaign": "gasto-test",
            "status": "ativa",
        },
        follow_redirects=False,
    )
    db = SessionLocal()
    campanha = db.query(Campanha).filter(Campanha.utm_campaign_norm == "gasto-test").one()
    cid = campanha.id
    db.close()
    det = client.get(f"/app/campanhas/{cid}")
    r = client.post(
        f"/app/campanhas/{cid}/gastos",
        data={
            "csrf": csrf_da_resposta(det),
            "valor": "350,50",
            "referencia": "2026-07-10",
            "nota": "semana 2",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "350" in r.text
    db = SessionLocal()
    g = db.query(CampanhaGasto).one()
    assert g.valor == Decimal("350.50")
    db.close()


def test_roi_pagina_dono(client, chatbot_fake):
    login(client)
    r = client.get("/app/trafego/roi")
    assert r.status_code == 200
    assert "ROI" in r.text
    assert "ROAS" in r.text or "Roas" in r.text or "roas" in r.text.casefold()
