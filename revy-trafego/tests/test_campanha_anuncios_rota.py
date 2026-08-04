"""Rota de campanha grava/edita ad_ids (Fase 1) via form real (session + CSRF)."""
from app.db import SessionLocal
from app.models import Campanha, CampanhaAnuncio
from tests.conftest import csrf_da_resposta

LOJA = "loja-teste"


def _selecionar_loja(client, slug: str = LOJA):
    home = client.get("/app")
    assert home.status_code == 200
    r = client.post(
        "/app/loja",
        data={"loja_slug": slug, "csrf": csrf_da_resposta(home)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client


def test_form_grava_e_edita_ad_ids(client_logado):
    client = _selecionar_loja(client_logado)

    # Criar campanha com dois ad_ids (um com lixo/espacos para exercitar a normalizacao).
    p = client.get("/app/campanhas/nova")
    assert p.status_code == 200
    r = client.post(
        "/app/campanhas/nova",
        data={
            "csrf": csrf_da_resposta(p),
            "nome": "MT03 CAUA",
            "canal": "meta",
            "status": "ativa",
            "utm_campaign": "mt03-adids",
            "ad_ids": " 120252470707220341 \n120252470799120341\nabc\n",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionLocal()
    try:
        camp = (
            db.query(Campanha)
            .filter(Campanha.utm_campaign_norm == "mt03-adids")
            .one()
        )
        camp_id = camp.id
        assert {
            a.ad_id for a in db.query(CampanhaAnuncio).filter_by(campanha_id=camp_id)
        } == {"120252470707220341", "120252470799120341"}
        assert {
            a.loja_slug for a in db.query(CampanhaAnuncio).filter_by(campanha_id=camp_id)
        } == {LOJA}
    finally:
        db.close()

    # O form de edicao pre-preenche o textarea com os ad_ids atuais.
    e = client.get(f"/app/campanhas/{camp_id}/editar")
    assert e.status_code == 200
    assert "120252470707220341" in e.text
    assert "120252470799120341" in e.text

    # Reeditar removendo um ad_id -> registro correspondente e apagado.
    r2 = client.post(
        f"/app/campanhas/{camp_id}/editar",
        data={
            "csrf": csrf_da_resposta(e),
            "nome": "MT03 CAUA",
            "canal": "meta",
            "status": "ativa",
            "utm_campaign": "mt03-adids",
            "ad_ids": "120252470707220341\n",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303

    db = SessionLocal()
    try:
        assert {
            a.ad_id for a in db.query(CampanhaAnuncio).filter_by(campanha_id=camp_id)
        } == {"120252470707220341"}
    finally:
        db.close()
