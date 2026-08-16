from __future__ import annotations

from app.control.delivery import (
    DurableProvisioningDelivery,
    InMemoryProvisioningDelivery,
    ProvisioningPublisher,
)
from app.control.people import PeopleDirectory
from app.control.portfolio import PortfolioControl
from app.control.provisioning import ProvisioningControl
from app.control.provisioning_outbox import (
    enqueue_delivery,
    process_pending,
    snapshot_to_payload,
)
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
from app.models import ControlProvisioningOutbox, GestorRevy, ModuloRevy


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


def _store_with_snapshot(admin: Actor) -> tuple[str, str]:
    _seed_modules()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Outbox", slug="loja-outbox"),
    )
    person = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(name="Dono Outbox", email="dono.outbox@example.com"),
    )
    StoreRoles(SessionLocal).assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque"},
    )
    return store.id, store.slug


def test_enqueue_e_idempotente_para_mesmo_event_id():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    with SessionLocal() as db:
        before = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.destination == "chatbot",
            )
            .count()
        )
        first = enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="chatbot",
            snapshot=snapshot,
        )
        db.commit()
        first_id = first.id
        second = enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="chatbot",
            snapshot=snapshot,
        )
        db.commit()
        assert second.id == first_id
        after = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.destination == "chatbot",
            )
            .count()
        )
        # Hooks já podem ter enfileirado o mesmo snapshot; re-enqueue não cria linha.
        assert after == max(before, 1)
        assert after == before or before == 0


def test_process_pending_chama_poster_e_marca_delivered():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    with SessionLocal() as db:
        enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="estoque",
            snapshot=snapshot,
        )
        db.commit()

    posted: list[tuple[str, dict]] = []

    def poster(destination: str, payload: dict) -> None:
        posted.append((destination, payload))

    with SessionLocal() as db:
        delivered = process_pending(db, poster, limit=20)
        db.commit()
        rows = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.destination == "estoque",
            )
            .all()
        )
        assert delivered >= 1
        assert rows
        assert all(row.status == "delivered" for row in rows)
        assert all(row.attempts >= 1 for row in rows)
        assert all(row.last_error is None for row in rows)

    assert any(destination == "estoque" for destination, _ in posted)
    assert any(payload["loja_slug"] == store_slug for _, payload in posted)


def test_process_pending_falha_marca_failed_e_incrementa_attempts():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    with SessionLocal() as db:
        # destino isolado para não colidir com hooks chatbot
        enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="motor",
            snapshot=snapshot,
        )
        db.commit()

    def failing_poster(destination: str, payload: dict) -> None:
        if destination == "motor":
            raise RuntimeError("destino indisponivel")

    with SessionLocal() as db:
        delivered = process_pending(db, failing_poster, limit=20)
        db.commit()
        row = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.destination == "motor",
            )
            .one()
        )
        assert row.status == "failed"
        assert row.attempts == 1
        assert "RuntimeError" in (row.last_error or "")
        assert "destino indisponivel" in (row.last_error or "")
        # outras filas chatbot dos hooks podem ter sido entregues
        assert delivered >= 0


def test_process_pending_retenta_failed_e_marca_delivered():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    with SessionLocal() as db:
        row = enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="motor-retry",
            snapshot=snapshot,
        )
        row.status = "failed"
        row.attempts = 1
        row.last_error = "RuntimeError: falha anterior"
        db.commit()
        row_id = row.id

    with SessionLocal() as db:
        delivered = process_pending(db, lambda d, p: None, limit=20)
        db.commit()
        row = db.query(ControlProvisioningOutbox).filter_by(id=row_id).one()
        assert delivered >= 1
        assert row.status == "delivered"
        assert row.attempts == 2
        assert row.last_error is None


def test_process_pending_nao_retenta_failed_no_max_attempts():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    with SessionLocal() as db:
        row = enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="motor-exhausted",
            snapshot=snapshot,
        )
        row.status = "failed"
        row.attempts = 5
        row.last_error = "RuntimeError: esgotado"
        db.commit()
        row_id = row.id
        attempts_before = row.attempts

    posted: list[str] = []

    def poster(destination: str, payload: dict) -> None:
        posted.append(destination)

    with SessionLocal() as db:
        process_pending(db, poster, limit=20, max_attempts=5)
        db.commit()
        row = db.query(ControlProvisioningOutbox).filter_by(id=row_id).one()
        assert row.status == "failed"
        assert row.attempts == attempts_before
        assert "motor-exhausted" not in posted


def test_process_pending_prioriza_pending_sobre_failed():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    with SessionLocal() as db:
        failed = enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="motor-order-failed",
            snapshot=snapshot,
        )
        failed.status = "failed"
        failed.attempts = 1
        db.flush()
        enqueue_delivery(
            db,
            loja_id=store_id,
            loja_slug=store_slug,
            destination="motor-order-pending",
            snapshot=snapshot,
        )
        db.commit()

    order: list[str] = []

    def poster(destination: str, payload: dict) -> None:
        if destination.startswith("motor-order-"):
            order.append(destination)

    with SessionLocal() as db:
        process_pending(db, poster, limit=20)
        db.commit()

    assert "motor-order-pending" in order
    assert "motor-order-failed" in order
    assert order.index("motor-order-pending") < order.index("motor-order-failed")


def test_payload_inclui_loja_slug_e_agregados_operacionais():
    admin = _admin_actor()
    store_id, store_slug = _store_with_snapshot(admin)
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=store_id))

    payload = snapshot_to_payload(snapshot, loja_slug=store_slug)

    assert payload["schema_version"] == 1
    assert payload["loja_id"] == store_id
    assert payload["loja_slug"] == store_slug
    aggregates = [item["aggregate"] for item in payload["operational"]]
    assert aggregates == ["loja", "whatsapp_modo", "vendas", "estoque"]
    assert all("version" in item for item in payload["operational"])
    assert all(
        isinstance(item["effective_at"], str) and "T" in item["effective_at"]
        for item in payload["operational"]
    )
    assert all(
        isinstance(item["occurred_at"], str) and "T" in item["occurred_at"]
        for item in payload["operational"]
    )
    assert payload["people"]
    assert payload["people"][0]["email"] == "dono.outbox@example.com"
    assert any(role["role"] == "dono" for role in payload["roles"])


def test_durable_delivery_enfileira_via_porta():
    admin = _admin_actor()
    store_id, _ = _store_with_snapshot(admin)
    delivery = DurableProvisioningDelivery(SessionLocal)
    publisher = ProvisioningPublisher(
        SessionLocal,
        delivery=delivery,
        targets=("chatbot",),
    )

    publisher.publish(StoreRef(id=store_id))

    with SessionLocal() as db:
        rows = (
            db.query(ControlProvisioningOutbox)
            .filter(
                ControlProvisioningOutbox.loja_id == store_id,
                ControlProvisioningOutbox.destination == "chatbot",
            )
            .all()
        )
        assert len(rows) >= 1
        assert all(row.status == "pending" for row in rows)


def test_publisher_com_outbox_session_enfileira_e_mantem_inmemory():
    admin = _admin_actor()
    store_id, _ = _store_with_snapshot(admin)
    memory = InMemoryProvisioningDelivery()
    publisher = ProvisioningPublisher(
        SessionLocal,
        delivery=memory,
        targets=("chatbot", "estoque"),
        outbox_session_factory=SessionLocal,
    )

    snapshot = publisher.publish(StoreRef(id=store_id))

    assert len(memory.deliveries) == 2
    assert all(item is snapshot for _, item in memory.deliveries)
    with SessionLocal() as db:
        destinations = {
            row.destination
            for row in db.query(ControlProvisioningOutbox)
            .filter(ControlProvisioningOutbox.loja_id == store_id)
            .all()
        }
        assert "chatbot" in destinations
        assert "estoque" in destinations
