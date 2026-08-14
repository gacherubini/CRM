import httpx
import pytest

from app.clients.estoque import ConflitoEstoque, EstoqueClient, VeiculoNaoEncontrado


def _client(handler):
    class ClientComTransporte(EstoqueClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                transport=httpx.MockTransport(handler),
            ) as c:
                resposta = c.request(method, path, **kwargs)
            if resposta.status_code == 404 and erro_404 is not None:
                raise erro_404("veículo não encontrado")
            if resposta.status_code == 409 and erro_409 is not None:
                raise erro_409("veículo em estado incompatível")
            resposta.raise_for_status()
            return resposta.json()

    return ClientComTransporte("http://estoque.test", "token")


def test_adicionar_foto_faz_post_com_bytes_e_headers():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["content"] = request.content
        capturado["content_type"] = request.headers.get("content-type")
        capturado["idem"] = request.headers.get("idempotency-key")
        return httpx.Response(201, json={"id": "v1", "publicado": True})

    client = _client(handler)
    out = client.adicionar_foto(
        "v1", b"\xff\xd8jpegbytes", "image/jpeg", idempotency_key="portal-foto:v1:abc"
    )
    assert out["id"] == "v1"
    assert "/v1/veiculos/v1/fotos/upload" in capturado["url"]
    assert "publicar=true" in capturado["url"]
    assert capturado["content"] == b"\xff\xd8jpegbytes"
    assert capturado["content_type"] == "image/jpeg"
    assert capturado["idem"] == "portal-foto:v1:abc"


def test_adicionar_foto_404_vira_veiculo_nao_encontrado():
    client = _client(lambda r: httpx.Response(404, json={"detail": "x"}))
    with pytest.raises(VeiculoNaoEncontrado):
        client.adicionar_foto("v1", b"x", "image/jpeg", idempotency_key="k")


def test_adicionar_foto_409_vira_conflito():
    client = _client(lambda r: httpx.Response(409, json={"detail": "x"}))
    with pytest.raises(ConflitoEstoque):
        client.adicionar_foto("v1", b"x", "image/jpeg", idempotency_key="k")
