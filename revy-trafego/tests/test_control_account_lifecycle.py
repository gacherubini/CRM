import pytest

from app.auth import hash_senha
from app.control.access_backfill import backfill_acessos_control
from app.control.accounts import ControlAccounts
from app.control.audit import AuditTrail
from app.control.people import PeopleDirectory
from app.control.types import (
    AccessDenied,
    Actor,
    AuditQuery,
    ControlAccountConflict,
    ControlAccountStatus,
    RegisterPerson,
)
from app.db import SessionLocal
from app.models import AcessoControl, GestorRevy


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _project_manager(email: str) -> tuple[str, str]:
    password_hash = hash_senha("senha-lifecycle")
    with SessionLocal() as db:
        manager = GestorRevy(
            email=email,
            nome="Gestor Lifecycle",
            senha_hash=password_hash,
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.flush()
        manager_id = manager.id
        backfill_acessos_control(db.connection())
        db.commit()
    return manager_id, password_hash


def test_admin_desativa_e_reativa_acesso_revogando_sessoes_e_legado():
    manager_id, password_hash = _project_manager(
        "gestor.lifecycle@revy.local"
    )
    admin = _admin_actor()
    accounts = ControlAccounts(SessionLocal)

    disabled = accounts.disable(admin, manager_id)

    assert disabled.id == manager_id
    assert disabled.status is ControlAccountStatus.DISABLED
    assert [
        item.status
        for item in accounts.list(admin)
        if item.id == manager_id
    ] == [ControlAccountStatus.DISABLED]
    with SessionLocal() as db:
        access = db.get(AcessoControl, manager_id)
        manager = db.get(GestorRevy, manager_id)
        assert access is not None
        assert access.sessao_versao == 2
        assert access.senha_hash == password_hash
        assert manager is not None
        assert manager.ativo is False

    enabled = accounts.enable(admin, manager_id)

    assert enabled.id == manager_id
    assert enabled.status is ControlAccountStatus.ACTIVE
    with SessionLocal() as db:
        access = db.get(AcessoControl, manager_id)
        manager = db.get(GestorRevy, manager_id)
        assert access is not None
        assert access.sessao_versao == 3
        assert access.senha_hash == password_hash
        assert manager is not None
        assert manager.ativo is True
    events = AuditTrail(SessionLocal).list(admin, AuditQuery()).items
    assert [event.action for event in events] == [
        "control_account.disabled",
        "control_account.enabled",
    ]
    assert events[0].before == {
        "session_version": 1,
        "status": "ativo",
    }
    assert events[0].after == {
        "session_version": 2,
        "status": "desativado",
    }
    assert events[1].before == {
        "session_version": 2,
        "status": "desativado",
    }
    assert events[1].after == {
        "session_version": 3,
        "status": "ativo",
    }


def test_lifecycle_exige_admin_bloqueia_auto_desativacao_e_transicoes_repetidas():
    manager_id, _ = _project_manager("gestor.guardas@revy.local")
    admin = _admin_actor()
    with SessionLocal() as db:
        manager = db.get(GestorRevy, manager_id)
        assert manager is not None
        manager_actor = Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )
    accounts = ControlAccounts(SessionLocal)

    with pytest.raises(AccessDenied):
        accounts.disable(manager_actor, manager_id)
    with pytest.raises(AccessDenied):
        accounts.enable(manager_actor, manager_id)
    with pytest.raises(
        ControlAccountConflict,
        match="não pode desativar o próprio acesso",
    ):
        accounts.disable(admin, admin.id)
    with pytest.raises(
        ControlAccountConflict,
        match="Acesso Control não encontrado",
    ):
        accounts.enable(admin, "acesso-inexistente")

    accounts.disable(admin, manager_id)
    with pytest.raises(
        ControlAccountConflict,
        match="somente acesso ativo",
    ):
        accounts.disable(admin, manager_id)
    accounts.enable(admin, manager_id)
    with pytest.raises(
        ControlAccountConflict,
        match="somente acesso desativado",
    ):
        accounts.enable(admin, manager_id)

    with SessionLocal() as db:
        access = db.get(AcessoControl, manager_id)
        manager = db.get(GestorRevy, manager_id)
        assert access is not None
        assert access.estado == "ativo"
        assert access.sessao_versao == 3
        assert manager is not None
        assert manager.ativo is True
    events = AuditTrail(SessionLocal).list(admin, AuditQuery()).items
    assert [event.action for event in events] == [
        "control_account.disabled",
        "control_account.enabled",
    ]


def test_reativacao_exige_credencial_e_gestor_legado():
    _project_manager("gestor.setup@revy.local")
    admin = _admin_actor()
    person = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(
            name="Acesso sem Credencial",
            email="sem.credencial@example.com",
        ),
    )
    with SessionLocal() as db:
        db.add(
            AcessoControl(
                id="acesso-sem-credencial",
                pessoa_id=person.id,
                papel="gestor",
                estado="desativado",
                senha_hash=None,
                sessao_versao=4,
                gestor_legado_id=None,
            )
        )
        db.commit()

    accounts = ControlAccounts(SessionLocal)
    with pytest.raises(
        ControlAccountConflict,
        match="não possui credencial e gestor legado",
    ):
        accounts.enable(admin, "acesso-sem-credencial")

    visible = {
        item.id: item
        for item in accounts.list(admin)
    }["acesso-sem-credencial"]
    assert visible.status is ControlAccountStatus.DISABLED
    with SessionLocal() as db:
        access = db.get(AcessoControl, "acesso-sem-credencial")
        assert access is not None
        assert access.sessao_versao == 4
    assert [
        event.action
        for event in AuditTrail(SessionLocal).list(
            admin,
            AuditQuery(),
        ).items
    ] == ["person.registered"]
