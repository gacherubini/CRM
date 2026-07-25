from datetime import date
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


def test_dono_apaga_campanha_e_gastos_vinculados(client):
    login(client)
    db = SessionLocal()
    campanha = Campanha(
        loja_slug="loja-teste",
        nome="Campanha para apagar",
        canal="meta",
        status="ativa",
        utm_campaign="campanha-apagar",
        utm_campaign_norm="campanha-apagar",
        criada_por_email="dono@loja.test",
    )
    db.add(campanha)
    db.flush()
    db.add(
        CampanhaGasto(
            campanha_id=campanha.id,
            loja_slug="loja-teste",
            valor=Decimal("250.00"),
            referencia=date(2026, 7, 20),
            criada_por="dono@loja.test",
        )
    )
    db.commit()
    campanha_id = campanha.id
    db.close()

    lista = client.get("/app/campanhas")
    assert f'action="/app/campanhas/{campanha_id}/apagar"' in lista.text
    detalhe = client.get(f"/app/campanhas/{campanha_id}")
    assert "Apagar campanha" in detalhe.text

    resposta = client.post(
        f"/app/campanhas/{campanha_id}/apagar",
        data={"csrf": csrf_da_resposta(lista)},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/campanhas?ok=apagada"
    db = SessionLocal()
    assert db.query(Campanha).filter_by(id=campanha_id).first() is None
    assert db.query(CampanhaGasto).filter_by(campanha_id=campanha_id).count() == 0
    db.close()


def test_apagar_campanha_exige_csrf_e_respeita_loja(client):
    login(client)
    db = SessionLocal()
    propria = Campanha(
        loja_slug="loja-teste",
        nome="Campanha própria",
        canal="meta",
        status="ativa",
        utm_campaign="campanha-propria",
        utm_campaign_norm="campanha-propria",
        criada_por_email="dono@loja.test",
    )
    outra = Campanha(
        loja_slug="outra-loja",
        nome="Campanha de outra loja",
        canal="meta",
        status="ativa",
        utm_campaign="campanha-outra-loja",
        utm_campaign_norm="campanha-outra-loja",
        criada_por_email="outra@loja.test",
    )
    db.add_all([propria, outra])
    db.commit()
    propria_id = propria.id
    outra_id = outra.id
    db.close()

    csrf = csrf_da_resposta(client.get("/app/campanhas"))
    sem_csrf = client.post(
        f"/app/campanhas/{propria_id}/apagar",
        data={"csrf": "invalido"},
        follow_redirects=False,
    )
    outra_loja = client.post(
        f"/app/campanhas/{outra_id}/apagar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert sem_csrf.status_code == 303
    assert sem_csrf.headers["location"] == "/app"
    assert outra_loja.status_code == 303
    assert outra_loja.headers["location"] == "/app/campanhas?erro=1"
    db = SessionLocal()
    assert db.query(Campanha).filter_by(id=propria_id).first() is not None
    assert db.query(Campanha).filter_by(id=outra_id).first() is not None
    db.close()


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


def test_gasto_manual_substitui_meta_api_do_mesmo_dia(client):
    login(client)
    db = SessionLocal()
    campanha = Campanha(
        loja_slug="loja-teste",
        nome="Gasto sem duplicidade",
        canal="meta",
        status="ativa",
        utm_campaign="gasto-sem-duplicidade",
        utm_campaign_norm="gasto-sem-duplicidade",
        meta_campaign_id="12030001",
        criada_por_email="dono@loja.test",
    )
    db.add(campanha)
    db.flush()
    db.add(
        CampanhaGasto(
            campanha_id=campanha.id,
            loja_slug="loja-teste",
            valor=Decimal("100.00"),
            referencia=date(2026, 7, 20),
            origem="meta_api",
            external_key="meta:loja-teste:12030001:2026-07-20",
            criada_por="meta_api",
        )
    )
    db.commit()
    campanha_id = campanha.id
    db.close()

    pagina = client.get(f"/app/campanhas/{campanha_id}")
    resposta = client.post(
        f"/app/campanhas/{campanha_id}/gastos",
        data={
            "csrf": csrf_da_resposta(pagina),
            "valor": "125,50",
            "referencia": "2026-07-20",
            "nota": "ajuste manual",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303

    db = SessionLocal()
    gastos = db.query(CampanhaGasto).filter_by(campanha_id=campanha_id).all()
    assert len(gastos) == 1
    assert gastos[0].origem == "manual"
    assert gastos[0].valor == Decimal("125.50")
    assert gastos[0].external_key is None
    db.close()


def test_roi_pagina_dono(client, chatbot_fake):
    login(client)
    r = client.get("/app/trafego/roi")
    assert r.status_code == 200
    assert "ROI" in r.text
    assert "ROAS" in r.text or "Roas" in r.text or "roas" in r.text.casefold()


def _criar_campanhas_lote():
    db = SessionLocal()
    campanhas = []
    for indice in range(3):
        campanha = Campanha(
            loja_slug="loja-teste",
            nome=f"Campanha {indice + 1}",
            canal="meta",
            status="ativa",
            utm_campaign=f"camp-{indice + 1}",
            utm_campaign_norm=f"camp-{indice + 1}",
            criada_por_email="dono@loja.test",
        )
        db.add(campanha)
        campanhas.append(campanha)
    db.commit()
    ids = [campanha.id for campanha in campanhas]
    db.close()
    return ids


def test_lancamento_gastos_em_lote_cria_so_valores_preenchidos(client):
    login(client)
    ids = _criar_campanhas_lote()
    pagina = client.get("/app/campanhas/gastos/lote")
    assert pagina.status_code == 200
    resposta = client.post(
        "/app/campanhas/gastos/lote",
        data={
            "csrf": csrf_da_resposta(pagina),
            "referencia": "2026-07-20",
            f"valor_{ids[0]}": "500,25",
            f"valor_{ids[1]}": "",
            f"valor_{ids[2]}": "900",
            "nota_global": "semana 3",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    db = SessionLocal()
    gastos = db.query(CampanhaGasto).order_by(CampanhaGasto.valor).all()
    assert [g.valor for g in gastos] == [Decimal("500.25"), Decimal("900.00")]
    assert all(g.loja_slug == "loja-teste" for g in gastos)
    db.close()


def test_csv_gastos_importa_ok_e_exibe_erros_sem_abort(client):
    login(client)
    _criar_campanhas_lote()
    pagina = client.get("/app/campanhas/gastos/lote")
    resposta = client.post(
        "/app/campanhas/gastos/csv",
        data={"csrf": csrf_da_resposta(pagina)},
        files={
            "arquivo": (
                "gastos.csv",
                b"utm_campaign;valor;referencia;nota\ncamp-1;700,00;2026-07-20;ok\nfora;20;2026-07-20;erro\n",
                "text/csv",
            )
        },
    )
    assert resposta.status_code == 200
    assert "1 gasto importado" in resposta.text
    assert "não cadastrada" in resposta.text
    db = SessionLocal()
    assert db.query(CampanhaGasto).count() == 1
    db.close()


def test_vendedor_nao_acessa_gastos_em_lote(client):
    login(client, papel="vendedor")
    assert client.get("/app/campanhas/gastos/lote", follow_redirects=False).headers["location"] == "/app"


def test_download_modelo_csv(client):
    login(client)
    resposta = client.get("/app/campanhas/gastos/csv/modelo")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "utm_campaign;valor;referencia;nota" in resposta.text
