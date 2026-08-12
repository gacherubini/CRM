import pytest

from app.control.access import AccessControl
from app.control.audit import AuditTrail
from app.control.portfolio import (
    InvalidModuleSelection,
    ModuleCode,
    ModuleStatus,
    PortfolioConflict,
    PortfolioControl,
)
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


def _seed_catalog() -> None:
    with SessionLocal() as db:
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


def _manager_actor(email: str) -> Actor:
    with SessionLocal() as db:
        manager = GestorRevy(
            email=email,
            nome="Gestor Portfólio",
            senha_hash="hash-nao-usado",
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


def test_admin_configura_vendas_e_estoque_e_lista_portfolio():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Portfólio", slug="loja-portfolio-domain"),
    )
    portfolio = PortfolioControl(SessionLocal)

    configured = portfolio.configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque"},
    )
    listed = portfolio.list_modules(admin, StoreRef(id=store.id))

    assert configured == listed
    assert [
        (item.code, item.name, item.status, item.version)
        for item in configured
    ] == [
        (ModuleCode.INVENTORY, "Estoque", ModuleStatus.ACTIVE, 1),
        (ModuleCode.SALES, "Vendas", ModuleStatus.ACTIVE, 1),
    ]
    events = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=store.id),
    ).items
    assert [event.action for event in events] == [
        "store.created",
        "store_module.contracted",
        "store_module.contracted",
    ]
    assert events[1].after == {
        "code": "estoque",
        "status": "ativo",
        "version": 1,
    }


def test_admin_contrata_copiloto_junto_com_vendas_e_estoque():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Copiloto", slug="loja-copiloto-domain"),
    )
    portfolio = PortfolioControl(SessionLocal)

    configured = portfolio.configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque", "copiloto"},
    )

    by_code = {item.code: item for item in configured}
    assert by_code[ModuleCode.COPILOTO].status is ModuleStatus.ACTIVE
    assert by_code[ModuleCode.COPILOTO].name == "Copiloto de Vendas"
    assert set(by_code) == {
        ModuleCode.INVENTORY,
        ModuleCode.SALES,
        ModuleCode.COPILOTO,
    }


def test_reconfigurar_suspende_e_reativa_sem_apagar_historico():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Histórico", slug="loja-historico-modulos"),
    )
    portfolio = PortfolioControl(SessionLocal)
    portfolio.configure(admin, StoreRef(id=store.id), {"vendas", "estoque"})

    without_inventory = portfolio.configure(
        admin,
        StoreRef(id=store.id),
        {"vendas"},
    )
    restored = portfolio.configure(
        admin,
        StoreRef(id=store.id),
        {"vendas", "estoque"},
    )

    assert [
        (item.code, item.status, item.version) for item in without_inventory
    ] == [
        (ModuleCode.INVENTORY, ModuleStatus.SUSPENDED, 2),
        (ModuleCode.SALES, ModuleStatus.ACTIVE, 1),
    ]
    assert [
        (item.code, item.status, item.version) for item in restored
    ] == [
        (ModuleCode.INVENTORY, ModuleStatus.ACTIVE, 3),
        (ModuleCode.SALES, ModuleStatus.ACTIVE, 1),
    ]
    actions = [
        event.action
        for event in AuditTrail(SessionLocal)
        .list(admin, AuditQuery(store_id=store.id))
        .items
    ]
    assert actions == [
        "store.created",
        "store_module.contracted",
        "store_module.contracted",
        "store_module.suspended",
        "store_module.activated",
    ]


def test_gestor_lista_apenas_loja_vinculada_e_nao_pode_mutar_portfolio():
    _seed_catalog()
    admin = _admin_actor()
    manager = _manager_actor("gestor-portfolio@revy.local")
    linked_store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Vinculada", slug="loja-vinculada-portfolio"),
    )
    hidden_store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Oculta", slug="loja-oculta-portfolio"),
    )
    portfolio = PortfolioControl(SessionLocal)
    portfolio.configure(admin, StoreRef(id=linked_store.id), {"vendas"})
    AccessControl(SessionLocal).grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=linked_store.id),
            manager_id=manager.id,
            role=TrafficRole.RESPONSIBLE,
        ),
    )

    assert portfolio.list_modules(
        manager,
        StoreRef(id=linked_store.id),
    ) == portfolio.list_modules(admin, StoreRef(id=linked_store.id))
    with pytest.raises(StoreNotFound):
        portfolio.list_modules(manager, StoreRef(id=hidden_store.id))
    with pytest.raises(AccessDenied):
        portfolio.configure(manager, StoreRef(id=linked_store.id), {"vendas"})
    with pytest.raises(AccessDenied):
        portfolio.suspend(manager, StoreRef(id=linked_store.id), "vendas")
    with pytest.raises(AccessDenied):
        portfolio.activate(manager, StoreRef(id=linked_store.id), "vendas")


def test_admin_suspende_e_reativa_modulo_com_versao_e_auditoria():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Transições", slug="loja-transicoes-modulos"),
    )
    portfolio = PortfolioControl(SessionLocal)
    portfolio.configure(admin, StoreRef(id=store.id), {"vendas"})

    suspended = portfolio.suspend(
        admin,
        StoreRef(id=store.id),
        "vendas",
        reason="pausa operacional",
    )
    with pytest.raises(PortfolioConflict):
        portfolio.suspend(admin, StoreRef(id=store.id), "vendas")
    activated = portfolio.activate(
        admin,
        StoreRef(id=store.id),
        "vendas",
        reason="operação normalizada",
    )
    with pytest.raises(PortfolioConflict):
        portfolio.activate(admin, StoreRef(id=store.id), "vendas")
    with pytest.raises(PortfolioConflict):
        portfolio.suspend(admin, StoreRef(id=store.id), "estoque")

    assert (suspended.code, suspended.status, suspended.version) == (
        ModuleCode.SALES,
        ModuleStatus.SUSPENDED,
        2,
    )
    assert (activated.code, activated.status, activated.version) == (
        ModuleCode.SALES,
        ModuleStatus.ACTIVE,
        3,
    )
    events = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=store.id),
    ).items
    assert [event.action for event in events] == [
        "store.created",
        "store_module.contracted",
        "store_module.suspended",
        "store_module.activated",
    ]
    assert [event.reason for event in events[-2:]] == [
        "pausa operacional",
        "operação normalizada",
    ]


def test_configuracao_rejeita_selecao_vazia_ou_fora_do_catalogo():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Catálogo", slug="loja-catalogo-modulos"),
    )
    portfolio = PortfolioControl(SessionLocal)

    with pytest.raises(InvalidModuleSelection):
        portfolio.configure(admin, StoreRef(id=store.id), set())
    with pytest.raises(InvalidModuleSelection):
        portfolio.configure(
            admin,
            StoreRef(id=store.id),
            ("vendas", "financeiro"),
        )

    assert portfolio.list_modules(admin, StoreRef(id=store.id)) == ()
    actions = [
        event.action
        for event in AuditTrail(SessionLocal)
        .list(admin, AuditQuery(store_id=store.id))
        .items
    ]
    assert actions == ["store.created"]
