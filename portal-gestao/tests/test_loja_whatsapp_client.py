"""Client de escrita de canais WhatsApp usado pela Loja (Ajustes)."""
from app.clients.chatbot import ChatbotClient


def test_client_registrar_canal_manda_so_label():
    chamadas = []

    class _Fake(ChatbotClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            chamadas.append((method, path, kwargs.get("json")))
            return {"id": "c1", "e164_or_label": "linha 2"}

    cliente = _Fake("http://chatbot", "tok")
    canal = cliente.registrar_canal_whatsapp("linha 2")

    assert canal["id"] == "c1"
    assert chamadas == [("POST", "/v1/whatsapp/canais", {"e164_or_label": "linha 2"})]


def test_client_conectar_usa_endpoint_do_canal():
    chamadas = []

    class _Fake(ChatbotClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            chamadas.append((method, path))
            return {"id": "c1", "qr_payload": "QR", "estado": "pendente"}

    cliente = _Fake("http://chatbot", "tok")
    out = cliente.conectar_canal_whatsapp("c1")

    assert out["qr_payload"] == "QR"
    assert chamadas == [("POST", "/v1/whatsapp/canais/c1/connect")]
