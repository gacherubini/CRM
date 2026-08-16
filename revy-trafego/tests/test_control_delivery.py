from app.control.delivery import (
    InMemoryProvisioningDelivery,
    ProvisioningPublisher,
    apply_snapshot,
    allows_processing,
)
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
    StoreStatus,
    TransitionStore,
)
from app.db import SessionLocal
from app.models import AcessoControl, GestorRevy, ModuloRevy, agora


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _seed_modules() -> None:
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


def _grant_owner_access(person_id: str) -> None:
    now = agora()
    with SessionLocal() as db:
        db.add(
            AcessoControl(
                pessoa_id=person_id,
                papel="gestor",
                estado="pendente",
                senha_hash=None,
                sessao_versao=1,
                gestor_legado_id=None,
                criada_em=now,
                atualizada_em=now,
            )
        )
        db.commit()


def _store_ready_with_modules(admin: Actor) -> str:
    _seed_modules()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Entrega", slug="loja-entrega"),
    )
    person = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(name="Dono Entrega", email="dono.entrega@example.com"),
    )
    StoreRoles(SessionLocal).assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    _grant_owner_access(person.id)
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque"},
    )
    for target in (StoreStatus.CONFIGURING, StoreStatus.READY, StoreStatus.ACTIVE):
        stores.transition(
            admin,
            TransitionStore(store=StoreRef(id=store.id), target=target),
        )
    return store.id


def test_publisher_entrega_snapshot_a_todos_os_destinos():
    admin = _admin_actor()
    store_id = _store_ready_with_modules(admin)
    delivery = InMemoryProvisioningDelivery()
    publisher = ProvisioningPublisher(
        SessionLocal,
        delivery=delivery,
        targets=("chatbot", "estoque"),
    )

    snapshot = publisher.publish(StoreRef(id=store_id))

    assert len(delivery.deliveries) == 2
    assert {target for target, _ in delivery.deliveries} == {"chatbot", "estoque"}
    assert all(item is snapshot for _, item in delivery.deliveries)
    assert tuple(item.aggregate for item in snapshot.operational)[:1] == ("loja",)
    assert snapshot.people[0].email == "dono.entrega@example.com"
    assert any(role.role == "dono" for role in snapshot.roles)


def test_apply_rejeita_versao_antiga_e_e_idempotente():
    admin = _admin_actor()
    store_id = _store_ready_with_modules(admin)
    control = ProvisioningControl(SessionLocal)
    stores = StoreControl(SessionLocal)

    active = control.snapshot(StoreRef(id=store_id))
    applied, reasons = apply_snapshot(None, active)
    assert reasons == ["applied", "applied", "applied", "applied"]
    assert allows_processing(applied) is True
    assert allows_processing(applied, module="vendas") is True

    same, same_reasons = apply_snapshot(applied, active)
    assert same_reasons == ["idempotent", "idempotent", "idempotent", "idempotent"]
    assert same == applied

    stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store_id),
            target=StoreStatus.SUSPENDED,
            reason="manutencao",
        ),
    )
    suspended = control.snapshot(StoreRef(id=store_id))
    after_suspend, suspend_reasons = apply_snapshot(applied, suspended)
    assert "applied" in suspend_reasons
    assert allows_processing(after_suspend) is False
    assert allows_processing(after_suspend, module="vendas") is False

    stale, stale_reasons = apply_snapshot(after_suspend, active)
    assert stale_reasons == ["stale", "stale", "idempotent", "idempotent"]
    assert allows_processing(stale) is False
    loja = stale.aggregates["loja"]
    assert loja.state == "suspensa"
    assert loja.version == after_suspend.aggregates["loja"].version


def test_modulo_suspenso_bloqueia_so_o_modulo():
    admin = _admin_actor()
    store_id = _store_ready_with_modules(admin)
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store_id),
        {"estoque"},
    )
    # configure with only estoque suspends vendas by leaving it out? Check portfolio behavior
    # Actually configure with selected set - vendas not selected might suspend or remove.
    # Read portfolio - if not in selected and assignment exists and active, it suspends.

    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))
    projection, _ = apply_snapshot(None, snapshot)

    assert allows_processing(projection) is True
    assert allows_processing(projection, module="estoque") is True
    assert allows_processing(projection, module="vendas") is False
