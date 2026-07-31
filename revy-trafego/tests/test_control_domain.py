import pytest

from app.control.access import AccessControl
from app.control.audit import AuditTrail
from app.control.people import PeopleDirectory
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.types import (
    ActiveResponsibleConflict,
    AccessDenied,
    Actor,
    AssignStoreRole,
    AuditQuery,
    CreateStore,
    GrantTrafficAccess,
    InvalidStoreSlug,
    InvalidStoreTransition,
    ManagerNotFound,
    PersonRef,
    RegisterPerson,
    RevokeTrafficAccess,
    StoreEditConflict,
    StoreRef,
    StoreNotFound,
    StoreReadinessBlocked,
    StoreRole,
    StoreStatus,
    TrafficRole,
    TransitionStore,
    UpdateStore,
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


def _manager_actor(email: str, *, active: bool = True) -> Actor:
    with SessionLocal() as db:
        manager = GestorRevy(
            email=email,
            nome=email.split("@", 1)[0].replace(".", " ").title(),
            senha_hash="hash-nao-usado-neste-teste",
            papel="gestor",
            ativo=active,
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


def _create_active_store(
    stores: StoreControl,
    admin: Actor,
    *,
    slug: str,
):
    from app.control.portfolio import PortfolioControl
    from app.models import AcessoControl, ModuloRevy, agora

    with SessionLocal() as db:
        if db.query(ModuloRevy).count() == 0:
            db.add_all(
                [
                    ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                    ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                ]
            )
            db.commit()

    store = stores.create(
        admin,
        CreateStore(name=f"Loja {slug}", slug=slug),
    )
    owner = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(
            name=f"Dono {slug}",
            email=f"dono.{slug}@example.com",
        ),
    )
    StoreRoles(SessionLocal).assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=owner.id),
            role=StoreRole.OWNER,
        ),
    )
    now = agora()
    with SessionLocal() as db:
        db.add(
            AcessoControl(
                pessoa_id=owner.id,
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
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas"},
    )
    for target in (
        StoreStatus.CONFIGURING,
        StoreStatus.READY,
        StoreStatus.ACTIVE,
    ):
        store = stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=target,
            ),
        )
    return store


def test_admin_cria_e_consulta_loja_em_rascunho():
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()

    created = stores.create(
        admin,
        CreateStore(name="Loja Centro", slug="loja-centro"),
    )
    retrieved = stores.get(admin, StoreRef(id=created.id))

    assert retrieved == created
    assert retrieved.name == "Loja Centro"
    assert retrieved.slug == "loja-centro"
    assert retrieved.status is StoreStatus.DRAFT
    assert retrieved.version == 1


@pytest.mark.parametrize(
    "slug",
    (
        "loja centro",
        "loja_centro",
        "loja-cêntro",
        "loja--centro",
    ),
)
def test_criar_loja_rejeita_slug_nao_canonico(slug):
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()

    with pytest.raises(InvalidStoreSlug) as error:
        stores.create(
            admin,
            CreateStore(name="Loja Centro", slug=slug),
        )

    assert error.value.slug == slug


def test_criar_loja_normaliza_espacos_externos_e_caixa_do_slug():
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()

    created = stores.create(
        admin,
        CreateStore(name="Loja Centro", slug="  Loja-Centro  "),
    )

    assert created.slug == "loja-centro"


def test_loja_rascunho_ativa_direto_mas_exige_prontidao():
    # Ativação em 1 clique: rascunho -> ativa é permitido como transição, mas
    # sem dono/módulo o gate de prontidão bloqueia e a loja segue em rascunho.
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja Norte", slug="loja-norte"),
    )

    with pytest.raises(StoreReadinessBlocked):
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=store.id),
                target=StoreStatus.ACTIVE,
            ),
        )

    assert stores.get(admin, StoreRef(id=store.id)).status is StoreStatus.DRAFT


def test_admin_concede_responsavel_e_colaborador():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja Sul", slug="loja-sul"),
    )
    responsible = _manager_actor("responsavel@revy.local")
    collaborator = _manager_actor("colaborador@revy.local")

    responsible_link = access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=responsible.id,
            role=TrafficRole.RESPONSIBLE,
        ),
    )
    collaborator_link = access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=collaborator.id,
            role=TrafficRole.COLLABORATOR,
        ),
    )

    assert responsible_link.store_id == store.id
    assert responsible_link.manager_id == responsible.id
    assert responsible_link.role is TrafficRole.RESPONSIBLE
    assert responsible_link.active is True
    assert collaborator_link.store_id == store.id
    assert collaborator_link.manager_id == collaborator.id
    assert collaborator_link.role is TrafficRole.COLLABORATOR
    assert collaborator_link.active is True


def test_segundo_responsavel_ativo_falha_explicitamente():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja Leste", slug="loja-leste"),
    )
    first = _manager_actor("primeiro@revy.local")
    second = _manager_actor("segundo@revy.local")
    access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=first.id,
            role=TrafficRole.RESPONSIBLE,
        ),
    )

    with pytest.raises(ActiveResponsibleConflict) as error:
        access.grant(
            admin,
            GrantTrafficAccess(
                store=StoreRef(id=store.id),
                manager_id=second.id,
                role=TrafficRole.RESPONSIBLE,
            ),
        )

    assert error.value.store_id == store.id
    assert error.value.manager_id == first.id


def test_gestor_ve_apenas_lojas_com_vinculo_ativo():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    admin = _admin_actor()
    visible = stores.create(
        admin,
        CreateStore(name="Loja Visível", slug="loja-visivel"),
    )
    stores.create(
        admin,
        CreateStore(name="Loja Oculta", slug="loja-oculta"),
    )
    manager = _manager_actor("escopado@revy.local")
    access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=visible.id),
            manager_id=manager.id,
            role=TrafficRole.COLLABORATOR,
        ),
    )

    scope = access.scope(manager)

    assert [(item.store.id, item.role) for item in scope] == [
        (visible.id, TrafficRole.COLLABORATOR),
    ]


def test_revogacao_remove_acesso_na_proxima_consulta():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja Revogada", slug="loja-revogada"),
    )
    manager = _manager_actor("revogado@revy.local")
    access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=manager.id,
            role=TrafficRole.COLLABORATOR,
        ),
    )

    revoked = access.revoke(
        admin,
        RevokeTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=manager.id,
            reason="fim da colaboração",
        ),
    )

    assert revoked.active is False
    assert access.scope(manager) == ()
    with pytest.raises(StoreNotFound):
        stores.get(manager, StoreRef(id=store.id))


def test_mutacoes_aparecem_na_trilha_de_auditoria():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    audit = AuditTrail(SessionLocal)
    admin = _admin_actor()
    manager = _manager_actor("auditado@revy.local")

    store = stores.create(
        admin,
        CreateStore(name="Loja Auditada", slug="loja-auditada"),
    )
    access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=manager.id,
            role=TrafficRole.RESPONSIBLE,
        ),
    )
    access.revoke(
        admin,
        RevokeTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=manager.id,
            reason="troca de responsável",
        ),
    )

    events = audit.list(admin, AuditQuery(store_id=store.id)).items

    assert [event.action for event in events] == [
        "store.created",
        "traffic_access.granted",
        "traffic_access.revoked",
    ]
    assert events[0].actor_id == admin.id
    assert events[0].after == {
        "name": "Loja Auditada",
        "slug": "loja-auditada",
        "status": "rascunho",
    }
    assert events[1].after == {
        "manager_id": manager.id,
        "role": "responsavel",
    }
    assert events[2].reason == "troca de responsável"


def test_concessao_exige_gestor_existente_e_ativo():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja Validada", slug="loja-validada"),
    )
    inactive = _manager_actor("inativo@revy.local", active=False)

    for manager_id in (inactive.id, "gestor-inexistente"):
        with pytest.raises(ManagerNotFound):
            access.grant(
                admin,
                GrantTrafficAccess(
                    store=StoreRef(id=store.id),
                    manager_id=manager_id,
                    role=TrafficRole.COLLABORATOR,
                ),
            )


def test_transicao_atualiza_loja_e_auditoria_na_mesma_mutacao():
    stores = StoreControl(SessionLocal)
    audit = AuditTrail(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja em Configuração", slug="loja-em-configuracao"),
    )

    transitioned = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.CONFIGURING,
            reason="início do onboarding",
        ),
    )
    events = audit.list(admin, AuditQuery(store_id=store.id)).items

    assert transitioned.status is StoreStatus.CONFIGURING
    assert transitioned.version == store.version + 1
    assert transitioned.updated_at > store.updated_at
    assert [event.action for event in events] == [
        "store.created",
        "store.status_changed",
    ]
    assert events[1].before == {"status": "rascunho"}
    assert events[1].after == {"status": "em_configuracao"}
    assert events[1].reason == "início do onboarding"


def test_loja_suspensa_pode_ser_reativada_com_nova_versao():
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()
    active = _create_active_store(
        stores,
        admin,
        slug="loja-reativada",
    )
    suspended = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=active.id),
            target=StoreStatus.SUSPENDED,
        ),
    )

    reactivated = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=active.id),
            target=StoreStatus.ACTIVE,
            reason="reativação explícita",
        ),
    )

    assert suspended.status is StoreStatus.SUSPENDED
    assert suspended.version == active.version + 1
    assert reactivated.status is StoreStatus.ACTIVE
    assert reactivated.version == suspended.version + 1


def test_loja_encerrada_permanece_terminal_sem_incrementar_versao():
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()
    active = _create_active_store(
        stores,
        admin,
        slug="loja-encerrada",
    )
    suspended = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=active.id),
            target=StoreStatus.SUSPENDED,
        ),
    )
    closed = stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=active.id),
            target=StoreStatus.CLOSED,
        ),
    )

    with pytest.raises(InvalidStoreTransition):
        stores.transition(
            admin,
            TransitionStore(
                store=StoreRef(id=active.id),
                target=StoreStatus.ACTIVE,
            ),
        )

    current = stores.get(admin, StoreRef(id=active.id))
    assert closed.version == suspended.version + 1
    assert current.status is StoreStatus.CLOSED
    assert current.version == closed.version


def test_admin_edita_loja_em_rascunho_com_auditoria():
    stores = StoreControl(SessionLocal)
    audit = AuditTrail(SessionLocal)
    admin = _admin_actor()
    store = stores.create(
        admin,
        CreateStore(name="Loja Antes", slug="loja-antes"),
    )

    updated = stores.update(
        admin,
        UpdateStore(
            store=StoreRef(id=store.id),
            name="  Loja Depois  ",
        ),
    )
    repeated = stores.update(
        admin,
        UpdateStore(
            store=StoreRef(id=store.id),
            name="Loja Depois",
        ),
    )

    assert updated.id == store.id
    assert updated.name == "Loja Depois"
    assert updated.slug == "loja-antes"
    assert updated.status is StoreStatus.DRAFT
    assert updated.version == store.version + 1
    assert repeated == updated
    assert repeated.version == updated.version
    events = audit.list(admin, AuditQuery(store_id=store.id)).items
    assert [event.action for event in events] == [
        "store.created",
        "store.updated",
    ]
    assert events[-1].action == "store.updated"
    assert events[-1].before == {"name": "Loja Antes"}
    assert events[-1].after == {"name": "Loja Depois"}


def test_edicao_de_loja_exige_admin_e_estado_rascunho():
    stores = StoreControl(SessionLocal)
    admin = _admin_actor()
    manager = _manager_actor("gestor.edicao@revy.local")
    store = stores.create(
        admin,
        CreateStore(name="Loja Protegida", slug="loja-protegida"),
    )
    command = UpdateStore(
        store=StoreRef(id=store.id),
        name="Loja Alterada",
    )

    with pytest.raises(AccessDenied):
        stores.update(manager, command)

    stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=store.id),
            target=StoreStatus.CONFIGURING,
        ),
    )
    with pytest.raises(StoreEditConflict):
        stores.update(admin, command)
    assert stores.get(admin, StoreRef(id=store.id)).name == "Loja Protegida"


def test_autorizacao_resolve_apenas_loja_no_escopo_do_gestor():
    stores = StoreControl(SessionLocal)
    access = AccessControl(SessionLocal)
    admin = _admin_actor()
    allowed = stores.create(
        admin,
        CreateStore(name="Loja Autorizada", slug="loja-autorizada"),
    )
    denied = stores.create(
        admin,
        CreateStore(name="Loja Fora do Escopo", slug="loja-fora-escopo"),
    )
    manager = _manager_actor("autorizado@revy.local")
    access.grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=allowed.id),
            manager_id=manager.id,
            role=TrafficRole.RESPONSIBLE,
        ),
    )

    authorized = access.authorize(manager, StoreRef(id=allowed.id))

    assert authorized.store == allowed
    assert authorized.role is TrafficRole.RESPONSIBLE
    with pytest.raises(StoreNotFound):
        access.authorize(manager, StoreRef(id=denied.id))
