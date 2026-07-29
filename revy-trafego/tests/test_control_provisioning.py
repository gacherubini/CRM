from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from app.control.portfolio import PortfolioControl
from app.control.provisioning import ProvisioningControl
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, ModuloRevy


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
            ]
        )
        db.commit()


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
    assert tuple(item.aggregate for item in snapshot) == (
        "loja",
        "vendas",
        "estoque",
    )
    assert tuple(item.schema_version for item in snapshot) == (1, 1, 1)
    assert tuple(item.loja_id for item in snapshot) == (
        store.id,
        store.id,
        store.id,
    )
    assert tuple(item.version for item in snapshot) == (1, 1, 1)
    assert tuple(item.state for item in snapshot) == (
        "rascunho",
        "ativo",
        "ativo",
    )
    assert len({item.event_id for item in snapshot}) == 3
    assert all(item.event_id for item in snapshot)
    assert all(isinstance(item.effective_at, datetime) for item in snapshot)
    assert all(isinstance(item.occurred_at, datetime) for item in snapshot)
    assert tuple(item.reason for item in snapshot) == (None, None, None)
    with pytest.raises(FrozenInstanceError):
        snapshot[0].state = "ativa"
