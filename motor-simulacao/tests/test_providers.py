def test_catalogo_expoe_santander_real_e_pan_api(client):
    resposta = client.get("/v1/provedores")
    assert resposta.status_code == 200
    provedores = {p["nome"]: p for p in resposta.json()["provedores"]}
    assert provedores["mock"]["real"] is False
    assert provedores["santander"]["modo"] == "playwright"
    assert provedores["pan"]["modo"] == "api"
    assert {c["nome"] for c in provedores["pan"]["campos_credencial"]} >= {
        "api_key",
        "secret_key",
        "id_loja",
    }
