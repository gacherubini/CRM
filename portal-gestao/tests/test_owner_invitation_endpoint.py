import os
import pytest
from fastapi.testclient import TestClient

os.environ["PORTAL_SERVICE_TOKEN"] = "test-service-token"

from app.db import SessionLocal
from app.main import app
from app.models import PessoaRevyProjetada, Usuario, VinculoLojaPessoa


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def test_invite_owner_internal_new_user_returns_200(client):
    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "owner@example.com",
            "nome": "Owner One",
            "loja_slug": "loja-a",
        },
        headers={"X-Service-Token": "test-service-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "owner@example.com"
    assert data["loja_slug"] == "loja-a"
    assert "usuario_id" in data
    assert "expira_em" in data


def test_invite_owner_internal_existing_user_different_store_returns_200(client, db):
    user = Usuario(
        email="owner@example.com",
        nome="Owner One",
        senha_hash="fake-hash",
        papel="dono",
        loja_slug="loja-a",
        ativo=False,
    )
    db.add(user)
    db.flush()

    pessoa = PessoaRevyProjetada(
        id=user.id,
        email="owner@example.com",
        nome="Owner One",
    )
    db.add(pessoa)
    db.flush()

    vinculo = VinculoLojaPessoa(
        pessoa_id=user.id,
        loja_slug="loja-a",
        cargo="dono",
        state="pendente",
        versao=0,
    )
    db.add(vinculo)
    db.commit()

    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "owner@example.com",
            "nome": "Owner One",
            "loja_slug": "loja-b",
        },
        headers={"X-Service-Token": "test-service-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "owner@example.com"
    assert data["loja_slug"] == "loja-b"

    db_vinculos = db.query(VinculoLojaPessoa).filter(
        VinculoLojaPessoa.pessoa_id == user.id
    ).all()
    assert len(db_vinculos) == 2

    slugs = {v.loja_slug for v in db_vinculos}
    assert slugs == {"loja-a", "loja-b"}


def test_invite_owner_internal_reissue_inactive_same_store_returns_200_with_reenvio(client, db):
    user = Usuario(
        email="owner@example.com",
        nome="Owner One",
        senha_hash="fake-hash",
        papel="dono",
        loja_slug="loja-a",
        ativo=False,
    )
    db.add(user)
    db.flush()

    pessoa = PessoaRevyProjetada(
        id=user.id,
        email="owner@example.com",
        nome="Owner One",
    )
    db.add(pessoa)
    db.flush()

    vinculo = VinculoLojaPessoa(
        pessoa_id=user.id,
        loja_slug="loja-a",
        cargo="dono",
        state="pendente",
        versao=0,
    )
    db.add(vinculo)
    db.commit()

    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "owner@example.com",
            "nome": "Owner One",
            "loja_slug": "loja-a",
        },
        headers={"X-Service-Token": "test-service-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "owner@example.com"


def test_invite_owner_internal_email_de_outro_papel_returns_409(client, db):
    # E-mail que já pertence a um vendedor não pode virar dono: conflito real (409),
    # não "sucesso" mascarado.
    user = Usuario(
        email="vendedor@example.com",
        nome="Vendedor",
        senha_hash="fake-hash",
        papel="vendedor",
        loja_slug="loja-a",
        ativo=True,
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "vendedor@example.com",
            "nome": "Vendedor",
            "loja_slug": "loja-b",
        },
        headers={"X-Service-Token": "test-service-token"},
    )

    assert response.status_code == 409


def test_invite_owner_internal_invalid_email_returns_422(client):
    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "invalid",
            "nome": "Owner One",
            "loja_slug": "loja-a",
        },
        headers={"X-Service-Token": "test-service-token"},
    )

    assert response.status_code == 422


def test_invite_owner_internal_missing_token_returns_401(client):
    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "owner@example.com",
            "nome": "Owner One",
            "loja_slug": "loja-a",
        },
    )

    assert response.status_code == 401


def test_invite_owner_internal_wrong_token_returns_401(client):
    response = client.post(
        "/internal/v1/lojistas/convite",
        json={
            "email": "owner@example.com",
            "nome": "Owner One",
            "loja_slug": "loja-a",
        },
        headers={"X-Service-Token": "wrong-token"},
    )

    assert response.status_code == 401
