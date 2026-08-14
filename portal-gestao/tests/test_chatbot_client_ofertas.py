import httpx

from app.clients.chatbot import ChatbotClient


def _client(handler):
    class ClientComTransporte(ChatbotClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                transport=httpx.MockTransport(handler),
            ) as c:
                resposta = c.request(method, path, **kwargs)
            if resposta.status_code == 404 and erro_404 is not None:
                raise erro_404("recurso não encontrado")
            resposta.raise_for_status()
            return resposta.json()

    return ClientComTransporte("http://chatbot.test", "token")


def test_listar_ofertas_chama_a_rota():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": "of-1", "estado": "aberta"}])

    out = _client(handler).listar_ofertas()
    assert "/v1/ofertas" in capturado["url"]
    assert out == [{"id": "of-1", "estado": "aberta"}]


def test_listar_ofertas_repassa_estado():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        return httpx.Response(200, json=[])

    _client(handler).listar_ofertas(estado="esgotada")
    assert "estado=esgotada" in capturado["url"]


def test_assumir_oferta_posta_no_id():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["method"] = request.method
        return httpx.Response(200, json={"ganhou": True, "telefone_cliente": "5511"})

    out = _client(handler).assumir_oferta("of-1")
    assert "/v1/ofertas/of-1/assumir" in capturado["url"]
    assert capturado["method"] == "POST"
    assert out["ganhou"] is True
