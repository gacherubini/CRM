import httpx
import pytest

from app.clients.estoque import (
    ConflitoEstoque,
    EstoqueClient,
    EstoqueIndisponivel,
    VeiculoNaoEncontrado,
)


def _client(handler):
    class ClientComTransporte(EstoqueClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            transporte = httpx.MockTransport(handler)
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                transport=transporte,
            ) as c:
                resposta = c.request(method, path, **kwargs)
            if resposta.status_code == 404 and erro_404 is not None:
                raise erro_404("veículo não encontrado")
            if resposta.status_code == 409 and erro_409 is not None:
                raise erro_409("veículo em estado incompatível")
            if resposta.status_code >= 400:
                raise EstoqueIndisponivel("erro")
            return resposta.json()

    return ClientComTransporte("http://estoque.test", "token")


def test_404_no_patch_vira_veiculo_nao_encontrado():
    client = _client(lambda r: httpx.Response(404, json={"detail": "not found"}))
    with pytest.raises(VeiculoNaoEncontrado):
        client.atualizar("v1", {"preco": 25000})


def test_409_no_patch_vira_conflito():
    client = _client(lambda r: httpx.Response(409, json={"detail": "conflito"}))
    with pytest.raises(ConflitoEstoque):
        client.atualizar("v1", {"preco": 25000})


def test_500_continua_indisponivel():
    client = _client(lambda r: httpx.Response(500, json={}))
    with pytest.raises(EstoqueIndisponivel):
        client.atualizar("v1", {"preco": 25000})


def test_200_devolve_o_veiculo():
    client = _client(lambda r: httpx.Response(200, json={"id": "v1", "preco": 25000}))
    assert client.atualizar("v1", {"preco": 25000})["preco"] == 25000
