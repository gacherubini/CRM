import httpx
import pytest

from app.contracts import Store, Vehicle, VehiclePage
from app.provider import HttpInventoryProvider, InventoryNotFound, InventoryUnavailable


def test_fixture_representa_contrato_publico_atual(contract_data):
    assert Store.model_validate(contract_data["loja"]).slug == "moto-center"
    assert Vehicle.model_validate(contract_data["veiculo"]).modelo == "CG 160"
    page = VehiclePage.model_validate(
        {
            "loja": contract_data["loja"],
            "veiculos": [contract_data["veiculo"]],
            "paginacao": contract_data["paginacao"],
        }
    )
    assert page.paginacao.quantidade == 1


def test_provider_http_consome_rotas_e_parametros_suportados(contract_data):
    requests = []

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/veiculos/vehicle-1"):
            return httpx.Response(200, json=contract_data["veiculo"])
        if path.endswith("/veiculos"):
            payload = {
                "loja": contract_data["loja"],
                "veiculos": [contract_data["veiculo"]],
                "paginacao": {"limit": 10, "offset": 20, "quantidade": 1},
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json=contract_data["loja"])

    provider = HttpInventoryProvider(
        "https://inventory.example",
        token="server-token",
        transport=httpx.MockTransport(handler),
    )
    assert provider.get_store("moto-center").nome == "Moto Center"
    page = provider.list_vehicles(
        "moto-center", tipo="moto", marca="Honda", preco_min=10000, limit=10, offset=20
    )
    assert page.veiculos[0].id == "vehicle-1"
    assert provider.get_vehicle("moto-center", "vehicle-1").modelo == "CG 160"

    list_request = requests[1]
    assert dict(list_request.url.params) == {
        "tipo": "moto",
        "marca": "Honda",
        "preco_min": "10000",
        "limit": "10",
        "offset": "20",
    }
    assert list_request.headers["authorization"] == "Bearer server-token"


@pytest.mark.parametrize(
    ("status", "error"), [(404, InventoryNotFound), (429, InventoryUnavailable), (500, InventoryUnavailable)]
)
def test_provider_traduz_erros_http(status, error):
    provider = HttpInventoryProvider(
        "https://inventory.example",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={})),
    )
    with pytest.raises(error):
        provider.get_store("inexistente")


def test_provider_rejeita_resposta_fora_do_contrato():
    provider = HttpInventoryProvider(
        "https://inventory.example",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"slug": "x"})),
    )
    with pytest.raises(InventoryUnavailable):
        provider.get_store("x")
