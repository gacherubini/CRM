def test_health_live(client):
    resposta = client.get("/health/live")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_health_ready_confirma_banco_e_estoque_configurado(client):
    resposta = client.get("/health/ready")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "estoque_configurado": True}
