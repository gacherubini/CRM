def _novo():
    return {"tipo": "moto", "marca": "Honda", "modelo": "CG 160", "ano_modelo": 2023, "preco": 16000}


def test_sem_credencial_401(client):
    assert client.get("/v1/veiculos").status_code == 401
    assert client.post("/v1/veiculos", json=_novo()).status_code == 401


def test_credencial_invalida_401(client):
    r = client.get("/v1/veiculos", headers={"Authorization": "Bearer nao-existe"})
    assert r.status_code == 401


def test_loja_b_nao_le_veiculo_da_loja_a(client, loja_a, loja_b):
    vid = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"]).json()["id"]
    # loja B não enxerga o veículo da loja A, mesmo com o ID em mãos
    assert client.get(f"/v1/veiculos/{vid}", headers=loja_b["headers"]).status_code == 404
    assert client.get("/v1/veiculos", headers=loja_b["headers"]).json()["veiculos"] == []


def test_loja_b_nao_altera_veiculo_da_loja_a(client, loja_a, loja_b):
    vid = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"]).json()["id"]
    assert client.patch(
        f"/v1/veiculos/{vid}", json={"preco": 1}, headers=loja_b["headers"]
    ).status_code == 404
    assert client.post(f"/v1/veiculos/{vid}/vender", headers=loja_b["headers"]).status_code == 404
