"""Tela Ajustes → Catálogo (WhatsApp do CTA da vitrine)."""
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


def test_catalogo_shell_off_redireciona(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    login(client)
    r = client.get("/app/loja/catalogo", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"


def test_catalogo_get_e_post_whatsapp(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    fake = _EstoqueFake()
    from app.main import app
    from app.web import loja_catalogo

    app.dependency_overrides[loja_catalogo.get_estoque_client] = lambda: fake
    try:
        login(client)
        get = client.get("/app/loja/catalogo")
        assert get.status_code == 200
        assert "WhatsApp do catálogo" in get.text
        assert 'value="5511999999999"' in get.text
        assert 'href="/app/loja/catalogo"' in get.text

        csrf = csrf_da_resposta(get)
        post = client.post(
            "/app/loja/catalogo",
            data={"csrf": csrf, "whatsapp": "(21) 98888-7777"},
            follow_redirects=False,
        )
        assert post.status_code == 200
        assert fake.patches == ["(21) 98888-7777"]
        assert "atualizado" in post.text.lower()
    finally:
        app.dependency_overrides.pop(loja_catalogo.get_estoque_client, None)
