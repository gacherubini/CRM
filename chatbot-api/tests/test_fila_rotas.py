def test_criar_e_listar_vendedor(client, loja_a):
    resposta = client.post(
        "/v1/fila-vendedores",
        json={"nome": "João", "telefone": "(11) 99999-8888", "ordem": 0},
        headers=loja_a["headers"],
    )
    assert resposta.status_code == 201
    criado = resposta.json()
    assert criado["nome"] == "João"
    # Normalizado na entrada: o lojista digita como quiser.
    assert criado["telefone"] == "11999998888"

    listagem = client.get("/v1/fila-vendedores", headers=loja_a["headers"])
    assert [v["nome"] for v in listagem.json()] == ["João"]


def test_sem_credencial_e_401(client):
    assert client.get("/v1/fila-vendedores").status_code == 401


def test_apagar_e_inativacao_logica(client, loja_a):
    criado = client.post(
        "/v1/fila-vendedores",
        json={"nome": "João", "telefone": "11999998888", "ordem": 0},
        headers=loja_a["headers"],
    ).json()

    assert client.delete(
        f"/v1/fila-vendedores/{criado['id']}", headers=loja_a["headers"]
    ).status_code == 204

    assert client.get("/v1/fila-vendedores", headers=loja_a["headers"]).json() == []
