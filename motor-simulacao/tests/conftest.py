"""Fixtures de teste: banco isolado em memória e override da dependência get_db."""
import os

os.environ["MOTOR_SKIP_INIT"] = "1"  # não tocar no engine default ao importar o app
# Sem MOTOR_ENCRYPTION_KEY: cripto usa o fallback de dev (chave Fernet válida).

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models_db  # noqa: E402,F401 (registra os modelos antes do create_all)
from app.auth import hash_token  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models_db import ClienteApiORM, CredencialApiORM  # noqa: E402

TEST_CLIENT_ID = "10000000-0000-0000-0000-000000000001"
TEST_TOKEN = "token-teste-cliente-principal"

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


@pytest.fixture
def client():
    return TestClient(app, headers={"Authorization": f"Bearer {TEST_TOKEN}"})


@pytest.fixture
def db():
    sessao = _TestSession()
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture(autouse=True)
def _limpar_banco(db):
    # Banco de teste é compartilhado; a fila é global. Cada teste começa sem jobs de outros.
    # Rollback limpa transação residual (ex.: worker multi-commit no mesmo StaticPool).
    db.rollback()
    for tabela in (
        "simulacao_eventos",
        "simulacao_tentativas",
        "simulacao_resultados",
        "simulacao_provedores",
        "worker_slots",
        "idempotencia",
        "simulacoes",
        "auditoria",
        "credenciais_provedor",
        "credenciais_api",
        "clientes_api",
    ):
        db.execute(text(f"DELETE FROM {tabela}"))
    db.add(ClienteApiORM(id=TEST_CLIENT_ID, nome="Cliente dos testes"))
    db.add(
        CredencialApiORM(
            id="20000000-0000-0000-0000-000000000001",
            cliente_id=TEST_CLIENT_ID,
            nome="Credencial dos testes",
            token_hash=hash_token(TEST_TOKEN),
        )
    )
    db.commit()
    db.expire_all()
    yield
    db.rollback()
