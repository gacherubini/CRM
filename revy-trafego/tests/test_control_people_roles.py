from dataclasses import fields

import pytest

from app.control.access import AccessControl
from app.control.audit import AuditTrail
from app.control.people import PeopleDirectory
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    AssignStoreRole,
    AuditQuery,
    CreateStore,
    GrantTrafficAccess,
    InvalidPersonEmail,
    PersonEmailConflict,
    PersonRef,
    RegisterPerson,
    RevokeStoreRole,
    RevokeTrafficAccess,
    StoreRef,
    StoreRole,
    StoreRoleConflict,
    StoreNotFound,
    TrafficRole,
)
from app.db import SessionLocal
from app.models import GestorRevy


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _manager_actor(email: str) -> Actor:
    with SessionLocal() as db:
        manager = GestorRevy(
            email=email,
            nome=email.split("@", 1)[0].title(),
            senha_hash="hash-nao-usado-neste-teste",
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()
        db.refresh(manager)
        return Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )


def test_admin_registra_pessoa_e_atribui_multiplos_cargos_na_loja():
    admin = _admin_actor()
    people = PeopleDirectory(SessionLocal)
    roles = StoreRoles(SessionLocal)
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Centro", slug="loja-centro"),
    )

    registered = people.register(
        admin,
        RegisterPerson(
            name="  Ana Souza  ",
            email="  ANA.SOUZA@EXAMPLE.COM  ",
        ),
    )
    owner = roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=registered.id),
            role=StoreRole.OWNER,
        ),
    )
    manager = roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=registered.id),
            role=StoreRole.MANAGER,
        ),
    )

    with pytest.raises(StoreRoleConflict):
        roles.assign(
            admin,
            AssignStoreRole(
                store=StoreRef(id=store.id),
                person=PersonRef(id=registered.id),
                role=StoreRole.OWNER,
            ),
        )

    by_id = people.get(admin, PersonRef(id=registered.id))
    by_email = people.find_by_email(admin, " ANA.SOUZA@EXAMPLE.COM ")
    assigned = roles.list_for_store(admin, StoreRef(id=store.id))
    events = AuditTrail(SessionLocal).list(admin, AuditQuery()).items

    assert tuple(field.name for field in fields(registered)) == (
        "id",
        "name",
        "email",
        "created_at",
        "updated_at",
    )
    assert by_id == registered
    assert by_email == registered
    assert registered.name == "Ana Souza"
    assert registered.email == "ana.souza@example.com"
    assert {
        (item.person_id, item.role, item.active)
        for item in assigned
    } == {
        (registered.id, StoreRole.OWNER, True),
        (registered.id, StoreRole.MANAGER, True),
    }
    assert owner.store_id == store.id
    assert manager.store_id == store.id
    assert [event.action for event in events] == [
        "store.created",
        "person.registered",
        "store_role.assigned",
        "store_role.assigned",
    ]
    assert events[1].after == {
        "email": "ana.souza@example.com",
        "name": "Ana Souza",
    }


def test_identidade_rejeita_email_invalido_e_duplicado_explicitamente():
    admin = _admin_actor()
    people = PeopleDirectory(SessionLocal)
    registered = people.register(
        admin,
        RegisterPerson(name="Ana Souza", email="ana.souza@example.com"),
    )

    with pytest.raises(PersonEmailConflict) as duplicate:
        people.register(
            admin,
            RegisterPerson(
                name="Outra Ana",
                email=" ANA.SOUZA@EXAMPLE.COM ",
            ),
        )
    with pytest.raises(InvalidPersonEmail) as invalid:
        people.register(
            admin,
            RegisterPerson(name="Sem E-mail", email="sem-arroba.example.com"),
        )

    assert duplicate.value.email == registered.email
    assert invalid.value.email == "sem-arroba.example.com"
    assert people.find_by_email(admin, registered.email) == registered


def test_gestor_lista_cargos_somente_enquanto_tem_vinculo_ativo_com_a_loja():
    admin = _admin_actor()
    manager = _manager_actor("gestor.escopado@revy.local")
    people = PeopleDirectory(SessionLocal)
    roles = StoreRoles(SessionLocal)
    stores = StoreControl(SessionLocal)
    traffic_access = AccessControl(SessionLocal)
    linked_store = stores.create(
        admin,
        CreateStore(name="Loja Vinculada", slug="loja-vinculada"),
    )
    other_store = stores.create(
        admin,
        CreateStore(name="Outra Loja", slug="outra-loja"),
    )
    person = people.register(
        admin,
        RegisterPerson(name="Pessoa Multi Loja", email="multi.loja@example.com"),
    )

    with pytest.raises(AccessDenied):
        people.get(manager, PersonRef(id=person.id))
    with pytest.raises(AccessDenied):
        roles.assign(
            manager,
            AssignStoreRole(
                store=StoreRef(id=linked_store.id),
                person=PersonRef(id=person.id),
                role=StoreRole.OWNER,
            ),
        )

    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=linked_store.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=other_store.id),
            person=PersonRef(id=person.id),
            role=StoreRole.SELLER,
        ),
    )
    traffic_access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=linked_store.id),
            manager_id=manager.id,
            role=TrafficRole.COLLABORATOR,
        ),
    )

    visible = roles.list_for_store(manager, StoreRef(id=linked_store.id))
    with pytest.raises(StoreNotFound):
        roles.list_for_store(manager, StoreRef(id=other_store.id))

    traffic_access.revoke(
        admin,
        RevokeTrafficAccess(
            store=StoreRef(id=linked_store.id),
            manager_id=manager.id,
        ),
    )

    assert [(item.person_id, item.role) for item in visible] == [
        (person.id, StoreRole.OWNER),
    ]
    assert [
        (item.person_id, item.role)
        for item in roles.list_for_store(admin, StoreRef(id=other_store.id))
    ] == [(person.id, StoreRole.SELLER)]
    with pytest.raises(StoreNotFound):
        roles.list_for_store(manager, StoreRef(id=linked_store.id))


def test_revogacao_preserva_historico_e_permitem_nova_atribuicao_auditada():
    admin = _admin_actor()
    people = PeopleDirectory(SessionLocal)
    roles = StoreRoles(SessionLocal)
    audit = AuditTrail(SessionLocal)
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Histórica", slug="loja-historica"),
    )
    person = people.register(
        admin,
        RegisterPerson(name="Dono Histórico", email="historico@example.com"),
    )
    command = AssignStoreRole(
        store=StoreRef(id=store.id),
        person=PersonRef(id=person.id),
        role=StoreRole.OWNER,
    )
    first = roles.assign(admin, command)

    revoked = roles.revoke(
        admin,
        RevokeStoreRole(
            store=command.store,
            person=command.person,
            role=command.role,
            reason="troca temporária de dono",
        ),
    )
    second = roles.assign(admin, command)

    active = roles.list_for_store(admin, StoreRef(id=store.id))
    history = roles.list_for_store(
        admin,
        StoreRef(id=store.id),
        include_ended=True,
    )
    events = audit.list(admin, AuditQuery(store_id=store.id)).items

    assert first.id == revoked.id
    assert revoked.active is False
    assert second.id != first.id
    assert [(item.id, item.active) for item in active] == [(second.id, True)]
    assert {
        (item.id, item.role, item.active)
        for item in history
    } == {
        (first.id, StoreRole.OWNER, False),
        (second.id, StoreRole.OWNER, True),
    }
    assert [event.action for event in events] == [
        "store.created",
        "store_role.assigned",
        "store_role.revoked",
        "store_role.assigned",
    ]
    assert events[2].before == {
        "active": True,
        "person_id": person.id,
        "role": "dono",
    }
    assert events[2].after == {
        "active": False,
        "person_id": person.id,
        "role": "dono",
    }
    assert events[2].reason == "troca temporária de dono"
