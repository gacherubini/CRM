def _novo(**over):
    base = {
        "tipo": "moto",
        "marca": "Honda",
        "modelo": "CG 160",
        "ano_modelo": 2023,
        "preco": 16000,
    }
    base.update(over)
    return base


# --- normalização / validação de placa ---------------------------------------


def test_placa_normalizada_maiuscula_sem_hifen(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(placa="abc-1d23"), headers=loja_a["headers"])
    assert r.status_code == 201
    assert r.json()["placa"] == "ABC1D23"


def test_placa_normaliza_espacos(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(placa=" abc 1234 "), headers=loja_a["headers"])
    assert r.status_code == 201
    assert r.json()["placa"] == "ABC1234"


def test_placa_formato_antigo_valido(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(placa="ABC1234"), headers=loja_a["headers"])
    assert r.status_code == 201
    assert r.json()["placa"] == "ABC1234"


def test_placa_mercosul_valida(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=loja_a["headers"])
    assert r.status_code == 201
    assert r.json()["placa"] == "ABC1D23"


def test_placa_opcional(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"])
    assert r.status_code == 201
    assert r.json()["placa"] is None


def test_placa_invalida_curta_422(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(placa="ABC12"), headers=loja_a["headers"])
    assert r.status_code == 422


def test_placa_invalida_formato_422(client, loja_a):
    # 4 letras + números não é placa válida
    r = client.post("/v1/veiculos", json=_novo(placa="ABCD123"), headers=loja_a["headers"])
    assert r.status_code == 422


def test_placa_vazia_vira_nula(client, loja_a):
    r = client.post("/v1/veiculos", json=_novo(placa=""), headers=loja_a["headers"])
    assert r.status_code == 201
    assert r.json()["placa"] is None


# --- unicidade por loja ------------------------------------------------------


def test_placa_unica_na_mesma_loja_409(client, loja_a):
    h = loja_a["headers"]
    assert client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h).status_code == 201
    # mesma placa (com hífen para provar que compara normalizado) → conflito
    r = client.post("/v1/veiculos", json=_novo(placa="abc-1d23"), headers=h)
    assert r.status_code == 409


def test_placa_mesma_em_lojas_diferentes_ok(client, loja_a, loja_b):
    assert client.post(
        "/v1/veiculos", json=_novo(placa="ABC1D23"), headers=loja_a["headers"]
    ).status_code == 201
    assert client.post(
        "/v1/veiculos", json=_novo(placa="ABC1D23"), headers=loja_b["headers"]
    ).status_code == 201


def test_placa_atualizada_valida_e_normaliza(client, loja_a):
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    r = client.patch(f"/v1/veiculos/{vid}", json={"placa": "xyz-9k88"}, headers=h)
    assert r.status_code == 200
    assert r.json()["placa"] == "XYZ9K88"


def test_placa_atualizada_conflito_409(client, loja_a):
    h = loja_a["headers"]
    client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h)
    vid = client.post("/v1/veiculos", json=_novo(placa="XYZ1234"), headers=h).json()["id"]
    r = client.patch(f"/v1/veiculos/{vid}", json={"placa": "ABC1D23"}, headers=h)
    assert r.status_code == 409


# --- busca por placa (GET /v1/veiculos/por-placa/{placa}) --------------------


def test_por_placa_encontra(client, loja_a):
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h).json()["id"]
    r = client.get("/v1/veiculos/por-placa/ABC1D23", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == vid
    assert body["marca"] == "Honda"
    assert body["modelo"] == "CG 160"
    assert body["ano_modelo"] == 2023
    assert body["preco"] == 16000
    assert body["status"] == "disponivel"


def test_por_placa_normaliza_entrada(client, loja_a):
    h = loja_a["headers"]
    client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h)
    r = client.get("/v1/veiculos/por-placa/abc-1d23", headers=h)
    assert r.status_code == 200


def test_por_placa_404_inexistente(client, loja_a):
    r = client.get("/v1/veiculos/por-placa/ZZZ9Z99", headers=loja_a["headers"])
    assert r.status_code == 404


def test_por_placa_isolamento_entre_lojas(client, loja_a, loja_b):
    client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=loja_a["headers"])
    # loja B não resolve a placa da loja A
    r = client.get("/v1/veiculos/por-placa/ABC1D23", headers=loja_b["headers"])
    assert r.status_code == 404


def test_por_placa_sem_credencial_401(client, loja_a):
    client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=loja_a["headers"])
    assert client.get("/v1/veiculos/por-placa/ABC1D23").status_code == 401


# --- filtro placa em GET /v1/veiculos ----------------------------------------


def test_filtro_placa_na_listagem(client, loja_a):
    h = loja_a["headers"]
    client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h)
    client.post("/v1/veiculos", json=_novo(placa="XYZ1234", modelo="Biz"), headers=h)
    achados = client.get("/v1/veiculos?placa=abc-1d23", headers=h).json()["veiculos"]
    assert len(achados) == 1
    assert achados[0]["modelo"] == "CG 160"


# --- CSV ---------------------------------------------------------------------


def test_csv_export_inclui_placa(client, loja_a):
    h = loja_a["headers"]
    client.post("/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h)
    texto = client.get("/v1/veiculos.csv", headers=h).text
    assert "placa" in texto.splitlines()[0]
    assert "ABC1D23" in texto


def test_csv_import_placa(client, loja_a):
    h = loja_a["headers"]
    csv_txt = (
        "tipo;marca;modelo;ano_modelo;preco;placa\n"
        "moto;Honda;CG 160;2023;16000;abc-1d23\n"
    )
    r = client.post(
        "/v1/importacoes/csv",
        content=csv_txt.encode("utf-8"),
        headers=h | {"Content-Type": "text/csv"},
    )
    assert r.status_code == 201
    assert r.json()["importadas"] == 1
    achado = client.get("/v1/veiculos/por-placa/ABC1D23", headers=h)
    assert achado.status_code == 200
