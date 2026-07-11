def _novo():
    return {
        "tipo": "moto",
        "marca": "Honda",
        "modelo": "CG 160",
        "ano_modelo": 2023,
        "preco": 16000,
        "custo": 13000,
    }


def test_vitrine_mostra_so_publicado_e_disponivel(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]

    # ainda não publicado -> vitrine vazia
    assert client.get(f"/public/v1/lojas/{slug}/veiculos").json()["veiculos"] == []

    client.post(f"/v1/veiculos/{vid}/publicar", headers=h)
    pub = client.get(f"/public/v1/lojas/{slug}/veiculos").json()
    assert pub["loja"]["slug"] == slug
    assert len(pub["veiculos"]) == 1
    assert "custo" not in pub["veiculos"][0]  # nunca vaza custo


def test_detalhe_publico_sem_custo(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    client.post(f"/v1/veiculos/{vid}/publicar", headers=h)

    d = client.get(f"/public/v1/lojas/{slug}/veiculos/{vid}").json()
    assert d["modelo"] == "CG 160"
    assert "custo" not in d and "codigo_interno" not in d


def test_vendido_some_da_vitrine(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    client.post(f"/v1/veiculos/{vid}/publicar", headers=h)
    client.post(f"/v1/veiculos/{vid}/vender", headers=h)

    assert client.get(f"/public/v1/lojas/{slug}/veiculos").json()["veiculos"] == []
    assert client.get(f"/public/v1/lojas/{slug}/veiculos/{vid}").status_code == 404


def test_filtro_preco_publico(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    v1 = client.post("/v1/veiculos", json=_novo() | {"preco": 16000}, headers=h).json()["id"]
    v2 = client.post("/v1/veiculos", json=_novo() | {"preco": 45000, "modelo": "XRE 300"}, headers=h).json()["id"]
    client.post(f"/v1/veiculos/{v1}/publicar", headers=h)
    client.post(f"/v1/veiculos/{v2}/publicar", headers=h)

    ate_20k = client.get(f"/public/v1/lojas/{slug}/veiculos?preco_max=20000").json()["veiculos"]
    assert [v["modelo"] for v in ate_20k] == ["CG 160"]


def test_slug_inexistente_404(client):
    assert client.get("/public/v1/lojas/nao-existe/veiculos").status_code == 404
    assert client.get("/public/v1/lojas/nao-existe").status_code == 404
