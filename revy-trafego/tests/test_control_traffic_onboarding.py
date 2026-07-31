from app.control.access import AccessControl
from app.control.invitations import ControlInvitations, _token_hash
from app.control.stores import StoreControl
from app.control.traffic_onboarding import (
    InviteTrafficManager,
    TrafficManagerOnboarding,
)
from app.control.types import (
    AccessDenied,
    ActivateControlAccess,
    Actor,
    CreateStore,
    StoreRef,
    TrafficRole,
)
from app.db import SessionLocal
from app.models import AcessoControl, ConviteAcessoControl, GestorRevy, VinculoTrafego


def _admin(db) -> Actor:
    gestor = db.query(GestorRevy).filter(GestorRevy.papel == "admin").first()
    return Actor(id=gestor.id, email=gestor.email, name=gestor.nome, role="admin")


def _make_store(actor: Actor) -> str:
    store = StoreControl(SessionLocal).create(
        actor, CreateStore(name="Loja Teste", slug="loja-teste")
    )
    return store.id


def test_invita_gestor_novo_cria_identidades_alinhadas_e_convite():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)

    result = TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_id),
            email="Gestora.Nova@Example.com",
            name="Gestora Nova",
            role=TrafficRole.RESPONSIBLE,
        ),
    )

    assert result.token is not None and len(result.token) >= 32
    assert result.already_active is False
    with SessionLocal() as db:
        gestor = (
            db.query(GestorRevy)
            .filter(GestorRevy.email == "gestora.nova@example.com")
            .one()
        )
        acesso = db.get(AcessoControl, gestor.id)
        assert acesso is not None
        assert acesso.id == gestor.id
        assert acesso.gestor_legado_id == gestor.id
        assert acesso.papel == "gestor"
        assert acesso.estado == "pendente"
        link = (
            db.query(VinculoTrafego)
            .filter(VinculoTrafego.loja_id == store_id, VinculoTrafego.gestor_id == gestor.id)
            .one()
        )
        assert link.tipo == "responsavel"
        convite = db.query(ConviteAcessoControl).filter(
            ConviteAcessoControl.acesso_id == acesso.id
        ).one()
        assert convite.token_hash == _token_hash(result.token)


def test_aceite_reusa_activate_e_gestor_ve_a_loja():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    result = TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_id),
            email="gestora@example.com",
            name="Gestora",
            role=TrafficRole.COLLABORATOR,
        ),
    )

    account = ControlInvitations(SessionLocal).activate(
        ActivateControlAccess(token=result.token, password="senha-super-segura")
    )
    assert account.status.value == "ativo"

    with SessionLocal() as db:
        acesso = db.get(AcessoControl, result.manager_id)
        gestor_actor = Actor(
            id=acesso.id,
            email="gestora@example.com",
            name="Gestora",
            role="gestor",
        )
        scope = AccessControl(SessionLocal).scope(gestor_actor)
    assert store_id in [item.store.id for item in scope]


def test_invita_gestor_ja_ativo_apenas_vincula_sem_novo_convite():
    with SessionLocal() as db:
        actor = _admin(db)
    store_a = _make_store(actor)
    onboarding = TrafficManagerOnboarding(SessionLocal)
    first = onboarding.invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_a),
            email="g@example.com",
            name="G",
            role=TrafficRole.COLLABORATOR,
        ),
    )
    ControlInvitations(SessionLocal).activate(
        ActivateControlAccess(token=first.token, password="senha-super-segura")
    )
    store_b = StoreControl(SessionLocal).create(
        actor, CreateStore(name="Loja B", slug="loja-b")
    ).id

    second = onboarding.invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_b),
            email="g@example.com",
            name="G",
            role=TrafficRole.COLLABORATOR,
        ),
    )
    assert second.already_active is True
    assert second.token is None
    with SessionLocal() as db:
        assert db.query(VinculoTrafego).filter(
            VinculoTrafego.gestor_id == first.manager_id,
            VinculoTrafego.encerrado_em.is_(None),
        ).count() == 2


def test_nao_admin_recebe_access_denied():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    intruso = Actor(id="x", email="x@y.z", name="X", role="gestor")

    try:
        TrafficManagerOnboarding(SessionLocal).invite_or_bind(
            intruso,
            InviteTrafficManager(
                store=StoreRef(id=store_id),
                email="a@b.c",
                name="A",
                role=TrafficRole.COLLABORATOR,
            ),
        )
        assert False, "esperava AccessDenied"
    except AccessDenied:
        pass


def test_reenvio_de_convite_pendente_reemite_token_sem_duplicar_vinculo():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    onboarding = TrafficManagerOnboarding(SessionLocal)
    command = InviteTrafficManager(
        store=StoreRef(id=store_id),
        email="reenvio@example.com",
        name="Gestor Reenvio",
        role=TrafficRole.COLLABORATOR,
    )
    first = onboarding.invite_or_bind(actor, command)
    second = onboarding.invite_or_bind(actor, command)
    assert second.token is not None
    assert second.token != first.token
    with SessionLocal() as db:
        assert db.query(VinculoTrafego).filter(
            VinculoTrafego.loja_id == store_id,
            VinculoTrafego.gestor_id == first.manager_id,
            VinculoTrafego.encerrado_em.is_(None),
        ).count() == 1
        invitations = db.query(ConviteAcessoControl).filter(
            ConviteAcessoControl.acesso_id == first.manager_id
        ).order_by(ConviteAcessoControl.criado_em).all()
        assert len(invitations) == 2
        assert invitations[0].revogado_em is not None
        assert invitations[1].token_hash == _token_hash(second.token)


def test_list_links_traz_email_e_nome_do_gestor():
    with SessionLocal() as db:
        actor = _admin(db)
    store_id = _make_store(actor)
    TrafficManagerOnboarding(SessionLocal).invite_or_bind(
        actor,
        InviteTrafficManager(
            store=StoreRef(id=store_id),
            email="lista@example.com",
            name="Gestor Lista",
            role=TrafficRole.RESPONSIBLE,
        ),
    )
    links = AccessControl(SessionLocal).list_links(actor, StoreRef(id=store_id))
    assert len(links) == 1
    assert links[0].manager_email == "lista@example.com"
    assert links[0].manager_name == "Gestor Lista"
    assert links[0].link.role == TrafficRole.RESPONSIBLE
