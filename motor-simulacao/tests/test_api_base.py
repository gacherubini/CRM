import httpx
import pytest

from app.motor.api_base import ApiBankDriver
from app.motor.drivers import ErroTransitorio, IntervencaoNecessaria, RejeicaoNegocio


class _Driver(ApiBankDriver):
    provedor = "teste"

    def simular(self, sol, ctx=None):
        return self._request_json("GET", "/teste")


def _driver(status: int, body=None):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json=body or {"ok": True})
    )
    return _Driver(base_url="https://api.test", transport=transport)


def test_api_base_devolve_json():
    assert _driver(200).simular(None) == {"ok": True}


@pytest.mark.parametrize("status", [500, 503, 429])
def test_api_base_mapeia_falha_transitoria(status):
    with pytest.raises(ErroTransitorio):
        _driver(status).simular(None)


def test_api_base_mapeia_credencial_invalida():
    with pytest.raises(IntervencaoNecessaria):
        _driver(401).simular(None)


def test_api_base_mapeia_rejeicao_de_request():
    with pytest.raises(RejeicaoNegocio):
        _driver(422).simular(None)
