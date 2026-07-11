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
