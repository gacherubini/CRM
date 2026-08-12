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


# Testes de integração via rota HTTP
from conftest import csrf_da_resposta, login


def test_rota_estoque_editar_com_404_retorna_erro_no_template(client, estoque_fake):
    login(client)
    estoque_fake.atualizar_nao_encontrado = True
    pagina = client.get("/app/estoque/v1")
    resposta = client.post(
        "/app/estoque/v1",
        data={
            "csrf": csrf_da_resposta(pagina),
            "tipo": "carro",
            "marca": "Toyota",
            "modelo": "Corolla",
            "versao": "GLi",
            "ano_modelo": "2023",
            "cor": "Prata",
            "km": "12000",
            "preco": "129900.50",
            "custo": "110000",
            "codigo_interno": "T01",
            "foto_url": "",
            "placa": "ABC1D23",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 422
    assert "veículo não encontrado" in resposta.text


def test_rota_estoque_editar_com_409_retorna_erro_no_template(client, estoque_fake):
    login(client)
    estoque_fake.atualizar_conflito = True
    pagina = client.get("/app/estoque/v1")
    resposta = client.post(
        "/app/estoque/v1",
        data={
            "csrf": csrf_da_resposta(pagina),
            "tipo": "carro",
            "marca": "Toyota",
            "modelo": "Corolla",
            "versao": "GLi",
            "ano_modelo": "2023",
            "cor": "Prata",
            "km": "12000",
            "preco": "129900.50",
            "custo": "110000",
            "codigo_interno": "T01",
            "foto_url": "",
            "placa": "ABC1D23",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 422
    assert "veículo em estado incompatível" in resposta.text
