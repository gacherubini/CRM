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
    StoreRoleNotFound,
    StoreRoleRef,
    StoreReadinessBlocked,
    StoreNotFound,
    TrafficRole,
    StoreStatus,
    TransitionStore,
)
from app.db import SessionLocal
from app.models import AcessoControl, GestorRevy, agora


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


_TRANSITIONS_TO = {
    StoreStatus.DRAFT: (),
    StoreStatus.CONFIGURING: (StoreStatus.CONFIGURING,),
    StoreStatus.READY: (StoreStatus.CONFIGURING, StoreStatus.READY),
    StoreStatus.ACTIVE: (
        StoreStatus.CONFIGURING,
        StoreStatus.READY,
        StoreStatus.ACTIVE,
    ),
    StoreStatus.SUSPENDED: (
        StoreStatus.CONFIGURING,
        StoreStatus.READY,
        StoreStatus.ACTIVE,
        StoreStatus.SUSPENDED,
    ),
    StoreStatus.CLOSED: (
        StoreStatus.CONFIGURING,
        StoreStatus.READY,
        StoreStatus.ACTIVE,
        StoreStatus.SUSPENDED,
        StoreStatus.CLOSED,
    ),
}


def _grant_activatable_access(person_id: str, *, estado: str = "pendente") -> None:
    now = agora()
    with SessionLocal() as db:
        db.add(
            AcessoControl(
                pessoa_id=person_id,
                papel="gestor",
                estado=estado,
                senha_hash=None if estado == "pendente" else "hash-teste",
                sessao_versao=1,
                gestor_legado_id=None,
                criada_em=now,
                atualizada_em=now,
            )
        )
        db.commit()


def _store_with_owners(admin, *, slug, status, owner_count=1):
    stores = StoreControl(SessionLocal)
    people = PeopleDirectory(SessionLocal)
    roles = StoreRoles(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name=f"Loja {slug}", slug=slug),
    )
    owners = [
        people.register(
            admin,
            RegisterPerson(
                name=f"Dono {index}",
                email=f"{slug}.dono-{index}@example.com",
            ),
        )
        for index in range(1, owner_count + 1)
    ]
    assigned = [
        roles.assign(
            admin,
            AssignStoreRole(
                store=StoreRef(id=store.id),
                person=PersonRef(id=owner.id),
                role=StoreRole.OWNER,
            ),
        )
        for owner in owners
    ]
    needs_ready = status in {
        StoreStatus.READY,
        StoreStatus.ACTIVE,
        StoreStatus.SUSPENDED,
        StoreStatus.CLOSED,
    }
    if needs_ready:
        for owner in owners:
            _grant_activatable_access(owner.id)
    for target in _TRANSITIONS_TO[status]:
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=target,
            ),
        )
    return stores, roles, store, owners, assigned


def test_loja_em_configuracao_sem_dono_nao_pode_ficar_pronta():
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja sem Dono", slug="loja-sem-dono"),
    )
    configuring = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.CONFIGURING,
        ),
    )

    with pytest.raises(StoreReadinessBlocked) as error:
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=StoreStatus.READY,
            ),
        )

    current = stores.get(admin, StoreRef(id=store.id))
    events = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=store.id),
    ).items
    assert configuring.status is StoreStatus.CONFIGURING
    assert error.value.store_id == store.id
    assert error.value.requirement == "active_owner"
    assert current.status is StoreStatus.CONFIGURING
    assert [event.action for event in events] == [
        "store.created",
        "store.status_changed",
    ]


def test_dono_revogado_nao_satisfaz_prontidao_da_loja():
    admin = _admin_actor()
    stores, roles, store, _, assigned = _store_with_owners(
        admin,
        slug="loja-sem-dono-ativo",
        status=StoreStatus.CONFIGURING,
    )
    roles.revoke(
        admin,
        RevokeStoreRole(
            store=StoreRef(id=store.id),
            assignment=StoreRoleRef(id=assigned[0].id),
        ),
    )

    with pytest.raises(StoreReadinessBlocked):
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=StoreStatus.READY,
            ),
        )

    assert stores.get(admin, StoreRef(id=store.id)).status is StoreStatus.CONFIGURING


def test_dono_ativo_sem_acesso_ativavel_nao_permite_loja_ficar_pronta():
    admin = _admin_actor()
    stores, _, store, _, _ = _store_with_owners(
        admin,
        slug="loja-dono-sem-acesso",
        status=StoreStatus.CONFIGURING,
    )

    with pytest.raises(StoreReadinessBlocked) as error:
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=StoreStatus.READY,
            ),
        )

    assert error.value.requirement == "activatable_owner"
    assert stores.get(admin, StoreRef(id=store.id)).status is StoreStatus.CONFIGURING


def test_dono_com_acesso_ativavel_permite_loja_ficar_pronta():
    admin = _admin_actor()
    stores, _, store, owners, _ = _store_with_owners(
        admin,
        slug="loja-com-dono",
        status=StoreStatus.CONFIGURING,
    )
    _grant_activatable_access(owners[0].id)

    ready = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.READY,
        ),
    )

    assert ready.status is StoreStatus.READY


@pytest.mark.parametrize(
    "protected_status",
    (
        StoreStatus.READY,
        StoreStatus.ACTIVE,
        StoreStatus.SUSPENDED,
    ),
)
def test_revogar_ultimo_dono_de_loja_operacional_preserva_estado_e_historico(
    protected_status,
):
    admin = _admin_actor()
    audit = AuditTrail(SessionLocal)
    stores, roles, store, _, assigned = _store_with_owners(
        admin,
        slug="loja-operacional-protegida",
        status=protected_status,
    )
    events_before = audit.list(admin, AuditQuery(store_id=store.id)).items

    with pytest.raises(StoreReadinessBlocked) as error:
        roles.revoke(
            admin,
            RevokeStoreRole(
                store=StoreRef(id=store.id),
                assignment=StoreRoleRef(id=assigned[0].id),
            ),
        )

    current = stores.get(admin, StoreRef(id=store.id))
    role_history = roles.list_for_store(
        admin,
        StoreRef(id=store.id),
        include_ended=True,
    )
    events_after = audit.list(admin, AuditQuery(store_id=store.id)).items
    assert error.value.store_id == store.id
    assert error.value.requirement == "active_owner"
    assert current.status is protected_status
    assert [(item.id, item.active) for item in role_history] == [
        (assigned[0].id, True),
    ]
    assert events_after == events_before


@pytest.mark.parametrize(
    "permissive_status",
    (
        StoreStatus.DRAFT,
        StoreStatus.CONFIGURING,
        StoreStatus.CLOSED,
    ),
)
def test_ultimo_dono_pode_ser_revogado_em_estado_permissivo(permissive_status):
    admin = _admin_actor()
    stores, roles, store, _, assigned = _store_with_owners(
        admin,
        slug="loja-permissiva",
        status=permissive_status,
    )

    revoked = roles.revoke(
        admin,
        RevokeStoreRole(
            store=StoreRef(id=store.id),
            assignment=StoreRoleRef(id=assigned[0].id),
        ),
    )

    assert revoked.active is False
    assert stores.get(admin, StoreRef(id=store.id)).status is permissive_status


def test_loja_pronta_permite_revogar_dono_quando_outro_permanece_ativo():
    admin = _admin_actor()
    _, roles, store, owners, assigned = _store_with_owners(
        admin,
        slug="loja-dois-donos",
        status=StoreStatus.READY,
        owner_count=2,
    )

    revoked = roles.revoke(
        admin,
        RevokeStoreRole(
            store=StoreRef(id=store.id),
            assignment=StoreRoleRef(id=assigned[0].id),
        ),
    )

    active = roles.list_for_store(admin, StoreRef(id=store.id))
    assert revoked.id == assigned[0].id
    assert revoked.active is False
    assert [(item.id, item.person_id) for item in active] == [
        (assigned[1].id, owners[1].id),
    ]


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
            assignment=StoreRoleRef(id=first.id),
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


def test_repetir_revogacao_antiga_nao_revoga_cargo_reatribuido():
    admin = _admin_actor()
    _, roles, store, owners, assigned = _store_with_owners(
        admin,
        slug="loja-sem-aba",
        status=StoreStatus.DRAFT,
    )
    old_role = assigned[0]
    command = RevokeStoreRole(
        store=StoreRef(id=store.id),
        assignment=StoreRoleRef(id=old_role.id),
        reason="troca temporária",
    )
    roles.revoke(admin, command)
    new_role = roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=owners[0].id),
            role=StoreRole.OWNER,
        ),
    )

    with pytest.raises(StoreRoleNotFound):
        roles.revoke(admin, command)

    active = roles.list_for_store(admin, StoreRef(id=store.id))
    assert new_role.id != old_role.id
    assert [(item.id, item.active) for item in active] == [(new_role.id, True)]


def test_id_de_cargo_de_outra_loja_parece_inexistente():
    admin = _admin_actor()
    _, roles, source_store, _, source_roles = _store_with_owners(
        admin,
        slug="loja-origem-cargo",
        status=StoreStatus.DRAFT,
    )
    _, _, target_store, _, _ = _store_with_owners(
        admin,
        slug="loja-destino-cargo",
        status=StoreStatus.DRAFT,
    )

    with pytest.raises(StoreRoleNotFound):
        roles.revoke(
            admin,
            RevokeStoreRole(
                store=StoreRef(id=target_store.id),
                assignment=StoreRoleRef(id=source_roles[0].id),
            ),
        )

    source_active = roles.list_for_store(
        admin,
        StoreRef(id=source_store.id),
    )
    assert [(item.id, item.active) for item in source_active] == [
        (source_roles[0].id, True),
    ]
