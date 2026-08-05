from app.inventory import HttpInventoryProvider, get_inventory_provider
from app.main import app


class _FakeProvider:
    def __init__(self, veiculos=None, por_placa=None, midia=None):
        self._veiculos = veiculos or []
        self._por_placa = por_placa
        self._midia = midia
        self.midias_consultadas = []

    def buscar(self, slug, termo=None):
        return self._veiculos

    def obter_por_placa(self, placa):
        return self._por_placa

    def obter_midia_principal(self, slug, veiculo_id):
        self.midias_consultadas.append((slug, veiculo_id))
        return self._midia


def test_busca_estoque_com_resultado(client, loja_a):
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeProvider(
        veiculos=[{"marca": "Chevrolet", "modelo": "Onix", "preco": 45000.0}]
    )
    try:
        r = client.get("/v1/estoque/buscar?termo=onix", headers=loja_a["headers"])
        body = r.json()
        assert body["fonte"] == "estoque"
        assert body["veiculos"][0]["modelo"] == "Onix"
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_busca_estoque_vazio_gera_fallback(client, loja_a):
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeProvider(veiculos=[])
    try:
        r = client.get("/v1/estoque/buscar", headers=loja_a["headers"])
        body = r.json()
        assert body["fonte"] == "fallback"
        assert body["veiculos"] == []
        assert "atendente" not in body["mensagem"].lower()
        assert "vendedor" not in body["mensagem"].lower()
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_http_provider_filtra_por_termo(monkeypatch):
    from app import inventory

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "veiculos": [
                    {"marca": "Chevrolet", "modelo": "Onix"},
                    {"marca": "Honda", "modelo": "CG 160"},
                ]
            }

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    prov = HttpInventoryProvider(base_url="http://estoque")
    assert [v["modelo"] for v in prov.buscar("slug", "onix")] == ["Onix"]


def test_veiculo_casa_termo_mt03_com_ano_e_marca_aproximada():
    """Bug real: bot buscou 'mt-03 2023' e o filtro antigo (marca+modelo substring) zerou."""
    from app.inventory import veiculo_casa_termo

    v = {
        "marca": "yahamaha",  # typo no cadastro
        "modelo": "MT-03",
        "versao": "MT-03 321/ABS",
        "ano_modelo": 2023,
    }
    assert veiculo_casa_termo(v, "mt-03")
    assert veiculo_casa_termo(v, "MT-03 2023")
    assert veiculo_casa_termo(v, "mt 03")
    assert veiculo_casa_termo(v, "yamaha mt-03")
    assert veiculo_casa_termo(v, "mt03")
    assert not veiculo_casa_termo(v, "biz 125")


def test_http_provider_filtra_mt03_2023(monkeypatch):
    from app import inventory

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "veiculos": [
                    {
                        "marca": "yahamaha",
                        "modelo": "MT-03",
                        "versao": "MT-03 321/ABS",
                        "ano_modelo": 2023,
                        "preco": 31900,
                    },
                    {"marca": "Honda", "modelo": "CG 160", "ano_modelo": 2018},
                ]
            }

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    prov = HttpInventoryProvider(base_url="http://estoque")
    achados = prov.buscar("slug", "mt-03 2023")
    assert len(achados) == 1
    assert achados[0]["modelo"] == "MT-03"


def test_http_provider_sem_base_url_retorna_vazio():
    assert HttpInventoryProvider(base_url="").buscar("slug", "onix") == []


def test_por_placa_endpoint_com_resultado(client, loja_a):
    veiculo = {
        "id": "v1",
        "placa": "ABC1D23",
        "marca": "Honda",
        "modelo": "CG 160",
        "preco": 15000.0,
        "tipo": "moto",
    }
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeProvider(por_placa=veiculo)
    try:
        r = client.get("/v1/estoque/por-placa/ABC1D23", headers=loja_a["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["fonte"] == "estoque"
        assert body["veiculo"]["placa"] == "ABC1D23"
        assert body["veiculo"]["preco"] == 15000.0
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_por_placa_endpoint_fallback(client, loja_a):
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeProvider(por_placa=None)
    try:
        r = client.get("/v1/estoque/por-placa/ZZZ9Z99", headers=loja_a["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["fonte"] == "fallback"
        assert body["veiculo"] is None
        assert "atendente" not in body["mensagem"].lower()
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_por_placa_exige_auth(client):
    r = client.get("/v1/estoque/por-placa/ABC1D23")
    assert r.status_code == 401


def test_http_provider_obter_por_placa(monkeypatch):
    from app import inventory

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "v1", "placa": "ABC1D23", "preco": 12000.0}

    def _get(url, headers=None, timeout=None):
        assert "por-placa/ABC1D23" in url
        assert headers["Authorization"] == "Bearer tok-est"
        return _FakeResp()

    monkeypatch.setattr(inventory.httpx, "get", _get)
    prov = HttpInventoryProvider(
        base_url="", api_url="http://estoque-api", api_token="tok-est"
    )
    assert prov.obter_por_placa("ABC1D23")["preco"] == 12000.0


def test_http_provider_por_placa_404_retorna_none(monkeypatch):
    from app import inventory

    class _FakeResp:
        status_code = 404

        def raise_for_status(self):
            raise RuntimeError("não deve chamar")

        def json(self):
            return {"detail": "not found"}

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    prov = HttpInventoryProvider(api_url="http://estoque-api", api_token="tok")
    assert prov.obter_por_placa("ZZZ9Z99") is None


def test_http_provider_por_placa_sem_config_retorna_none():
    assert HttpInventoryProvider(api_url="", api_token="tok").obter_por_placa("ABC1D23") is None
    assert HttpInventoryProvider(api_url="http://e", api_token="").obter_por_placa("ABC1D23") is None


def test_projecao_chatbot_expoe_midias_mas_remove_campos_internos(monkeypatch):
    from app import inventory

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "v1",
                "marca": "Honda",
                "modelo": "CG",
                "preco": 16000,
                "custo": 12000,
                "codigo_interno": "SEGREDO",
                "loja_id": "interno",
                "midias": [
                    {
                        "url": "https://cdn.example/cg.jpg",
                        "content_type": "image/jpeg",
                        "tamanho_bytes": 1234,
                        "ordem": 0,
                        "capa": True,
                    }
                ],
            }

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    veiculo = HttpInventoryProvider(api_url="http://estoque", api_token="tok").obter_por_placa(
        "ABC1D23"
    )
    assert veiculo["tem_foto"] is True
    assert veiculo["midia_principal"]["url"] == "https://cdn.example/cg.jpg"
    assert "custo" not in veiculo
    assert "codigo_interno" not in veiculo
    assert "loja_id" not in veiculo


def test_projecao_descarta_url_interna_ou_base64(monkeypatch):
    from app import inventory

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "veiculos": [
                    {
                        "id": "v1",
                        "foto_url": "http://estoque-api:8000/uploads/a.jpg",
                        "midias": [
                            {
                                "url": "data:image/jpeg;base64,AAAA",
                                "content_type": "image/jpeg",
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    veiculo = HttpInventoryProvider(base_url="http://estoque").buscar("loja")[0]
    assert veiculo["tem_foto"] is False
    assert veiculo["midias"] == []


def test_projecao_nao_disfarca_midia_legada_nao_imagem_como_jpeg(monkeypatch):
    from app import inventory

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "veiculos": [
                    {
                        "id": "v-video",
                        "foto_url": "https://cdn.example/apresentacao.mp4",
                    }
                ]
            }

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    veiculo = HttpInventoryProvider(base_url="http://estoque").buscar("loja")[0]
    assert veiculo["tem_foto"] is False
    assert veiculo["midia_principal"] is None


def test_projecao_respeita_allowlist_do_cdn(monkeypatch):
    from app import config, inventory

    monkeypatch.setattr(config, "ESTOQUE_MEDIA_ALLOWED_HOSTS", ("cdn.correto.example",))

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "veiculos": [
                    {
                        "id": "v1",
                        "midias": [
                            {
                                "url": "https://cdn.errado.example/foto.jpg",
                                "content_type": "image/jpeg",
                                "tamanho_bytes": 100,
                                "capa": True,
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setattr(inventory.httpx, "get", lambda *a, **k: _FakeResp())
    veiculo = HttpInventoryProvider(base_url="http://estoque").buscar("loja")[0]
    assert veiculo["tem_foto"] is False


def test_endpoint_midia_principal_resolve_por_loja_e_id(client, loja_a):
    fake = _FakeProvider(
        midia={
            "url": "https://cdn.example/cg.jpg",
            "content_type": "image/jpeg",
            "tamanho_bytes": 4567,
            "ordem": 0,
            "capa": True,
        }
    )
    app.dependency_overrides[get_inventory_provider] = lambda: fake
    try:
        resposta = client.get(
            "/v1/estoque/veiculos/veh-1/midia-principal", headers=loja_a["headers"]
        )
        assert resposta.status_code == 200
        assert resposta.json()["midia"] == {
            "tipo": "image",
            "url": "https://cdn.example/cg.jpg",
            "content_type": "image/jpeg",
            "tamanho_bytes": 4567,
        }
        assert fake.midias_consultadas == [(loja_a["slug"], "veh-1")]
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_endpoint_midia_principal_sem_foto_preserva_compatibilidade(client, loja_a):
    fake = _FakeProvider(midia=None)
    app.dependency_overrides[get_inventory_provider] = lambda: fake
    try:
        resposta = client.get(
            "/v1/estoque/veiculos/sem-foto/midia-principal", headers=loja_a["headers"]
        )
        assert resposta.status_code == 200
        assert resposta.json() == {
            "veiculo_id": "sem-foto",
            "midia": None,
            "tem_foto": False,
        }
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_http_provider_resolve_midia_em_detalhe_publico_tenant_scoped(monkeypatch):
    from app import inventory

    capturado = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "veh-1",
                "midias": [
                    {
                        "url": "https://cdn.example/veh-1.webp",
                        "content_type": "image/webp",
                        "tamanho_bytes": 999,
                        "ordem": 0,
                        "capa": True,
                    }
                ],
            }

    def _get(url, timeout=None):
        capturado["url"] = url
        return _FakeResp()

    monkeypatch.setattr(inventory.httpx, "get", _get)
    provider = HttpInventoryProvider(base_url="http://estoque")
    midia = provider.obter_midia_principal("loja-a", "veh-1")
    assert capturado["url"].endswith("/public/v1/lojas/loja-a/veiculos/veh-1")
    assert midia["url"] == "https://cdn.example/veh-1.webp"
    assert midia["content_type"] == "image/webp"


def test_config_catalogo_bot_configurado(client, loja_a, monkeypatch):
    class _Write:
        def disponivel(self):
            return True

        def obter_loja(self):
            return {
                "slug": "x",
                "catalogo_url": "https://exemplo.com/catalogo/l/loja",
            }

    from app.main import app
    from app.inventory import get_inventory_write_client

    app.dependency_overrides[get_inventory_write_client] = lambda: _Write()
    try:
        r = client.get("/v1/config/catalogo-bot", headers=loja_a["headers"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["configurado"] is True
        assert body["catalogo_url"].startswith("https://")
        assert "https://exemplo.com/catalogo/l/loja" in body["mensagem"]
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_config_catalogo_bot_sem_url(client, loja_a, monkeypatch):
    class _Write:
        def disponivel(self):
            return True

        def obter_loja(self):
            return {"slug": "x", "catalogo_url": None}

    from app.main import app
    from app.inventory import get_inventory_write_client

    app.dependency_overrides[get_inventory_write_client] = lambda: _Write()
    try:
        r = client.get("/v1/config/catalogo-bot", headers=loja_a["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["configurado"] is False
        assert body["catalogo_url"] is None
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)
