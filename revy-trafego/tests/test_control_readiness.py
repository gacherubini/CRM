from datetime import date
from decimal import Decimal

import pytest

from app.control.contracts import (
    ContractBillingStatus,
    ContractControl,
    UpsertContract,
)
from app.control.people import PeopleDirectory
from app.control.portfolio import PortfolioControl
from app.control.readiness import StoreReadiness
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.types import (
    Actor,
    AssignStoreRole,
    CreateStore,
    PersonRef,
    RegisterPerson,
    StoreReadinessBlocked,
    StoreRef,
    StoreRole,
    StoreStatus,
    TransitionStore,
)
from app.db import SessionLocal
from app.models import AcessoControl, GestorRevy, ModuloRevy, agora


def _seed_catalog() -> None:
    with SessionLocal() as db:
        if db.query(ModuloRevy).count() == 0:
            db.add_all(
                [
                    ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                    ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                ]
            )
            db.commit()


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


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


def _create_owner(admin: Actor, store_id: str, *, slug: str):
    person = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(
            name=f"Dono {slug}",
            email=f"{slug}.dono@example.com",
        ),
    )
    StoreRoles(SessionLocal).assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store_id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    return person


def _checks_by_code(report):
    return {check.code: check for check in report.checks}


def test_rascunho_sem_dono_e_modulos_nao_esta_pronta():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Rascunho", slug="loja-readiness-draft"),
    )
    readiness = StoreReadiness(SessionLocal)

    report = readiness.evaluate(admin, StoreRef(id=store.id))
    again = readiness.evaluate(admin, StoreRef(id=store.id))

    assert report.ready is False
    assert report.store_id == store.id
    assert report.status is StoreStatus.DRAFT
    assert [check.code for check in report.checks] == [
        "active_owner",
        "activatable_owner",
        "module_selected",
        "contract_present",
    ]
    by_code = _checks_by_code(report)
    assert by_code["active_owner"].ok is False
    assert by_code["active_owner"].severity == "required"
    assert by_code["activatable_owner"].ok is False
    assert by_code["activatable_owner"].severity == "required"
    assert by_code["module_selected"].ok is False
    assert by_code["module_selected"].severity == "required"
    assert by_code["contract_present"].ok is False
    assert by_code["contract_present"].severity == "alert"
    # Determinismo: mesma entrada → mesmo relatório estrutural.
    assert again.ready is report.ready
    assert [c.code for c in again.checks] == [c.code for c in report.checks]
    assert [c.ok for c in again.checks] == [c.ok for c in report.checks]
    assert [c.severity for c in again.checks] == [
        c.severity for c in report.checks
    ]


def test_dono_ativavel_e_modulos_deixam_loja_pronta():
    _seed_catalog()
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Pronta", slug="loja-readiness-ready"),
    )
    owner = _create_owner(admin, store.id, slug="loja-readiness-ready")
    _grant_activatable_access(owner.id)
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas"},
    )
    readiness = StoreReadiness(SessionLocal)

    report = readiness.evaluate(admin, StoreRef(id=store.id))

    assert report.ready is True
    by_code = _checks_by_code(report)
    assert by_code["active_owner"].ok is True
    assert by_code["activatable_owner"].ok is True
    assert by_code["module_selected"].ok is True
    assert by_code["contract_present"].ok is False
    assert by_code["contract_present"].severity == "alert"


def test_somente_contrato_ausente_gera_alerta_e_mantem_pronta():
    _seed_catalog()
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Alerta Contrato", slug="loja-readiness-alert"),
    )
    owner = _create_owner(admin, store.id, slug="loja-readiness-alert")
    _grant_activatable_access(owner.id)
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"estoque"},
    )
    readiness = StoreReadiness(SessionLocal)

    without_contract = readiness.evaluate(admin, StoreRef(id=store.id))
    assert without_contract.ready is True
    assert _checks_by_code(without_contract)["contract_present"].ok is False
    assert _checks_by_code(without_contract)["contract_present"].severity == "alert"

    ContractControl(SessionLocal).upsert(
        admin,
        UpsertContract(
            store=StoreRef(id=store.id),
            monthly_amount=Decimal("199.90"),
            starts_on=date(2026, 1, 1),
            ends_on=None,
            due_day=10,
            billing_status=ContractBillingStatus.CURRENT,
        ),
    )
    with_contract = readiness.evaluate(admin, StoreRef(id=store.id))
    assert with_contract.ready is True
    assert _checks_by_code(with_contract)["contract_present"].ok is True


def test_transicao_para_pronta_bloqueada_quando_nao_ready():
    _seed_catalog()
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Bloqueada", slug="loja-readiness-block"),
    )
    stores.transition(
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

    assert error.value.store_id == store.id
    assert error.value.requirement == "active_owner"
    assert stores.get(admin, StoreRef(id=store.id)).status is StoreStatus.CONFIGURING

    owner = _create_owner(admin, store.id, slug="loja-readiness-block")
    _grant_activatable_access(owner.id)

    with pytest.raises(StoreReadinessBlocked) as modules_error:
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=StoreStatus.READY,
            ),
        )

    assert modules_error.value.requirement == "module_selected"

    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque"},
    )
    ready = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.READY,
        ),
    )
    assert ready.status is StoreStatus.READY
