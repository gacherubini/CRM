"""Isolamento de permissões Control vs cargos da Loja.

Plano: múltiplos cargos ativos somam permissões somente dentro da loja
selecionada; nenhum cargo ou acesso ao Control vaza para outra loja/superfície.
"""

from __future__ import annotations

import pytest

from app.control.access import AccessControl
from app.control.people import PeopleDirectory
from app.control.permissions import (
    CONTROL_ADMIN,
    CONTROL_GESTOR,
    CONTROL_PREFIX,
    STORE_DONO,
    STORE_GERENTE,
    STORE_PREFIX,
    STORE_VENDEDOR,
    ControlPermissions,
    PermissionBleed,
    StorePermissions,
    assert_no_bleed,
)
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.types import (
    Actor,
    AssignStoreRole,
    CreateStore,
    PersonRef,
    RegisterPerson,
    RevokeStoreRole,
    StoreRef,
    StoreRole,
    StoreRoleRef,
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


def _gestor_actor(*, email: str = "gestor.permissoes@revy.local") -> Actor:
    with SessionLocal() as db:
        existing = db.query(GestorRevy).filter(GestorRevy.email == email).first()
        if existing is None:
            existing = GestorRevy(
                email=email,
                nome="Gestor Permissoes",
                senha_hash="hash-nao-usado-neste-teste",
                papel="gestor",
                ativo=True,
            )
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return Actor(
            id=existing.id,
            email=existing.email,
            name=existing.nome,
            role=existing.papel,
        )


def _two_stores_and_person(admin: Actor):
    stores = StoreControl(SessionLocal)
    people = PeopleDirectory(SessionLocal)
    roles = StoreRoles(SessionLocal)

    store_a = stores.create(
        admin, CreateStore(name="Loja A Perms", slug="loja-a-perms")
    )
    store_b = stores.create(
        admin, CreateStore(name="Loja B Perms", slug="loja-b-perms")
    )
    person = people.register(
        admin,
        RegisterPerson(name="Pessoa Dual", email="pessoa.dual@example.com"),
    )
    return stores, roles, store_a, store_b, person


def test_control_permissions_mapeia_papel_do_actor():
    assert ControlPermissions.for_actor(
        Actor(id="1", email="a@x", name="A", role="admin")
    ) == frozenset({CONTROL_ADMIN})
    assert ControlPermissions.for_actor(
        Actor(id="2", email="g@x", name="G", role="gestor")
    ) == frozenset({CONTROL_GESTOR})
    assert ControlPermissions.for_actor(
        Actor(id="3", email="x@x", name="X", role="desconhecido")
    ) == frozenset()


def test_pessoa_com_controle_gestor_e_cargo_dono_tem_ambos_sem_bleed():
    admin = _admin_actor()
    gestor = _gestor_actor()
    _stores, roles, store_a, _store_b, person = _two_stores_and_person(admin)

    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_a.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )

    # Actor.role é Control-only: cargo dono não entra no Actor e não autoriza Control.
    control_from_gestor = ControlPermissions.for_actor(gestor)
    control_from_admin = ControlPermissions.for_actor(admin)
    store_perms = StorePermissions.for_person_in_store(
        SessionLocal, person.id, store_a.id
    )

    assert control_from_gestor == frozenset({CONTROL_GESTOR})
    assert control_from_admin == frozenset({CONTROL_ADMIN})
    assert store_perms == frozenset({STORE_DONO})

    assert all(code.startswith(CONTROL_PREFIX) for code in control_from_gestor)
    assert all(code.startswith(STORE_PREFIX) for code in store_perms)
    assert not any(code.startswith(STORE_PREFIX) for code in control_from_gestor)
    assert not any(code.startswith(CONTROL_PREFIX) for code in store_perms)

    assert_no_bleed(control_from_gestor, store_perms)
    assert_no_bleed(control_from_admin, store_perms)


def test_cargos_da_loja_a_nao_aparecem_na_loja_b():
    admin = _admin_actor()
    _stores, roles, store_a, store_b, person = _two_stores_and_person(admin)

    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_a.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_a.id),
            person=PersonRef(id=person.id),
            role=StoreRole.MANAGER,
        ),
    )

    perms_a = StorePermissions.for_person_in_store(
        SessionLocal, person.id, store_a.id
    )
    perms_b = StorePermissions.for_person_in_store(
        SessionLocal, person.id, store_b.id
    )

    assert perms_a == frozenset({STORE_DONO, STORE_GERENTE})
    assert perms_b == frozenset()
    assert_no_bleed(ControlPermissions.for_actor(admin), perms_a)
    assert_no_bleed(ControlPermissions.for_actor(admin), perms_b)


def test_multiplos_cargos_na_mesma_loja_unem_permissoes():
    admin = _admin_actor()
    _stores, roles, store_a, _store_b, person = _two_stores_and_person(admin)

    for role in (StoreRole.OWNER, StoreRole.MANAGER, StoreRole.SELLER):
        roles.assign(
            admin,
            AssignStoreRole(
                store=StoreRef(id=store_a.id),
                person=PersonRef(id=person.id),
                role=role,
            ),
        )

    perms = StorePermissions.for_person_in_store(
        SessionLocal, person.id, store_a.id
    )
    assert perms == frozenset({STORE_DONO, STORE_GERENTE, STORE_VENDEDOR})


def test_cargo_encerrado_sai_da_uniao():
    admin = _admin_actor()
    _stores, roles, store_a, _store_b, person = _two_stores_and_person(admin)

    dono = roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_a.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_a.id),
            person=PersonRef(id=person.id),
            role=StoreRole.SELLER,
        ),
    )
    roles.revoke(
        admin,
        RevokeStoreRole(
            store=StoreRef(id=store_a.id),
            assignment=StoreRoleRef(id=dono.id),
            reason="encerrado para teste de união",
        ),
    )

    perms = StorePermissions.for_person_in_store(
        SessionLocal, person.id, store_a.id
    )
    assert perms == frozenset({STORE_VENDEDOR})
    assert STORE_DONO not in perms


def test_assert_no_bleed_rejeita_cruzamento_de_namespaces():
    with pytest.raises(PermissionBleed):
        assert_no_bleed(
            frozenset({CONTROL_GESTOR, STORE_DONO}),
            frozenset({STORE_VENDEDOR}),
        )
    with pytest.raises(PermissionBleed):
        assert_no_bleed(
            frozenset({CONTROL_ADMIN}),
            frozenset({STORE_GERENTE, CONTROL_GESTOR}),
        )
    with pytest.raises(PermissionBleed):
        assert_no_bleed(frozenset({"admin"}), frozenset({STORE_DONO}))
    with pytest.raises(PermissionBleed):
        assert_no_bleed(frozenset({CONTROL_ADMIN}), frozenset({"dono"}))


def test_gestor_sem_vinculo_trafego_nao_ve_loja_mesmo_com_cargo():
    """Control API (Actor + AccessControl) ignora cargos da Loja."""
    admin = _admin_actor()
    gestor = _gestor_actor(email="gestor.sem.vinculo@revy.local")
    _stores, roles, store_a, _store_b, person = _two_stores_and_person(admin)

    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_a.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )

    store_perms = StorePermissions.for_person_in_store(
        SessionLocal, person.id, store_a.id
    )
    control_perms = ControlPermissions.for_actor(gestor)
    assert store_perms == frozenset({STORE_DONO})
    assert control_perms == frozenset({CONTROL_GESTOR})
    assert_no_bleed(control_perms, store_perms)

    # Scope Control usa somente vínculo de tráfego / admin — cargo não vaza.
    scope = AccessControl(SessionLocal).scope(gestor)
    assert scope == ()
