from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_live():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready():
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version():
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert "versao" in body and "schema" in body
