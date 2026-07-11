"""Fixtures: banco isolado, override do get_db e lojas de teste (com instância)."""
import os

os.environ["CHATBOT_SKIP_INIT"] = "1"

import uuid  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models_db  # noqa: E402,F401
from app.auth import hash_token  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Base.metadata.create_all(_engine)
_TestSession = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


def _criar_loja(nome, slug, instancia, token):
    db = _TestSession()
    loja = models_db.Loja(
        id=str(uuid.uuid4()), nome=nome, slug=slug, evolution_instance=instancia
    )
    db.add(loja)
    db.add(models_db.CredencialServico(token_hash=hash_token(token), loja_id=loja.id))
    db.commit()
    loja_id = loja.id
    db.close()
    return loja_id


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def loja_a():
    sufixo = uuid.uuid4().hex[:6]
    token = f"tok-a-{uuid.uuid4().hex}"
    inst = f"inst-a-{sufixo}"
    loja_id = _criar_loja("Loja A", f"loja-a-{sufixo}", inst, token)
    return {"loja_id": loja_id, "instance": inst, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def loja_b():
    sufixo = uuid.uuid4().hex[:6]
    token = f"tok-b-{uuid.uuid4().hex}"
    inst = f"inst-b-{sufixo}"
    loja_id = _criar_loja("Loja B", f"loja-b-{sufixo}", inst, token)
    return {"loja_id": loja_id, "instance": inst, "headers": {"Authorization": f"Bearer {token}"}}
