from app.inventory import HttpInventoryProvider, get_inventory_provider
from app.main import app


class _FakeProvider:
    def __init__(self, veiculos=None, por_placa=None):
        self._veiculos = veiculos or []
        self._por_placa = por_placa

    def buscar(self, slug, termo=None):
        return self._veiculos

    def obter_por_placa(self, placa):
        return self._por_placa


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
        assert "atendente" in body["mensagem"]
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
        assert "atendente" in body["mensagem"]
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
