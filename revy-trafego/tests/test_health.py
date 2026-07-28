from fastapi.testclient import TestClient

from app.main import app


def test_health_live():
    client = TestClient(app)
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
