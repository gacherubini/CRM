from app.inventory import HttpInventoryProvider, get_inventory_provider
from app.main import app


class _FakeProvider:
    def __init__(self, veiculos):
        self._veiculos = veiculos

    def buscar(self, slug, termo=None):
        return self._veiculos


def test_busca_estoque_com_resultado(client, loja_a):
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeProvider(
        [{"marca": "Chevrolet", "modelo": "Onix", "preco": 45000.0}]
    )
    try:
        r = client.get("/v1/estoque/buscar?termo=onix", headers=loja_a["headers"])
        body = r.json()
        assert body["fonte"] == "estoque"
        assert body["veiculos"][0]["modelo"] == "Onix"
    finally:
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_busca_estoque_vazio_gera_fallback(client, loja_a):
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeProvider([])
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
