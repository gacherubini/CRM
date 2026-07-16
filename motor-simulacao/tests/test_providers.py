def test_catalogo_expoe_bancos_reais_playwright(client):
    resposta = client.get("/v1/provedores")
    assert resposta.status_code == 200
    provedores = {p["nome"]: p for p in resposta.json()["provedores"]}
    assert provedores["mock"]["real"] is False
    for nome in ("santander", "fontecred", "bradesco", "pan"):
        assert provedores[nome]["modo"] == "playwright"
        assert provedores[nome]["real"] is True
    # PAN: só portal (usuario/senha); sem campos de OpenAPI na UI
    assert {c["nome"] for c in provedores["pan"]["campos_credencial"]} == {
        "usuario",
        "senha",
    }
