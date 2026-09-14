"""Ensure interno de cliente+credencial por loja_slug (provisionamento sem CLI)."""
from fastapi.testclient import TestClient

from app import config
from app.auth import hash_token
from app.main import app
from app.models_db import ClienteApiORM, CredencialApiORM

SEGREDO = "segredo-provisionamento"
ROTA = "/v1/internal/provisioning/ensure-cliente"


def _svc():
    return TestClient(app, headers={"Authorization": f"Bearer {SEGREDO}"})


def _liga(monkeypatch, valor=SEGREDO):
    monkeypatch.setattr(config, "PROVISIONING_TOKEN", valor)


def test_cria_cliente_e_credencial_e_devolve_token_uma_vez(db, monkeypatch):
    _liga(monkeypatch)
    r = _svc().post(ROTA, json={"loja_slug": "loja-nova"})
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["ja_existia"] is False
    assert corpo["loja_slug"] == "loja-nova"
    token = corpo["token"]
    assert token
    cliente_id = corpo["cliente_id"]

    db.expire_all()
    cliente = db.get(ClienteApiORM, cliente_id)
    assert cliente is not None
    assert cliente.nome == "loja-nova"
    creds = db.query(CredencialApiORM).filter_by(cliente_id=cliente_id).all()
    assert len(creds) == 1
    # Só o hash fica no banco; o claro aparece só nesta resposta.
    assert creds[0].token_hash == hash_token(token)
    assert token not in creds[0].token_hash

    # O token emitido autentica como Bearer de cliente nas rotas /v1/*.
    como_cliente = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    assert como_cliente.get("/v1/provedores/credenciais").status_code == 200

    # Interno: fora da superfície pública (OpenAPI).
    assert ROTA not in app.openapi()["paths"]


def test_segunda_chamada_nao_emite_nada_nem_devolve_token(db, monkeypatch):
    _liga(monkeypatch)
    svc = _svc()
    primeira = svc.post(ROTA, json={"loja_slug": " Loja-X "})
    assert primeira.status_code == 201
    corpo1 = primeira.json()
    assert corpo1["loja_slug"] == "loja-x"  # bordas aparadas, minúsculas
    n_cred = (
        db.query(CredencialApiORM).filter_by(cliente_id=corpo1["cliente_id"]).count()
    )

    segunda = svc.post(ROTA, json={"loja_slug": "loja-x"})
    assert segunda.status_code == 200
    assert segunda.json() == {
        "cliente_id": corpo1["cliente_id"],
        "loja_slug": "loja-x",
        "ja_existia": True,
        "token": None,
    }

    db.expire_all()
    assert (
        db.query(CredencialApiORM).filter_by(cliente_id=corpo1["cliente_id"]).count()
        == n_cred
    )
    assert db.query(ClienteApiORM).filter_by(nome="loja-x").count() == 1


def test_sem_env_responde_503_fail_closed_e_nao_cria_nada(db, monkeypatch):
    monkeypatch.setattr(config, "PROVISIONING_TOKEN", "")
    r = _svc().post(ROTA, json={"loja_slug": "loja-qualquer"})
    assert r.status_code == 503
    assert r.json()["erro"]["code"] == "provisionamento_indisponivel"
    db.expire_all()
    assert db.query(ClienteApiORM).filter_by(nome="loja-qualquer").count() == 0


def test_slug_invalido_retorna_422_no_padrao(monkeypatch):
    _liga(monkeypatch)
    svc = _svc()
    for invalido in [
        "",
        "   ",
        "loja com espaco",
        "loja!",
        "-loja",
        "loja-",
        "loja_ok",
        "a" * 121,
    ]:
        r = svc.post(ROTA, json={"loja_slug": invalido})
        assert r.status_code == 422, invalido
        corpo = r.json()
        assert corpo["erro"]["code"] == "loja_slug_invalido", invalido
        assert corpo["erro"]["message"], invalido

    sem_chave = svc.post(ROTA, json={})
    assert sem_chave.status_code == 422
    assert sem_chave.json()["erro"]["code"] == "loja_slug_invalido"


def test_bearer_de_cliente_nao_autoriza_o_ensure(client, monkeypatch, db):
    _liga(monkeypatch)
    r = client.post(ROTA, json={"loja_slug": "loja-outra"})
    assert r.status_code == 401
    assert r.json()["erro"]["code"] == "nao_autorizado"
    db.expire_all()
    assert db.query(ClienteApiORM).filter_by(nome="loja-outra").count() == 0


def test_token_de_servico_errado_retorna_401(monkeypatch):
    _liga(monkeypatch)
    errado = TestClient(app, headers={"Authorization": "Bearer errado"})
    r = errado.post(ROTA, json={"loja_slug": "loja-outra"})
    assert r.status_code == 401
    assert r.json()["erro"]["code"] == "nao_autorizado"
