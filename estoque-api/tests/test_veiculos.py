def _novo():
    return {
        "tipo": "moto",
        "marca": "Honda",
        "modelo": "CG 160",
        "ano_modelo": 2023,
        "preco": 16000,
        "km": 12000,
        "custo": 13000,
    }


def test_criar_veiculo(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"])
    assert r.status_code == 201
    v = r.json()
    assert v["status"] == "disponivel"
    assert v["publicado"] is False
    assert v["loja_id"] == loja_a["loja_id"]


def test_listar_e_filtrar(client, loja_a):
    client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"])
    carro = _novo() | {"tipo": "carro", "marca": "Chevrolet", "modelo": "Onix"}
    client.post("/v1/veiculos", json=carro, headers=loja_a["headers"])

    todos = client.get("/v1/veiculos", headers=loja_a["headers"]).json()["veiculos"]
    assert len(todos) == 2
    carros = client.get("/v1/veiculos?tipo=carro", headers=loja_a["headers"]).json()["veiculos"]
    assert len(carros) == 1 and carros[0]["modelo"] == "Onix"


def test_fluxo_publicar_reservar_vender(client, loja_a):
    vid = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"]).json()["id"]
    h = loja_a["headers"]

    assert client.post(f"/v1/veiculos/{vid}/publicar", headers=h).json()["publicado"] is True
    assert client.post(f"/v1/veiculos/{vid}/despublicar", headers=h).json()["publicado"] is False
    assert client.post(f"/v1/veiculos/{vid}/reservar", headers=h).json()["status"] == "reservado"
    vendido = client.post(f"/v1/veiculos/{vid}/vender", headers=h).json()
    assert vendido["status"] == "vendido"
    assert vendido["publicado"] is False


def test_nao_reserva_veiculo_vendido(client, loja_a):
    vid = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"]).json()["id"]
    h = loja_a["headers"]
    client.post(f"/v1/veiculos/{vid}/vender", headers=h)
    r = client.post(f"/v1/veiculos/{vid}/reservar", headers=h)
    assert r.status_code == 409


def test_nao_publica_veiculo_reservado(client, loja_a):
    vid = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"]).json()["id"]
    h = loja_a["headers"]
    client.post(f"/v1/veiculos/{vid}/reservar", headers=h)
    assert client.post(f"/v1/veiculos/{vid}/publicar", headers=h).status_code == 409


def test_validacao_tipo_e_preco(client, loja_a):
    h = loja_a["headers"]
    assert client.post("/v1/veiculos", json=_novo() | {"tipo": "aviao"}, headers=h).status_code == 422
    assert client.post("/v1/veiculos", json=_novo() | {"preco": 0}, headers=h).status_code == 422


def test_criacao_idempotente_retorna_o_mesmo_veiculo_e_guarda_so_hash(
    client, loja_a, db
):
    from app.models_db import EventoSaida, IdempotenciaCriacaoVeiculo, Veiculo

    headers = loja_a["headers"] | {"Idempotency-Key": "mensagem-wa-secreta-1"}
    payload = _novo() | {"placa": "IDM1P23"}
    primeira = client.post("/v1/veiculos", json=payload, headers=headers)
    repetida = client.post("/v1/veiculos", json=payload, headers=headers)

    assert primeira.status_code == 201
    assert repetida.status_code == 201
    assert repetida.json()["id"] == primeira.json()["id"]
    registros = (
        db.query(IdempotenciaCriacaoVeiculo)
        .filter(IdempotenciaCriacaoVeiculo.loja_id == loja_a["loja_id"])
        .all()
    )
    assert len(registros) == 1
    assert registros[0].chave_hash != "mensagem-wa-secreta-1"
    assert len(registros[0].chave_hash) == 64
    assert (
        db.query(Veiculo).filter(Veiculo.loja_id == loja_a["loja_id"]).count()
        == 1
    )
    assert (
        db.query(EventoSaida)
        .filter(
            EventoSaida.loja_id == loja_a["loja_id"],
            EventoSaida.tipo == "vehicle.created",
        )
        .count()
        == 1
    )


def test_criacao_idempotente_recusa_mesma_chave_com_payload_diferente(
    client, loja_a
):
    headers = loja_a["headers"] | {"Idempotency-Key": "mensagem-wa-conflito"}
    payload = _novo() | {"placa": "IDM2P34"}
    assert client.post("/v1/veiculos", json=payload, headers=headers).status_code == 201

    conflito = client.post(
        "/v1/veiculos",
        json=payload | {"preco": 17000},
        headers=headers,
    )

    assert conflito.status_code == 409
    assert "Idempotency-Key" in conflito.json()["detail"]


def test_chave_idempotente_e_isolada_por_loja(client, loja_a, loja_b):
    payload = _novo() | {"placa": "IDM3P45"}
    chave = {"Idempotency-Key": "mesma-chave-lojas-distintas"}
    a = client.post(
        "/v1/veiculos", json=payload, headers=loja_a["headers"] | chave
    )
    b = client.post(
        "/v1/veiculos", json=payload, headers=loja_b["headers"] | chave
    )

    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["id"] != b.json()["id"]
