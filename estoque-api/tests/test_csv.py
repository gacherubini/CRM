CSV_VALIDO = """codigo_interno;tipo;marca;modelo;ano_modelo;km;preco;custo
C001;carro;Chevrolet;Onix;2023;12000;78900,00;70000,00
M001;moto;Honda;CG 160;2024;500;19500,00;17000,00
""".encode()


def test_preview_csv_valida_sem_gravar(client, loja_a):
    resposta = client.post(
        "/v1/importacoes/csv/preview",
        content=CSV_VALIDO,
        headers=loja_a["headers"] | {"Content-Type": "text/csv"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["valido"] is True
    assert resposta.json()["total_linhas"] == 2
    assert client.get("/v1/veiculos", headers=loja_a["headers"]).json()["veiculos"] == []


def test_importacao_csv_e_idempotente_por_codigo_interno(client, loja_a):
    headers = loja_a["headers"] | {"Content-Type": "text/csv"}
    primeira = client.post(
        "/v1/importacoes/csv?nome_arquivo=lote.csv", content=CSV_VALIDO, headers=headers
    )
    assert primeira.status_code == 201
    assert primeira.json()["importadas"] == 2
    assert primeira.json()["atualizadas"] == 0

    alterado = CSV_VALIDO.replace(b"78900,00", b"79900,00")
    segunda = client.post("/v1/importacoes/csv", content=alterado, headers=headers)
    assert segunda.status_code == 201
    assert segunda.json()["importadas"] == 0
    assert segunda.json()["atualizadas"] == 2
    veiculos = client.get("/v1/veiculos", headers=loja_a["headers"]).json()["veiculos"]
    assert len(veiculos) == 2
    assert next(v for v in veiculos if v["codigo_interno"] == "C001")["preco"] == 79900.0


def test_importacao_parcial_informa_erros_por_linha(client, loja_a):
    csv = b"tipo,marca,modelo,ano_modelo,preco\ncarro,Ford,Ka,2020,45000\naviao,X,Y,2020,10\n"
    resposta = client.post(
        "/v1/importacoes/csv", content=csv,
        headers=loja_a["headers"] | {"Content-Type": "text/csv"},
    )
    assert resposta.status_code == 201
    assert resposta.json()["status"] == "concluida_com_erros"
    assert resposta.json()["importadas"] == 1
    assert resposta.json()["erros"][0]["linha"] == 3


def test_operador_nao_importa_custo_e_exportacao_nao_expoe_custo(
    client, loja_a, operador_loja_a
):
    headers = operador_loja_a["headers"] | {"Content-Type": "text/csv"}
    resposta = client.post("/v1/importacoes/csv", content=CSV_VALIDO, headers=headers)
    assert resposta.status_code == 201
    assert resposta.json()["importadas"] == 0
    assert len(resposta.json()["erros"]) == 2

    client.post(
        "/v1/veiculos",
        json={"tipo": "carro", "marca": "VW", "modelo": "Polo", "ano_modelo": 2024, "preco": 90000, "custo": 80000},
        headers=loja_a["headers"],
    )
    exportado = client.get("/v1/veiculos.csv", headers=operador_loja_a["headers"])
    assert exportado.status_code == 200
    assert "custo" not in exportado.text.splitlines()[0]
    assert "80000" not in exportado.text


def test_csv_sem_colunas_obrigatorias_retorna_422(client, loja_a):
    resposta = client.post(
        "/v1/importacoes/csv/preview", content=b"marca;modelo\nHonda;Civic\n",
        headers=loja_a["headers"] | {"Content-Type": "text/csv"},
    )
    assert resposta.status_code == 422
