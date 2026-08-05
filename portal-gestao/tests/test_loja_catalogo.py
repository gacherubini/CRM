"""WhatsApp do catálogo embutido em Números de WhatsApp (sem item de menu)."""
from conftest import csrf_da_resposta, login


class _EstoqueFake:
    def __init__(self, whatsapp="5511999999999"):
        self.whatsapp = whatsapp
        self.patches: list[str | None] = []

    def obter_loja(self):
        return {"slug": "loja-teste", "nome": "Loja", "whatsapp": self.whatsapp}

    def atualizar_loja(self, *, whatsapp):
        self.patches.append(whatsapp)
        self.whatsapp = whatsapp
        return {"slug": "loja-teste", "nome": "Loja", "whatsapp": whatsapp}


def test_catalogo_redirect_para_whatsapp(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", "1")
    login(client)
    r = client.get("/app/loja/catalogo", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/app/loja/whatsapp")


def test_whatsapp_exibe_e_salva_catalogo(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    fake = _EstoqueFake()

    from app.main import app
    from app.web import loja_whatsapp

    class _ChatbotFake:
        def listar_canais_whatsapp(self):
            return []

    app.dependency_overrides[loja_whatsapp.get_estoque_client] = lambda: fake
    app.dependency_overrides[loja_whatsapp.get_chatbot_client] = lambda: _ChatbotFake()
    try:
        login(client)
        get = client.get("/app/loja/whatsapp")
        assert get.status_code == 200
        assert "WhatsApp do catálogo" in get.text
        assert 'value="5511999999999"' in get.text
        assert 'href="/app/loja/catalogo"' not in get.text or "catalogo-wa" in get.text
        # Menu lateral não deve listar item Catálogo como destino principal
        # (o redirect de /app/loja/catalogo ainda existe).

        csrf = csrf_da_resposta(get)
        post = client.post(
            "/app/loja/whatsapp/catalogo",
            data={"csrf": csrf, "whatsapp": "(21) 98888-7777"},
            follow_redirects=False,
        )
        assert post.status_code == 303
        assert "/app/loja/whatsapp" in post.headers["location"]
        assert fake.patches == ["(21) 98888-7777"]

        after = client.get("/app/loja/whatsapp")
        assert "atualizado" in after.text.lower()
    finally:
        app.dependency_overrides.pop(loja_whatsapp.get_estoque_client, None)
        app.dependency_overrides.pop(loja_whatsapp.get_chatbot_client, None)
