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


def test_fotos_detalhadas_validam_tipo_tamanho_ordem_e_capa(client, loja_a):
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    fotos = [
        {
            "url": "https://cdn.example/traseira.webp",
            "content_type": "image/webp",
            "tamanho_bytes": 220_000,
            "ordem": 2,
            "capa": False,
        },
        {
            "url": "https://cdn.example/frente.jpg",
            "content_type": "image/jpeg",
            "tamanho_bytes": 350_000,
            "ordem": 1,
            "capa": True,
        },
    ]

    resposta = client.put(
        f"/v1/veiculos/{vid}/fotos", json={"fotos": fotos}, headers=h
    )
    assert resposta.status_code == 200, resposta.text
    body = resposta.json()
    assert [item["ordem"] for item in body["midias"]] == [1, 2]
    assert body["midia_principal"]["url"].endswith("/frente.jpg")
    assert body["foto_url"] == body["midia_principal"]["url"]
    assert body["midias"][0]["tamanho_bytes"] == 350_000
    client.post(f"/v1/veiculos/{vid}/publicar", headers=h)
    publico = client.get(
        f"/public/v1/lojas/{loja_a['slug']}/veiculos/{vid}"
    ).json()
    assert publico["midia_principal"]["content_type"] == "image/jpeg"
    assert publico["midia_principal"]["capa"] is True
    assert "custo" not in publico

    duas_capas = [dict(item, capa=True) for item in fotos]
    assert client.put(
        f"/v1/veiculos/{vid}/fotos", json={"fotos": duas_capas}, headers=h
    ).status_code == 422
    assert client.put(
        f"/v1/veiculos/{vid}/fotos",
        json={
            "fotos": [
                {
                    "url": "https://cdn.example/video.mp4",
                    "content_type": "video/mp4",
                    "tamanho_bytes": 10,
                    "capa": True,
                }
            ]
        },
        headers=h,
    ).status_code == 422


def test_fotos_bloqueiam_base64_host_interno_query_e_tamanho(client, loja_a, monkeypatch):
    from app import config

    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]

    def enviar(url, tamanho=100):
        return client.put(
            f"/v1/veiculos/{vid}/fotos",
            json={
                "fotos": [
                    {
                        "url": url,
                        "content_type": "image/jpeg",
                        "tamanho_bytes": tamanho,
                        "capa": True,
                    }
                ]
            },
            headers=h,
        )

    assert enviar("data:image/jpeg;base64,AAAA").status_code == 422
    assert enviar("https://127.0.0.1/foto.jpg").status_code == 422
    assert enviar("https://cdn.example/foto.jpg?token=secreto").status_code == 422
    assert enviar("https://cdn.example/foto.jpg", config.MEDIA_MAX_BYTES + 1).status_code == 422


def test_storage_key_vira_url_publica_sem_expor_path_interno(client, loja_a, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MEDIA_PUBLIC_BASE_URL", "https://media.example/veiculos")
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    resposta = client.put(
        f"/v1/veiculos/{vid}/fotos",
        json={
            "fotos": [
                {
                    "storage_key": "loja-a/cg-160/frente.jpg",
                    "content_type": "image/jpeg",
                    "tamanho_bytes": 12345,
                    "capa": True,
                }
            ]
        },
        headers=h,
    )
    assert resposta.status_code == 200, resposta.text
    midia = resposta.json()["midia_principal"]
    assert midia["url"] == "https://media.example/veiculos/loja-a/cg-160/frente.jpg"
    assert "storage_key" not in midia
    assert "base64" not in resposta.text


def test_allowlist_de_host_restringe_cdn(client, loja_a, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ("media.autorizada.example",))
    h = loja_a["headers"]
    vid = client.post("/v1/veiculos", json=_novo(), headers=h).json()["id"]
    negada = client.put(
        f"/v1/veiculos/{vid}/fotos",
        json={"urls": ["https://outro-cdn.example/frente.jpg"]},
        headers=h,
    )
    assert negada.status_code == 422
    aceita = client.put(
        f"/v1/veiculos/{vid}/fotos",
        json={"urls": ["https://media.autorizada.example/frente.jpg"]},
        headers=h,
    )
    assert aceita.status_code == 200


def test_fotos_respeitam_tenancy(client, loja_a, loja_b):
    vid = client.post(
        "/v1/veiculos", json=_novo(), headers=loja_a["headers"]
    ).json()["id"]
    resposta = client.put(
        f"/v1/veiculos/{vid}/fotos",
        json={"urls": ["https://cdn.example/frente.jpg"]},
        headers=loja_b["headers"],
    )
    assert resposta.status_code == 404


def test_upload_whatsapp_anexa_publica_e_fica_disponivel_no_catalogo(
    client, loja_a, tmp_path, monkeypatch
):
    from app import config

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    h, slug = loja_a["headers"], loja_a["slug"]
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="ABC1D23"), headers=h
    ).json()["id"]
    foto = b"\xff\xd8\xff" + b"imagem-jpeg-segura"
    headers = h | {
        "Content-Type": "image/jpeg",
        "Idempotency-Key": "wa-msg-foto-1",
    }

    primeira = client.post(
        f"/v1/veiculos/{vid}/fotos/upload?publicar=true",
        content=foto,
        headers=headers,
    )
    segunda = client.post(
        f"/v1/veiculos/{vid}/fotos/upload?publicar=true",
        content=foto,
        headers=headers,
    )

    assert primeira.status_code == 201, primeira.text
    assert segunda.status_code == 201, segunda.text
    body = segunda.json()
    assert body["publicado"] is True
    assert body["tem_foto"] is True
    assert len(body["midias"]) == 1
    url = body["midia_principal"]["url"]
    assert url.startswith("https://estoque.example/public/v1/media/")

    caminho_publico = url.removeprefix("https://estoque.example")
    arquivo = client.get(caminho_publico)
    assert arquivo.status_code == 200
    assert arquivo.content == foto
    assert arquivo.headers["content-type"].startswith("image/jpeg")
    assert arquivo.headers["x-content-type-options"] == "nosniff"

    catalogo = client.get(f"/public/v1/lojas/{slug}/veiculos").json()
    veiculo = next(item for item in catalogo["veiculos"] if item["id"] == vid)
    assert veiculo["fotos"] == [url]
    assert veiculo["midia_principal"]["url"] == url


def test_upload_whatsapp_bloqueia_loja_errada_e_conteudo_falso(
    client, loja_a, loja_b, tmp_path, monkeypatch
):
    from app import config

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="DEF2G34"), headers=loja_a["headers"]
    ).json()["id"]

    outra_loja = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=b"\xff\xd8\xfffoto",
        headers=loja_b["headers"] | {"Content-Type": "image/jpeg"},
    )
    falsa = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=b"nao-e-jpeg",
        headers=loja_a["headers"] | {"Content-Type": "image/jpeg"},
    )

    assert outra_loja.status_code == 404
    assert falsa.status_code == 415
    assert not list(tmp_path.rglob("*.jpg"))


def test_upload_whatsapp_anexa_sem_apagar_galeria_e_restringe_leitor(
    client, loja_a, leitor_loja_a, tmp_path, monkeypatch
):
    from app import config

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    h = loja_a["headers"]
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="GHI3J45"), headers=h
    ).json()["id"]
    primeira_url = "https://cdn.example/frente.jpg"
    client.put(f"/v1/veiculos/{vid}/fotos", json={"urls": [primeira_url]}, headers=h)

    foto = b"\x89PNG\r\n\x1a\n" + b"foto-png"
    leitor = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=foto,
        headers=leitor_loja_a["headers"] | {"Content-Type": "image/png"},
    )
    resposta = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=foto,
        headers=h
        | {
            "Content-Type": "image/png",
            "Idempotency-Key": "wa-msg-foto-2",
        },
    )

    assert leitor.status_code == 403
    assert resposta.status_code == 201
    assert resposta.json()["fotos"][0] == primeira_url
    assert len(resposta.json()["fotos"]) == 2
    assert resposta.json()["midia_principal"]["url"] == primeira_url


def test_upload_whatsapp_rejeita_tamanho_antes_de_persistir(
    client, loja_a, tmp_path, monkeypatch
):
    from app import config

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(config, "MEDIA_MAX_BYTES", 8)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="JKL4M56"), headers=loja_a["headers"]
    ).json()["id"]
    resposta = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=b"\xff\xd8\xff123456789",
        headers=loja_a["headers"] | {"Content-Type": "image/jpeg"},
    )

    assert resposta.status_code == 413
    assert not list(tmp_path.rglob("*.jpg"))


def test_upload_whatsapp_nao_sobrescreve_mesma_chave_com_outro_conteudo(
    client, loja_a, tmp_path, monkeypatch
):
    from app import config

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="MNO5P67"), headers=loja_a["headers"]
    ).json()["id"]
    headers = loja_a["headers"] | {
        "Content-Type": "image/jpeg",
        "Idempotency-Key": "wa-msg-chave-unica",
    }

    primeira = client.post(
        f"/v1/veiculos/{vid}/fotos/upload", content=b"\xff\xd8\xffprimeira", headers=headers
    )
    conflito = client.post(
        f"/v1/veiculos/{vid}/fotos/upload", content=b"\xff\xd8\xffdiferente", headers=headers
    )

    assert primeira.status_code == 201
    assert conflito.status_code == 409
    url = primeira.json()["midia_principal"]["url"]
    assert client.get(url.removeprefix("https://estoque.example")).content == b"\xff\xd8\xffprimeira"


def test_substituir_galeria_remove_arquivo_local_que_ficou_orfao(
    client, loja_a, tmp_path, monkeypatch
):
    from app import config

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    monkeypatch.setattr(config, "MEDIA_ORPHAN_GRACE_SECONDS", 0)
    h = loja_a["headers"]
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="ORF1A23"), headers=h
    ).json()["id"]
    upload = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=b"\xff\xd8\xffarquivo-local",
        headers=h
        | {
            "Content-Type": "image/jpeg",
            "Idempotency-Key": "foto-que-sera-removida",
        },
    )
    url = upload.json()["midia_principal"]["url"]
    caminho_publico = url.removeprefix("https://estoque.example")
    assert client.get(caminho_publico).status_code == 200

    limpa = client.put(
        f"/v1/veiculos/{vid}/fotos", json={"urls": []}, headers=h
    )

    assert limpa.status_code == 200
    assert limpa.json()["fotos"] == []
    assert client.get(caminho_publico).status_code == 404
    assert not list(tmp_path.rglob("*.jpg"))


def test_varredura_orfas_e_dry_run_por_padrao(
    client, loja_a, db, tmp_path, monkeypatch
):
    from app import config, media, servico

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ALLOWED_HOSTS", ())
    monkeypatch.setattr(config, "MEDIA_ORPHAN_GRACE_SECONDS", 0)
    h = loja_a["headers"]
    vid = client.post(
        "/v1/veiculos", json=_novo(placa="ORF2A34"), headers=h
    ).json()["id"]
    referenciada = client.post(
        f"/v1/veiculos/{vid}/fotos/upload",
        content=b"\xff\xd8\xffreferenciada",
        headers=h
        | {
            "Content-Type": "image/jpeg",
            "Idempotency-Key": "foto-referenciada",
        },
    ).json()["midia_principal"]["url"]
    chave_orfa = f"{loja_a['loja_id']}/{vid}/{'a' * 32}.jpg"
    caminho_orfao, _ = media.salvar(chave_orfa, b"\xff\xd8\xfforfa")

    simulacao = servico.limpar_midias_orfas(db)
    assert simulacao == {
        "arquivos": 2,
        "referenciados": 1,
        "orfaos": 1,
        "aguardando_carencia": 0,
        "removidos": 0,
        "modo": "previa",
    }
    assert caminho_orfao.exists()

    aplicada = servico.limpar_midias_orfas(db, aplicar=True)
    assert aplicada["removidos"] == 1
    assert not caminho_orfao.exists()
    chave_referenciada = media.storage_key_da_url(referenciada)
    assert chave_referenciada is not None
    assert media.caminho_seguro(chave_referenciada).exists()


def test_varredura_nao_remove_upload_recente_durante_carencia(
    tmp_path, monkeypatch
):
    from app import config, media

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "MEDIA_PUBLIC_BASE_URL",
        "https://estoque.example/public/v1/media",
    )
    monkeypatch.setattr(config, "MEDIA_ORPHAN_GRACE_SECONDS", 3600)
    chave = f"loja-segura/veiculo-seguro/{'b' * 32}.jpg"
    caminho, _ = media.salvar(chave, b"\xff\xd8\xffrecente")

    resultado = media.limpar_orfas(set(), aplicar=True)

    assert resultado["orfaos"] == 1
    assert resultado["aguardando_carencia"] == 1
    assert resultado["removidos"] == 0
    assert caminho.exists()


def test_varredura_falha_fechada_sem_base_publica(tmp_path, monkeypatch):
    from app import config, media

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(config, "MEDIA_PUBLIC_BASE_URL", "")
    chave = f"loja-segura/veiculo-seguro/{'c' * 32}.jpg"
    caminho, _ = media.salvar(chave, b"\xff\xd8\xffpreservada")

    resultado = media.limpar_orfas(set(), aplicar=True)

    assert resultado["modo"] == "desativado"
    assert resultado["arquivos"] == 1
    assert resultado["orfaos"] == 0
    assert resultado["removidos"] == 0
    assert caminho.exists()


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
