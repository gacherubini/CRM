from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.auth import hash_senha
from app.control.access import AccessControl
from app.control.audit import AuditTrail
from app.control.contracts import (
    ContractBillingStatus,
    ContractControl,
    UpsertContract,
)
from app.control.portfolio import PortfolioControl
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    AuditQuery,
    CreateStore,
    GrantTrafficAccess,
    StoreNotFound,
    StoreRef,
    TrafficRole,
)
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


def _manager_actor() -> Actor:
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.contratos@example.com",
            nome="Gestor de Contratos",
            senha_hash=hash_senha("senha-gestor-contratos"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()
        return Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )


def _seed_module_catalog() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                ModuloRevy(id="copiloto", codigo="copiloto", nome="Copiloto de Vendas"),
            ]
        )
        db.commit()


def test_admin_cria_e_consulta_contrato_auditado_da_loja():
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Contratada", slug="loja-contratada"),
    )
    contracts = ContractControl(SessionLocal)

    created = contracts.upsert(
        admin,
        UpsertContract(
            store=StoreRef(id=store.id),
            monthly_amount=Decimal("1299.90"),
            starts_on=date(2026, 8, 1),
            ends_on=None,
            due_day=12,
            billing_status=ContractBillingStatus.CURRENT,
        ),
    )

    assert created.store_id == store.id
    assert created.monthly_amount == Decimal("1299.90")
    assert created.currency == "BRL"
    assert created.starts_on == date(2026, 8, 1)
    assert created.ends_on is None
    assert created.due_day == 12
    assert created.billing_status is ContractBillingStatus.CURRENT
    assert contracts.get(admin, StoreRef(id=store.id)) == created

    audit = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=store.id),
    )
    assert audit.items[-1].action == "store_contract.upserted"
    assert audit.items[-1].before is None
    assert audit.items[-1].after == {
        "billing_status": "em_dia",
        "currency": "BRL",
        "due_day": 12,
        "ends_on": None,
        "monthly_amount": "1299.90",
        "starts_on": "2026-08-01",
    }


def test_somente_admin_pode_gravar_contrato():
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Contrato Protegido", slug="loja-contrato-protegido"),
    )
    manager = Actor(
        id="gestor-sem-autoridade-contratual",
        email="gestor.contrato@example.com",
        name="Gestor Contrato",
        role="gestor",
    )

    with pytest.raises(AccessDenied):
        ContractControl(SessionLocal).upsert(
            manager,
            UpsertContract(
                store=StoreRef(id=store.id),
                monthly_amount=Decimal("499.00"),
                starts_on=date(2026, 8, 1),
                ends_on=None,
                due_day=5,
                billing_status=ContractBillingStatus.CURRENT,
            ),
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("monthly_amount", Decimal("-0.01")),
        ("ends_on", date(2026, 7, 31)),
        ("due_day", 0),
        ("due_day", 32),
    ],
)
def test_contrato_rejeita_valor_vigencia_e_vencimento_invalidos(
    field,
    invalid_value,
):
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Contrato Inválido", slug="loja-contrato-invalido"),
    )
    valid = UpsertContract(
        store=StoreRef(id=store.id),
        monthly_amount=Decimal("100.00"),
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
        due_day=10,
        billing_status=ContractBillingStatus.CURRENT,
    )

    with pytest.raises(ValueError):
        ContractControl(SessionLocal).upsert(
            admin,
            replace(valid, **{field: invalid_value}),
        )


def test_gestor_le_contrato_somente_da_loja_com_vinculo_ativo():
    admin = _admin_actor()
    manager = _manager_actor()
    stores = StoreControl(SessionLocal)
    allowed = stores.create(
        admin,
        CreateStore(name="Loja Contrato Permitido", slug="loja-contrato-permitido"),
    )
    hidden = stores.create(
        admin,
        CreateStore(name="Loja Contrato Oculto", slug="loja-contrato-oculto"),
    )
    AccessControl(SessionLocal).grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=allowed.id),
            manager_id=manager.id,
            role=TrafficRole.COLLABORATOR,
        ),
    )
    contracts = ContractControl(SessionLocal)
    for store in (allowed, hidden):
        contracts.upsert(
            admin,
            UpsertContract(
                store=StoreRef(id=store.id),
                monthly_amount=Decimal("750.00"),
                starts_on=date(2026, 8, 1),
                ends_on=None,
                due_day=15,
                billing_status=ContractBillingStatus.CURRENT,
            ),
        )

    assert contracts.get(manager, StoreRef(id=allowed.id)).store_id == allowed.id
    with pytest.raises(StoreNotFound):
        contracts.get(manager, StoreRef(id=hidden.id))
    assert contracts.get(admin, StoreRef(id=hidden.id)).store_id == hidden.id


def test_upsert_atrasado_atualiza_mesmo_contrato_sem_mudar_loja_ou_modulos():
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Cobrança Atrasada", slug="loja-cobranca-atrasada"),
    )
    store_ref = StoreRef(id=store.id)
    _seed_module_catalog()
    portfolio = PortfolioControl(SessionLocal)
    modules_before = portfolio.configure(
        admin,
        store_ref,
        ("vendas", "estoque"),
    )
    store_before = stores.get(admin, store_ref)
    contracts = ContractControl(SessionLocal)
    first = contracts.upsert(
        admin,
        UpsertContract(
            store=store_ref,
            monthly_amount=Decimal("950.00"),
            starts_on=date(2026, 8, 1),
            ends_on=None,
            due_day=10,
            billing_status=ContractBillingStatus.CURRENT,
        ),
    )

    updated = contracts.upsert(
        admin,
        UpsertContract(
            store=store_ref,
            monthly_amount=Decimal("975.00"),
            starts_on=date(2026, 8, 1),
            ends_on=date(2027, 7, 31),
            due_day=20,
            billing_status=ContractBillingStatus.OVERDUE,
        ),
    )

    assert updated.id == first.id
    assert updated.created_at == first.created_at
    assert updated.billing_status is ContractBillingStatus.OVERDUE
    assert stores.get(admin, store_ref) == store_before
    assert portfolio.list_modules(admin, store_ref) == modules_before

    audit = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=store.id),
    )
    assert audit.items[-1].action == "store_contract.upserted"
    assert audit.items[-1].resource_id == first.id
    assert audit.items[-1].before == {
        "billing_status": "em_dia",
        "currency": "BRL",
        "due_day": 10,
        "ends_on": None,
        "monthly_amount": "950.00",
        "starts_on": "2026-08-01",
    }
    assert audit.items[-1].after == {
        "billing_status": "atrasada",
        "currency": "BRL",
        "due_day": 20,
        "ends_on": "2027-07-31",
        "monthly_amount": "975.00",
        "starts_on": "2026-08-01",
    }
