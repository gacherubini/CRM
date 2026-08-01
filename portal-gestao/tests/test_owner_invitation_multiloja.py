import pytest
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import PessoaRevyProjetada, Usuario, VinculoLojaPessoa
from app.owner_invitations import (
    OwnerInvitationConflict,
    OwnerInvitationError,
    issue_owner_invitation,
)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def test_issue_owner_invitation_new_user_creates_pessoa_and_vinculo(db: Session):
    invitation = issue_owner_invitation(
        db,
        email="owner@example.com",
        name="Owner One",
        store_slug="loja-a",
    )

    assert invitation.email == "owner@example.com"
    assert invitation.store_slug == "loja-a"

    user = db.query(Usuario).filter(Usuario.email == "owner@example.com").first()
    assert user is not None
    assert user.papel == "dono"
    assert user.ativo is False

    pessoa = db.query(PessoaRevyProjetada).filter(
        PessoaRevyProjetada.id == user.id
    ).first()
    assert pessoa is not None
    assert pessoa.email == "owner@example.com"
    assert pessoa.nome == "Owner One"

    vinculo = db.query(VinculoLojaPessoa).filter(
        VinculoLojaPessoa.pessoa_id == user.id,
        VinculoLojaPessoa.loja_slug == "loja-a",
    ).first()
    assert vinculo is not None
    assert vinculo.cargo == "dono"
    assert vinculo.state == "pendente"


def test_issue_owner_invitation_same_user_new_store_creates_second_vinculo(db: Session):
    issue_owner_invitation(
        db,
        email="owner@example.com",
        name="Owner One",
        store_slug="loja-a",
    )

    invitation2 = issue_owner_invitation(
        db,
        email="owner@example.com",
        name="Owner One",
        store_slug="loja-b",
    )

    assert invitation2.email == "owner@example.com"
    assert invitation2.store_slug == "loja-b"

    user = db.query(Usuario).filter(Usuario.email == "owner@example.com").first()
    assert user is not None

    vinculos = db.query(VinculoLojaPessoa).filter(
        VinculoLojaPessoa.pessoa_id == user.id
    ).all()
    assert len(vinculos) == 2

    slugs = {v.loja_slug for v in vinculos}
    assert slugs == {"loja-a", "loja-b"}


def test_issue_owner_invitation_reissue_same_loja_idempotent(db: Session):
    invitation1 = issue_owner_invitation(
        db,
        email="owner@example.com",
        name="Owner One",
        store_slug="loja-a",
    )

    token1 = invitation1.token

    invitation2 = issue_owner_invitation(
        db,
        email="owner@example.com",
        name="Owner One",
        store_slug="loja-a",
    )

    token2 = invitation2.token

    assert token1 != token2

    vinculo = db.query(VinculoLojaPessoa).filter(
        VinculoLojaPessoa.pessoa_id == invitation1.user_id,
        VinculoLojaPessoa.loja_slug == "loja-a",
    ).first()
    assert vinculo is not None
    assert vinculo.state == "pendente"


def test_issue_owner_invitation_invalid_email_raises_error(db: Session):
    with pytest.raises(OwnerInvitationError):
        issue_owner_invitation(
            db,
            email="invalid",
            name="Owner One",
            store_slug="loja-a",
        )


def test_issue_owner_invitation_invalid_slug_raises_error(db: Session):
    with pytest.raises(OwnerInvitationError):
        issue_owner_invitation(
            db,
            email="owner@example.com",
            name="Owner One",
            store_slug="INVALID SLUG",
        )


def test_issue_owner_invitation_active_user_with_different_papel_raises_error(db: Session):
    user = Usuario(
        email="seller@example.com",
        nome="Seller One",
        senha_hash="fake-hash",
        papel="vendedor",
        loja_slug="loja-a",
        ativo=True,
    )
    db.add(user)
    db.commit()

    with pytest.raises(OwnerInvitationConflict):
        issue_owner_invitation(
            db,
            email="seller@example.com",
            name="Seller One",
            store_slug="loja-b",
        )
