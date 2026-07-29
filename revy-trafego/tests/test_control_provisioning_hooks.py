from app.control.people import PeopleDirectory
from app.control.portfolio import PortfolioControl
from app.control.provisioning_job import ProvisioningDeliveryWorker
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
from app.models import AcessoControl, ControlProvisioningOutbox, GestorRevy, ModuloRevy, agora


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


def _store_with_owner(admin: Actor) -> str:
    _seed_modules()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Hook", slug="loja-hook"),
    )
    person = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(name="Dono Hook", email="dono.hook@example.com"),
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
        {"vendas"},
    )
    return store.id


def test_transicao_de_loja_enfileira_outbox_para_chatbot():
    admin = _admin_actor()
    store_id = _store_with_owner(admin)
    stores = StoreControl(SessionLocal)

    with SessionLocal() as db:
        before = db.query(ControlProvisioningOutbox).count()

    stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store_id),
            target=StoreStatus.CONFIGURING,
        ),
    )

    with SessionLocal() as db:
        rows = (
            db.query(ControlProvisioningOutbox)
            .filter(ControlProvisioningOutbox.loja_id == store_id)
            .order_by(ControlProvisioningOutbox.created_at.desc())
            .all()
        )
        assert len(rows) > before or len(rows) >= 1
        destinations = {row.destination for row in rows}
        assert {
            "chatbot",
            "estoque",
            "portal",
            "motor",
            "catalogo",
        } <= destinations
        assert all(row.status == "pending" for row in rows)
        assert any(store_id in row.event_id for row in rows)
        assert any("loja-hook" in row.payload_json for row in rows)


def test_suspender_modulo_enfileira_nova_versao():
    admin = _admin_actor()
    store_id = _store_with_owner(admin)
    portfolio = PortfolioControl(SessionLocal)

    portfolio.suspend(admin, StoreRef(id=store_id), "vendas", reason="teste")

    with SessionLocal() as db:
        rows = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.destination == "chatbot",
            )
            .all()
        )
        assert any("vendas=" in row.event_id for row in rows)
        assert any(row.status == "pending" for row in rows)


def test_worker_run_once_entrega_pendentes_com_poster_injetavel():
    admin = _admin_actor()
    store_id = _store_with_owner(admin)
    StoreControl(SessionLocal).transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store_id),
            target=StoreStatus.CONFIGURING,
        ),
    )
    posted: list[tuple[str, dict]] = []

    def poster(destination: str, payload: dict) -> None:
        posted.append((destination, payload))

    worker = ProvisioningDeliveryWorker(
        db_factory=SessionLocal,
        poster=poster,
        enabled=True,
        interval_seconds=60,
        initial_delay_seconds=0,
    )
    result = worker.run_once()

    assert result["ok"] is True
    assert result["delivered"] >= 1
    assert posted
    assert {destination for destination, _ in posted} >= {
        "chatbot",
        "estoque",
        "portal",
        "motor",
        "catalogo",
    }
    assert all(payload["loja_slug"] == "loja-hook" for _, payload in posted)
    with SessionLocal() as db:
        remaining = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.status == "pending",
            )
            .count()
        )
        assert remaining == 0
