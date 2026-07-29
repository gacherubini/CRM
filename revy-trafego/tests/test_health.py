from fastapi.testclient import TestClient

from app.main import app


def test_health_live():
    client = TestClient(app)
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_ready_confirma_schema():
    client = TestClient(app)
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
