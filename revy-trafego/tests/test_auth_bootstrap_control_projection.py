import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.auth import autenticar, bootstrap_gestor_se_vazio, hash_senha
from app.control.people import PeopleDirectory
from app.control.types import Actor
from app.db import Base
from app.models import AcessoControl, GestorRevy, Pessoa


def _isolated_sessions(tmp_path, name: str):
    engine = sa.create_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _actor_for(manager: GestorRevy) -> Actor:
    return Actor(
        id=manager.id,
        email=manager.email,
        name=manager.nome,
        role=manager.papel,
    )


def test_bootstrap_vazio_cria_gestor_pessoa_e_acesso_sem_cortar_auth(tmp_path):
    sessions = _isolated_sessions(tmp_path, "bootstrap-vazio.db")

    with sessions() as db:
        created = bootstrap_gestor_se_vazio(
            db,
            email="  ADMIN.BOOTSTRAP@EXAMPLE.COM  ",
            senha="senha-bootstrap-segura",
            nome="Admin Bootstrap",
        )

        assert created is not None
        manager_id = created.id
        manager_hash = created.senha_hash
        authenticated = autenticar(
            db,
            "ADMIN.BOOTSTRAP@EXAMPLE.COM",
            "senha-bootstrap-segura",
        )
        assert authenticated is not None
        assert authenticated.id == manager_id

        repeated = bootstrap_gestor_se_vazio(
            db,
            email="outro.admin@example.com",
            senha="outra-senha",
            nome="Outro Admin",
        )
        assert repeated is None
        actor = _actor_for(created)

    person = PeopleDirectory(sessions).find_by_email(
        actor,
        " admin.bootstrap@example.com ",
    )
    assert person is not None
    assert person.email == "admin.bootstrap@example.com"
    assert person.name == "Admin Bootstrap"

    with sessions() as db:
        accesses = db.query(AcessoControl).all()
        managers = db.query(GestorRevy).all()

    assert len(managers) == 1
    assert managers[0].id == manager_id
    assert len(accesses) == 1
    assert accesses[0].id == manager_id
    assert accesses[0].gestor_legado_id == manager_id
    assert accesses[0].pessoa_id == person.id
    assert accesses[0].papel == "admin"
    assert accesses[0].estado == "ativo"
    assert accesses[0].senha_hash == manager_hash
    assert manager_hash.startswith("$argon2")


def test_bootstrap_reconcilia_gestor_existente_sem_alterar_legado(tmp_path):
    sessions = _isolated_sessions(tmp_path, "bootstrap-legado.db")
    legacy_hash = hash_senha("senha-legada")

    with sessions() as db:
        legacy = GestorRevy(
            id="gestor-legado-admin",
            email="admin.legado@example.com",
            nome="Admin Legado Preservado",
            senha_hash=legacy_hash,
            papel="admin",
            ativo=True,
        )
        db.add(legacy)
        db.commit()
        before = (
            legacy.id,
            legacy.email,
            legacy.nome,
            legacy.senha_hash,
            legacy.papel,
            legacy.ativo,
            legacy.criado_em,
        )

        first = bootstrap_gestor_se_vazio(
            db,
            email="bootstrap.ignorado@example.com",
            senha="senha-ignorada",
            nome="Nome Ignorado",
        )
        second = bootstrap_gestor_se_vazio(
            db,
            email="outro.ignorado@example.com",
            senha="outra-senha-ignorada",
            nome="Outro Nome Ignorado",
        )
        assert first is None
        assert second is None
        db.refresh(legacy)
        after = (
            legacy.id,
            legacy.email,
            legacy.nome,
            legacy.senha_hash,
            legacy.papel,
            legacy.ativo,
            legacy.criado_em,
        )
        authenticated = autenticar(
            db,
            "ADMIN.LEGADO@EXAMPLE.COM",
            "senha-legada",
        )
        assert authenticated is not None
        assert authenticated.id == legacy.id
        actor = _actor_for(legacy)

    assert after == before
    person = PeopleDirectory(sessions).find_by_email(
        actor,
        "admin.legado@example.com",
    )
    assert person is not None
    assert person.name == "Admin Legado Preservado"

    with sessions() as db:
        accesses = db.query(AcessoControl).all()
        managers = db.query(GestorRevy).all()

    assert len(managers) == 1
    assert len(accesses) == 1
    assert accesses[0].id == legacy.id
    assert accesses[0].gestor_legado_id == legacy.id
    assert accesses[0].pessoa_id == person.id
    assert accesses[0].senha_hash == legacy_hash


def test_bootstrap_com_email_invalido_reverte_gestor_e_projecao(tmp_path):
    sessions = _isolated_sessions(tmp_path, "bootstrap-invalido.db")

    with sessions() as db:
        with pytest.raises(RuntimeError, match="e-mail inválido"):
            bootstrap_gestor_se_vazio(
                db,
                email="email-sem-arroba",
                senha="senha-nao-persistida",
                nome="Gestor Não Persistido",
            )

    with sessions() as db:
        assert db.query(GestorRevy).count() == 0
        assert db.query(Pessoa).count() == 0
        assert db.query(AcessoControl).count() == 0
        assert autenticar(db, "email-sem-arroba", "senha-nao-persistida") is None
