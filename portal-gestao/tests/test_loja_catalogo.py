"""Configuração do catálogo/vitrine — vive em Estoque › Vitrine."""
from conftest import csrf_da_resposta, login


class _EstoqueFake:
    def __init__(self, whatsapp="5511999999999", catalogo_url=""):
        self.whatsapp = whatsapp
        self.catalogo_url = catalogo_url
        self.patches: list[dict] = []

    def obter_loja(self):
        return {
            "slug": "loja-teste",
            "nome": "Loja",
            "whatsapp": self.whatsapp,
            "catalogo_url": self.catalogo_url or None,
        }

    def listar(self, **filtros):
        return []

    def atualizar_loja(self, *, whatsapp=..., catalogo_url=...):
        body = {}
        if whatsapp is not ...:
            body["whatsapp"] = whatsapp
            self.whatsapp = whatsapp
        if catalogo_url is not ...:
            body["catalogo_url"] = catalogo_url
            self.catalogo_url = catalogo_url or ""
        self.patches.append(body)
        return self.obter_loja()


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
    from app.web import loja_estoque, loja_whatsapp

    class _ChatbotFake:
        def listar_canais_whatsapp(self):
            return []

    app.dependency_overrides[loja_whatsapp.get_estoque_client] = lambda: fake
    app.dependency_overrides[loja_estoque.get_estoque_client] = lambda: fake
    app.dependency_overrides[loja_whatsapp.get_chatbot_client] = lambda: _ChatbotFake()
    try:
        login(client)
        get = client.get("/app/loja/estoque/vitrine")
        assert get.status_code == 200
        assert "Catálogo e vitrine" in get.text or "Link do catálogo" in get.text
        assert 'value="5511999999999"' in get.text
        assert 'name="catalogo_url"' in get.text
        # Números de WhatsApp deixou de carregar a configuração da vitrine.
        numeros = client.get("/app/loja/whatsapp")
        assert "Catálogo e vitrine" not in numeros.text

        csrf = csrf_da_resposta(get)
        post = client.post(
            "/app/loja/whatsapp/catalogo",
            data={
                "csrf": csrf,
                "whatsapp": "(21) 98888-7777",
                "catalogo_url": "https://app2037.fly.dev/catalogo/l/loja-teste",
            },
            follow_redirects=False,
        )
        assert post.status_code == 303
        assert "/app/loja/estoque/vitrine" in post.headers["location"]
        assert fake.patches == [
            {
                "whatsapp": "(21) 98888-7777",
                "catalogo_url": "https://app2037.fly.dev/catalogo/l/loja-teste",
            }
        ]

        after = client.get("/app/loja/estoque/vitrine")
        assert "atualizad" in after.text.lower()
    finally:
        app.dependency_overrides.pop(loja_whatsapp.get_estoque_client, None)
        app.dependency_overrides.pop(loja_estoque.get_estoque_client, None)
        app.dependency_overrides.pop(loja_whatsapp.get_chatbot_client, None)
