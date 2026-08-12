from datetime import date
from decimal import Decimal

import pytest

from app.control.audit import AuditTrail
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
    AccessDenied,
    Actor,
    AssignStoreRole,
    AuditQuery,
    CreateStore,
    InvalidAlertAcceptance,
    PersonRef,
    RegisterPerson,
    StoreReadinessBlocked,
    StoreRef,
    StoreRole,
    StoreStatus,
    TransitionStore,
)
from app.db import SessionLocal
from app.models import AcessoControl, AuditoriaEvento, GestorRevy, ModuloRevy, agora


def _seed_catalog() -> None:
    with SessionLocal() as db:
        if db.query(ModuloRevy).count() == 0:
            db.add_all(
                [
                    ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                    ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                    ModuloRevy(id="copiloto", codigo="copiloto", nome="Copiloto de Vendas"),
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
    assert by_code["activatable_owner"].severity == "alert"
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


def test_alerta_aceito_audita_e_nao_inventa_ready():
    """Aceite de alerta gera auditoria e não contorna checks required."""
    _seed_catalog()
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Aceite Alerta", slug="loja-aceite-alerta"),
    )
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"estoque"},
    )
    readiness = StoreReadiness(SessionLocal)

    before = readiness.evaluate(admin, StoreRef(id=store.id))
    assert before.ready is False
    assert _checks_by_code(before)["contract_present"].ok is False
    assert _checks_by_code(before)["contract_present"].severity == "alert"
    assert _checks_by_code(before)["contract_present"].accepted is False

    acceptance = readiness.accept_alert(
        admin,
        StoreRef(id=store.id),
        "contract_present",
        "piloto comercial sem contrato formal ainda",
    )
    assert acceptance.check_code == "contract_present"
    assert "piloto" in acceptance.reason

    after = readiness.evaluate(admin, StoreRef(id=store.id))
    # Aceite não inventa ready se required (dono/módulos) ainda falham.
    assert after.ready is False
    assert _checks_by_code(after)["contract_present"].accepted is True
    assert _checks_by_code(after)["active_owner"].ok is False

    with SessionLocal() as db:
        events = (
            db.query(AuditoriaEvento)
            .filter(
                AuditoriaEvento.loja_id == store.id,
                AuditoriaEvento.acao == "readiness.alert.accepted",
            )
            .all()
        )
        assert len(events) == 1
        assert events[0].motivo == "piloto comercial sem contrato formal ainda"
        assert events[0].recurso_id == "contract_present"

    trail = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=store.id, limit=50),
    )
    assert "readiness.alert.accepted" in [e.action for e in trail.items]


def test_nao_aceita_check_required_nem_motivo_vazio():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Aceite Inválido", slug="loja-aceite-invalido"),
    )
    readiness = StoreReadiness(SessionLocal)

    with pytest.raises(InvalidAlertAcceptance):
        readiness.accept_alert(
            admin,
            StoreRef(id=store.id),
            "active_owner",
            "tentativa de contornar dono",
        )

    with pytest.raises(InvalidAlertAcceptance):
        readiness.accept_alert(
            admin,
            StoreRef(id=store.id),
            "contract_present",
            "   ",
        )


def test_colaborador_nao_aceita_alerta():
    from app.auth import hash_senha
    from app.models import Loja, VinculoTrafego

    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Colab Alerta", slug="loja-colab-alerta"),
    )
    with SessionLocal() as db:
        collab = GestorRevy(
            email="colab.alerta@revy.local",
            nome="Colab Alerta",
            senha_hash=hash_senha("senha-colab"),
            papel="gestor",
            ativo=True,
        )
        db.add(collab)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=store.id,
                gestor_id=collab.id,
                tipo="colaborador",
            )
        )
        db.commit()
        collab_actor = Actor(
            id=collab.id,
            email=collab.email,
            name=collab.nome,
            role=collab.papel,
        )

    with pytest.raises(AccessDenied):
        StoreReadiness(SessionLocal).accept_alert(
            collab_actor,
            StoreRef(id=store.id),
            "contract_present",
            "colaborador não pode",
        )


def test_transicao_para_ativa_bloqueada_sem_required():
    """Ativação (pronta→ativa) revalida checks required."""
    _seed_catalog()
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(
        admin,
        CreateStore(name="Loja Ativação", slug="loja-ativacao-block"),
    )
    owner = _create_owner(admin, store.id, slug="loja-ativacao-block")
    _grant_activatable_access(owner.id)
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas"},
    )
    stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.CONFIGURING,
        ),
    )
    stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.READY,
        ),
    )

    # Suspender módulo deixa ready=False; ativação deve bloquear.
    PortfolioControl(SessionLocal).suspend(
        admin,
        StoreRef(id=store.id),
        "vendas",
        reason="teste bloqueio ativação",
    )
    report = StoreReadiness(SessionLocal).evaluate(admin, StoreRef(id=store.id))
    assert report.ready is False

    with pytest.raises(StoreReadinessBlocked) as error:
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=StoreStatus.ACTIVE,
            ),
        )

    assert error.value.requirement == "module_selected"
    assert stores.get(admin, StoreRef(id=store.id)).status is StoreStatus.READY

    # Restaura módulo e ativa com sucesso.
    PortfolioControl(SessionLocal).activate(
        admin,
        StoreRef(id=store.id),
        "vendas",
        reason="restaurar para ativar",
    )
    active = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.ACTIVE,
        ),
    )
    assert active.status is StoreStatus.ACTIVE
