import os

import pytest
from fastapi.testclient import TestClient

os.environ["REVY_TRAFEGO_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["REVY_TRAFEGO_SESSION_SECRET"] = "segredo-teste-trafego"
os.environ["REVY_TRAFEGO_SKIP_INIT"] = "1"
os.environ["REVY_TRAFEGO_META_SPEND_SYNC_ENABLED"] = "0"
os.environ["REVY_TRAFEGO_CAPI_WORKER"] = "0"
os.environ["GOOGLE_ADS_SYNC_ENABLED"] = "0"
os.environ["GOOGLE_CONVERSIONS_ENABLED"] = "0"
os.environ["MULTI_WHATSAPP_ENABLED"] = "0"
os.environ["REVY_CONTROL_DASHBOARD_ENABLED"] = "0"
os.environ["REVY_TRAFEGO_BOOTSTRAP_EMAIL"] = "trafego@revy.local"
os.environ["REVY_TRAFEGO_BOOTSTRAP_SENHA"] = "secret-teste"
os.environ["CHATBOT_API_TOKEN"] = "token-chatbot-teste"

from app.auth import hash_senha  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GestorRevy  # noqa: E402


@pytest.fixture(autouse=True)
def _db_setup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(GestorRevy).count() == 0:
            db.add(
                GestorRevy(
                    email="trafego@revy.local",
                    nome="Equipe Teste",
                    senha_hash=hash_senha("secret-teste"),
                    papel="admin",
                    ativo=True,
                )
            )
            db.commit()
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_logado(client):
    r = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client


def csrf_da_resposta(resposta) -> str:
    import re

    m = re.search(r'name="csrf" value="([^"]+)"', resposta.text)
    assert m, "csrf não encontrado na página"
    return m.group(1)
