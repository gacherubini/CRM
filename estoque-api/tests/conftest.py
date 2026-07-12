"""Fixtures: banco isolado em memória, override do get_db e lojas de teste."""
import os

os.environ["ESTOQUE_SKIP_INIT"] = "1"

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("ESTOQUE_OUTBOX_KEY", Fernet.generate_key().decode())

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


def _criar_loja(nome: str, slug: str, token: str, papel: str = "dono") -> str:
    db = _TestSession()
    loja = models_db.Loja(id=str(uuid.uuid4()), nome=nome, slug=slug, whatsapp="5511999999999")
    db.add(loja)
    db.add(
        models_db.CredencialServico(
            token_hash=hash_token(token), loja_id=loja.id, papel=papel
        )
    )
    db.commit()
    loja_id = loja.id
    db.close()
    return loja_id


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    sessao = _TestSession()
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture
def loja_a():
    token = f"tok-a-{uuid.uuid4().hex}"
    slug = f"loja-a-{uuid.uuid4().hex[:6]}"
    loja_id = _criar_loja("Loja A", slug, token)
    return {"loja_id": loja_id, "slug": slug, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def loja_b():
    token = f"tok-b-{uuid.uuid4().hex}"
    slug = f"loja-b-{uuid.uuid4().hex[:6]}"
    loja_id = _criar_loja("Loja B", slug, token)
    return {"loja_id": loja_id, "slug": slug, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def operador_loja_a(loja_a):
    token = f"tok-op-{uuid.uuid4().hex}"
    db = _TestSession()
    db.add(
        models_db.CredencialServico(
            token_hash=hash_token(token), loja_id=loja_a["loja_id"], papel="operador"
        )
    )
    db.commit()
    db.close()
    return {"headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def leitor_loja_a(loja_a):
    token = f"tok-read-{uuid.uuid4().hex}"
    db = _TestSession()
    db.add(
        models_db.CredencialServico(
            token_hash=hash_token(token), loja_id=loja_a["loja_id"], papel="leitor"
        )
    )
    db.commit()
    db.close()
    return {"headers": {"Authorization": f"Bearer {token}"}}
