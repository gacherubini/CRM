def test_health_live(client):
    assert client.get("/health/live").json() == {"status": "ok"}


def test_version(client):
    body = client.get("/version").json()
    assert "versao" in body and "schema" in body
