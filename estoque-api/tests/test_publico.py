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


def test_filtro_marca_paginacao_e_cache_condicional(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    honda = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    yamaha = client.post(
        "/v1/veiculos", json=_novo() | {"marca": "Yamaha", "modelo": "Fazer"}, headers=h
    ).json()["id"]
    client.post(f"/v1/veiculos/{honda}/publicar", headers=h)
    client.post(f"/v1/veiculos/{yamaha}/publicar", headers=h)

    resposta = client.get(f"/public/v1/lojas/{slug}/veiculos?marca=Honda&limit=1")
    assert resposta.status_code == 200
    assert [v["marca"] for v in resposta.json()["veiculos"]] == ["Honda"]
    assert resposta.json()["paginacao"] == {
        "limit": 1,
        "offset": 0,
        "quantidade": 1,
        "total": 1,
    }
    assert resposta.headers["etag"]
    assert resposta.headers["x-ratelimit-limit"]

    cache = client.get(
        f"/public/v1/lojas/{slug}/veiculos?marca=Honda&limit=1",
        headers={"If-None-Match": resposta.headers["etag"]},
    )
    assert cache.status_code == 304


def test_paginacao_publica_rejeita_limites_invalidos(client, loja_a):
    slug = loja_a["slug"]
    assert client.get(f"/public/v1/lojas/{slug}/veiculos?limit=0").status_code == 422
    assert client.get(f"/public/v1/lojas/{slug}/veiculos?limit=101").status_code == 422


def test_vitrine_prioriza_com_foto_e_expõe_total(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    sem_foto = client.post(
        "/v1/veiculos", json=_novo() | {"modelo": "SemFoto"}, headers=h
    ).json()["id"]
    com_foto = client.post(
        "/v1/veiculos", json=_novo() | {"modelo": "ComFoto"}, headers=h
    ).json()["id"]
    client.put(
        f"/v1/veiculos/{com_foto}/fotos",
        json={"urls": ["https://img.test/capa.jpg"]},
        headers=h,
    )
    client.post(f"/v1/veiculos/{sem_foto}/publicar", headers=h)
    client.post(f"/v1/veiculos/{com_foto}/publicar", headers=h)

    # Empate em ordem_vitrine: desempate tem_foto DESC.
    assert (
        client.put(
            "/v1/veiculos/ordem-vitrine",
            json={
                "itens": [
                    {"id": sem_foto, "ordem_vitrine": 0},
                    {"id": com_foto, "ordem_vitrine": 0},
                ]
            },
            headers=h,
        ).status_code
        == 200
    )

    pagina = client.get(f"/public/v1/lojas/{slug}/veiculos?limit=10").json()
    assert pagina["paginacao"]["total"] == 2
    assert pagina["paginacao"]["quantidade"] == 2
    assert [v["modelo"] for v in pagina["veiculos"]] == ["ComFoto", "SemFoto"]


def test_vitrine_respeita_ordem_manual(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    a = client.post(
        "/v1/veiculos", json=_novo() | {"modelo": "Primeira"}, headers=h
    ).json()["id"]
    b = client.post(
        "/v1/veiculos", json=_novo() | {"modelo": "Segunda"}, headers=h
    ).json()["id"]
    c = client.post(
        "/v1/veiculos", json=_novo() | {"modelo": "Terceira"}, headers=h
    ).json()["id"]
    for vid in (a, b, c):
        client.post(f"/v1/veiculos/{vid}/publicar", headers=h)

    r = client.put(
        "/v1/veiculos/ordem-vitrine",
        json={
            "itens": [
                {"id": c, "ordem_vitrine": 0},
                {"id": a, "ordem_vitrine": 1},
                {"id": b, "ordem_vitrine": 2},
            ]
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["atualizados"] == 3

    pagina = client.get(f"/public/v1/lojas/{slug}/veiculos?limit=10").json()
    assert [v["modelo"] for v in pagina["veiculos"]] == [
        "Terceira",
        "Primeira",
        "Segunda",
    ]

    # Idempotência de leitura: segunda reordenação troca topo.
    client.put(
        "/v1/veiculos/ordem-vitrine",
        json={
            "itens": [
                {"id": b, "ordem_vitrine": 0},
                {"id": c, "ordem_vitrine": 1},
                {"id": a, "ordem_vitrine": 2},
            ]
        },
        headers=h,
    )
    pagina2 = client.get(f"/public/v1/lojas/{slug}/veiculos?limit=10").json()
    assert [v["modelo"] for v in pagina2["veiculos"]] == [
        "Segunda",
        "Terceira",
        "Primeira",
    ]


def test_patch_whatsapp_loja_normaliza_e_reflete_no_publico(client, loja_a):
    h, slug = loja_a["headers"], loja_a["slug"]
    atual = client.get("/v1/loja", headers=h).json()
    assert atual["slug"] == slug
    assert atual["whatsapp"] == "5511999999999"
    assert "catalogo_url" in atual

    patch = client.patch("/v1/loja", json={"whatsapp": "(21) 98888-7777"}, headers=h)
    assert patch.status_code == 200
    assert patch.json()["whatsapp"] == "5521988887777"

    pub = client.get(f"/public/v1/lojas/{slug}").json()
    assert pub["whatsapp"] == "5521988887777"
    # Invertido em 25/08 junto com o payload: o chatbot precisa do link por slug,
    # e ele e a URL que o bot ja entrega a qualquer cliente que peca as motos.
    # Ver o docstring de `_loja_publica`.
    assert pub["catalogo_url"] is None

    limpa = client.patch("/v1/loja", json={"whatsapp": ""}, headers=h)
    assert limpa.status_code == 200
    assert limpa.json()["whatsapp"] is None


def test_patch_catalogo_url_loja(client, loja_a):
    h = loja_a["headers"]
    url = "https://app2037.fly.dev/catalogo/l/vitor-motos"
    patch = client.patch("/v1/loja", json={"catalogo_url": url}, headers=h)
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["catalogo_url"] == url
    assert body["whatsapp"] == "5511999999999"
    assert client.get("/v1/loja", headers=h).json()["catalogo_url"] == url

    ruim = client.patch("/v1/loja", json={"catalogo_url": "ftp://x"}, headers=h)
    assert ruim.status_code == 422

    limpa = client.patch("/v1/loja", json={"catalogo_url": ""}, headers=h)
    assert limpa.status_code == 200
    assert limpa.json()["catalogo_url"] is None


def test_publico_por_slug_devolve_o_catalogo_de_cada_loja(client, loja_a, loja_b):
    """O motivo de o campo existir aqui: o chatbot precisa do link POR SLUG.

    Com `/v1/loja` (escopada pelo token) e um token global, todas as lojas
    recebiam o catálogo de uma só — o cliente da loja B ganhava o link da
    vitrine da loja A, sem erro e sem log.
    """
    client.patch(
        "/v1/loja",
        json={"catalogo_url": "https://exemplo.com/a"},
        headers=loja_a["headers"],
    )
    client.patch(
        "/v1/loja",
        json={"catalogo_url": "https://exemplo.com/b"},
        headers=loja_b["headers"],
    )

    pub_a = client.get(f"/public/v1/lojas/{loja_a['slug']}").json()
    pub_b = client.get(f"/public/v1/lojas/{loja_b['slug']}").json()
    assert pub_a["catalogo_url"] == "https://exemplo.com/a"
    assert pub_b["catalogo_url"] == "https://exemplo.com/b"
