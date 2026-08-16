from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.control.people import PeopleDirectory
from app.control.portfolio import PortfolioControl
from app.control.provisioning import ProvisioningControl
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.types import (
    Actor,
    AssignStoreRole,
    CreateStore,
    PersonRef,
    RegisterPerson,
    StoreRef,
    StoreRole,
)
from app.db import SessionLocal
from app.models import GestorRevy, Loja, ModuloRevy


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _seed_module_catalog() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                ModuloRevy(id="copiloto", codigo="copiloto", nome="Copiloto de Vendas"),
                ModuloRevy(id="financeiro", codigo="financeiro", nome="Financeiro"),
            ]
        )
        db.commit()


def test_snapshot_inclui_copiloto_quando_contratado():
    _seed_module_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Copiloto Snap", slug="loja-copiloto-snap"),
    )
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque", "copiloto"},
    )

    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store.id))

    aggregates = tuple(item.aggregate for item in snapshot.operational)
    assert aggregates == ("loja", "whatsapp_modo", "vendas", "estoque", "copiloto")
    copiloto_env = next(
        item for item in snapshot.operational if item.aggregate == "copiloto"
    )
    assert copiloto_env.state == "ativo"
    assert copiloto_env.version == 1
    # event_id do snapshot precisa mudar ao ganhar copiloto (senão o outbox
    # deduplica contra a entrega anterior de vendas+estoque e nunca propaga).
    assert len({item.event_id for item in snapshot.operational}) == 5


def test_snapshot_operacional_e_versionado_estavel_e_ordenado():
    _seed_module_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(
            name="Loja Provisionada",
            slug="loja-provisionada",
        ),
    )
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque"},
    )
    provisioning = ProvisioningControl(SessionLocal)

    snapshot = provisioning.snapshot(StoreRef(id=store.id))
    repeated = provisioning.snapshot(StoreRef(id=store.id))

    assert repeated == snapshot
    assert snapshot.schema_version == 1
    assert tuple(item.aggregate for item in snapshot.operational) == (
        "loja",
        "whatsapp_modo",
        "vendas",
        "estoque",
    )
    assert tuple(item.schema_version for item in snapshot.operational) == (1, 1, 1, 1)
    assert tuple(item.loja_id for item in snapshot.operational) == (
        store.id,
        store.id,
        store.id,
        store.id,
    )
    assert tuple(item.version for item in snapshot.operational) == (1, 1, 1, 1)
    assert tuple(item.state for item in snapshot.operational) == (
        "rascunho",
        "1",
        "ativo",
        "ativo",
    )
    assert len({item.event_id for item in snapshot.operational}) == 4
    assert all(item.event_id for item in snapshot.operational)
    assert all(isinstance(item.effective_at, datetime) for item in snapshot.operational)
    assert all(isinstance(item.occurred_at, datetime) for item in snapshot.operational)
    assert tuple(item.reason for item in snapshot.operational) == (None, None, None, None)
    assert snapshot.people == ()
    assert snapshot.roles == ()
    with pytest.raises(FrozenInstanceError):
        snapshot.operational[0].state = "ativa"


def test_snapshot_inclui_pessoas_e_cargos_ativos_ordenados():
    _seed_module_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Identidade", slug="loja-identidade"),
    )
    people = PeopleDirectory(SessionLocal)
    owner = people.register(
        admin,
        RegisterPerson(name="Dono Ativo", email="dono.ativo@example.com"),
    )
    manager = people.register(
        admin,
        RegisterPerson(name="Gerente Ativo", email="gerente.ativo@example.com"),
    )
    roles = StoreRoles(SessionLocal)
    owner_role = roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=owner.id),
            role=StoreRole.OWNER,
        ),
    )
    manager_role = roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=manager.id),
            role=StoreRole.MANAGER,
        ),
    )
    provisioning = ProvisioningControl(SessionLocal)

    snapshot = provisioning.snapshot(StoreRef(id=store.id))
    repeated = provisioning.snapshot(StoreRef(id=store.id))

    assert repeated == snapshot
    assert tuple(
        (person.person_id, person.email, person.name)
        for person in snapshot.people
    ) == (
        (owner.id, "dono.ativo@example.com", "Dono Ativo"),
        (manager.id, "gerente.ativo@example.com", "Gerente Ativo"),
    )
    assert tuple(
        (
            role.assignment_id,
            role.person_id,
            role.role,
            role.state,
            role.ended_at,
        )
        for role in snapshot.roles
    ) == (
        (owner_role.id, owner.id, "dono", "ativo", None),
        (manager_role.id, manager.id, "gerente", "ativo", None),
    )


def test_snapshot_de_loja_legada_sem_auditoria_tem_evento_estavel():
    momento = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add(
            Loja(
                id="loja-legada",
                slug="loja-legada",
                nome="Loja Legada",
                status="ativa",
                versao=7,
                criada_em=momento,
                atualizada_em=momento,
            )
        )
        db.commit()
    provisioning = ProvisioningControl(SessionLocal)

    snapshot = provisioning.snapshot(StoreRef(id="loja-legada"))
    repeated = provisioning.snapshot(StoreRef(id="loja-legada"))

    assert repeated == snapshot
    assert len(snapshot.operational) == 2
    envelope = snapshot.operational[0]
    assert (
        envelope.schema_version,
        envelope.loja_id,
        envelope.aggregate,
        envelope.version,
        envelope.state,
    ) == (
        1,
        "loja-legada",
        "loja",
        7,
        "ativa",
    )
    assert envelope.event_id
    assert envelope.occurred_at == envelope.effective_at
    assert envelope.reason is None
    assert snapshot.people == ()
    assert snapshot.roles == ()
