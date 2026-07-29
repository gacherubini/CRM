def test_health_live(client):
    assert client.get("/health/live").json() == {"status": "ok"}


def test_health_ready_confirma_schema(client):
    resposta = client.get("/health/ready")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_version(client):
    body = client.get("/version").json()
    assert "versao" in body and "schema" in body
