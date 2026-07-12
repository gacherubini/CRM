import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models_db, servico
from app.auth import hash_token
from app.db import Base


def _db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_criar_loja_gera_token_valido():
    db = _db()
    loja, token = servico.criar_loja(db, "Loja X", "loja-x", "5511988887777")
    cred = db.get(models_db.CredencialServico, hash_token(token))
    assert cred is not None
    assert cred.loja_id == loja.id
    assert cred.papel == "dono"


def test_slug_duplicado_conflita():
    db = _db()
    servico.criar_loja(db, "L1", "dup")
    with pytest.raises(HTTPException) as exc:
        servico.criar_loja(db, "L2", "dup")
    assert exc.value.status_code == 409


def test_criar_credencial_adicional_para_loja_existente():
    db = _db()
    loja, _ = servico.criar_loja(db, "Loja Credencial", "loja-cred")
    mesma_loja, token = servico.criar_credencial(db, "loja-cred", "operador")
    credencial = db.get(models_db.CredencialServico, hash_token(token))
    assert mesma_loja.id == loja.id
    assert credencial is not None
    assert credencial.papel == "operador"
