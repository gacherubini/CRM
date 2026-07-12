def _novo(**extra):
    return {
        "tipo": "carro",
        "marca": "Toyota",
        "modelo": "Corolla",
        "ano_modelo": 2024,
        "preco": 145000,
    } | extra


def test_operador_gerencia_estoque_mas_nao_ve_nem_altera_custo(
    client, loja_a, operador_loja_a
):
    dono = loja_a["headers"]
    operador = operador_loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(custo=120000), headers=dono).json()["id"]

    visto = client.get(f"/v1/veiculos/{vid}", headers=operador)
    assert visto.status_code == 200
    assert "custo" not in visto.json()
    assert client.patch(
        f"/v1/veiculos/{vid}", json={"custo": 1}, headers=operador
    ).status_code == 403
    assert client.post(
        "/v1/veiculos", json=_novo(custo=1), headers=operador
    ).status_code == 403


def test_leitor_nao_altera_estoque(client, loja_a, leitor_loja_a):
    vid = client.post("/v1/veiculos", json=_novo(), headers=loja_a["headers"]).json()["id"]
    assert client.get(f"/v1/veiculos/{vid}", headers=leitor_loja_a["headers"]).status_code == 200
    assert client.patch(
        f"/v1/veiculos/{vid}", json={"preco": 1}, headers=leitor_loja_a["headers"]
    ).status_code == 403


def test_fotos_ordenadas_aparecem_na_api_privada_e_publica(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    urls = ["https://img.test/frente.jpg", "https://img.test/traseira.jpg"]

    resposta = client.put(f"/v1/veiculos/{vid}/fotos", json={"urls": urls}, headers=h)
    assert resposta.status_code == 200
    assert resposta.json()["fotos"] == urls
    assert resposta.json()["foto_url"] == urls[0]

    client.post(f"/v1/veiculos/{vid}/publicar", headers=h)
    publico = client.get(f"/public/v1/lojas/{slug}/veiculos/{vid}").json()
    assert publico["fotos"] == urls


def test_fotos_rejeitam_url_invalida_e_duplicada(client, loja_a):
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    assert client.put(
        f"/v1/veiculos/{vid}/fotos", json={"urls": ["arquivo-local.jpg"]}, headers=h
    ).status_code == 422
    assert client.put(
        f"/v1/veiculos/{vid}/fotos",
        json={"urls": ["https://img.test/a.jpg", "https://img.test/a.jpg"]},
        headers=h,
    ).status_code == 422


def test_mutacoes_geram_auditoria_e_outbox(client, loja_a, operador_loja_a):
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    client.post(f"/v1/veiculos/{vid}/publicar", headers=operador_loja_a["headers"])
    client.post(f"/v1/veiculos/{vid}/vender", headers=h)

    auditoria = client.get("/v1/auditoria", headers=h).json()["eventos"]
    assert {item["acao"] for item in auditoria if item["recurso_id"] == vid} >= {
        "criado", "publicado", "vendido"
    }
    assert any(item["ator_papel"] == "operador" for item in auditoria)

    eventos = client.get("/v1/eventos", headers=h).json()["eventos"]
    tipos = {item["tipo"] for item in eventos if item["agregado_id"] == vid}
    assert {"vehicle.created", "vehicle.published", "vehicle.sold"} <= tipos
    assert client.get("/v1/auditoria", headers=operador_loja_a["headers"]).status_code == 403
