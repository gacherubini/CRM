import pytest

from app.models_db import FilaVendedor, LojaOperacionalProjecao
from app.rodizio import abrir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    db.add(LojaOperacionalProjecao(
        loja_id=loja_a["loja_id"], aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-{loja_a['loja_id'][:8]}",
    ))
    db.commit()


def _fila(db, loja_id):
    db.add(FilaVendedor(
        id=f"{loja_id[:8]}-f0", loja_id=loja_id, nome="Ana",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()


def test_lista_oferta_aberta_com_nome_do_vendedor(client, db, loja_a):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    corpo = client.get("/v1/ofertas", headers=loja_a["headers"]).json()

    assert [o["id"] for o in corpo] == [oferta.id]
    assert corpo[0]["vendedor_nome"] == "Ana"
    assert corpo[0]["estado"] == "aberta"


def test_filtra_por_estado(client, db, loja_a):
    _fila(db, loja_a["loja_id"])
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    assert client.get(
        "/v1/ofertas", params={"estado": "travada"}, headers=loja_a["headers"]
    ).json() == []


def test_loja_so_ve_as_proprias_ofertas(client, db, loja_a, loja_b):
    _fila(db, loja_a["loja_id"])
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    assert client.get("/v1/ofertas", headers=loja_b["headers"]).json() == []


def test_sem_credencial_e_401(client):
    assert client.get("/v1/ofertas").status_code == 401
