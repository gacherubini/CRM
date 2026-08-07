from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.control.dashboard import DashboardControl
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore, StoreStatus, TransitionStore
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VinculoTrafego
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod


def _enable_control(monkeypatch, *, dashboard: bool = False) -> None:
    patched = replace(
        settings,
        revy_control_enabled=True,
        revy_control_dashboard_enabled=dashboard,
    )
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


def _login(client, email: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"email": email, "senha": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _seed_scoped_stores() -> tuple[str, str, str]:
    """Cria loja permitida (vínculo) e loja alheia; retorna (manager_id, allowed_id, other_id)."""
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.dashboard@revy.local",
            nome="Gestor Dashboard",
            senha_hash=hash_senha("senha-gestor-dashboard"),
            papel="gestor",
            ativo=True,
        )
        allowed = Loja(
            nome="Loja Dashboard Permitida",
            slug="loja-dashboard-permitida",
            status="rascunho",
        )
        other = Loja(
            nome="Loja Dashboard Alheia",
            slug="loja-dashboard-alheia",
            status="rascunho",
        )
        db.add_all([manager, allowed, other])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=allowed.id,
                gestor_id=manager.id,
                tipo="responsavel",
            )
        )
        db.commit()
        return manager.id, allowed.id, other.id


def test_dashboard_api_404_sem_flags(client):
    response = client.get("/control/v1/dashboard")
    assert response.status_code == 404


def test_dashboard_api_404_sem_flag_dashboard(client, monkeypatch):
    _enable_control(monkeypatch, dashboard=False)
    _login(client, "trafego@revy.local", "secret-teste")

    response = client.get("/control/v1/dashboard")

    assert response.status_code == 404


def test_dashboard_api_exige_sessao_quando_habilitada(client, monkeypatch):
    _enable_control(monkeypatch, dashboard=True)

    response = client.get("/control/v1/dashboard")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_dashboard_summary_admin_ve_todas_e_gestor_so_escopo():
    admin = _admin_actor()
    store_a = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Dashboard A", slug="dashboard-a"),
    )
    store_b = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Dashboard B", slug="dashboard-b"),
    )
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.summary@revy.local",
            nome="Gestor Summary",
            senha_hash=hash_senha("senha-summary"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=store_a.id,
                gestor_id=manager.id,
                tipo="colaborador",
            )
        )
        db.commit()
        manager_actor = Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )

    dashboard = DashboardControl(SessionLocal)
    admin_items = dashboard.summary(admin)
    admin_ids = {item.store_id for item in admin_items}
    assert store_a.id in admin_ids
    assert store_b.id in admin_ids
    for item in admin_items:
        assert set(item.__dataclass_fields__) >= {
            "store_id",
            "slug",
            "name",
            "status",
            "ready",
        }
        assert item.ready is False

    gestor_items = dashboard.summary(manager_actor)
    assert [item.store_id for item in gestor_items] == [store_a.id]
    assert gestor_items[0].slug == "dashboard-a"
    assert gestor_items[0].name == "Dashboard A"
    assert gestor_items[0].ready is False


def test_dashboard_api_admin_e_gestor_respeitam_escopo(client, monkeypatch):
    _, allowed_id, other_id = _seed_scoped_stores()
    _enable_control(monkeypatch, dashboard=True)
    _login(client, "trafego@revy.local", "secret-teste")

    admin_response = client.get("/control/v1/dashboard")

    assert admin_response.status_code == 200
    body = admin_response.json()
    assert "counts" in body
    assert set(body["counts"]) == {
        "ativas",
        "em_configuracao",
        "suspensas",
        "erro",
    }
    assert "pending_readiness" in body
    assert "integrations" in body
    admin_ids = {item["store_id"] for item in body["items"]}
    assert allowed_id in admin_ids
    assert other_id in admin_ids
    sample = next(
        item for item in body["items"] if item["store_id"] == allowed_id
    )
    assert set(sample) >= {
        "store_id",
        "slug",
        "name",
        "status",
        "ready",
        "gestor_responsavel",
        "modulos",
        "integration_failures",
    }
    assert sample["slug"] == "loja-dashboard-permitida"
    assert sample["name"] == "Loja Dashboard Permitida"
    assert sample["status"] == "rascunho"
    assert sample["ready"] is False
    assert sample["gestor_responsavel"] is not None
    assert sample["gestor_responsavel"]["email"] == "gestor.dashboard@revy.local"
    assert sample["modulos"] == []
    assert "recent_audit" in body
    assert isinstance(body["recent_audit"], list)
    pending_ids = {item["store_id"] for item in body["pending_readiness"]}
    assert allowed_id in pending_ids
    assert other_id in pending_ids
    integ = next(
        item for item in body["integrations"] if item["store_id"] == allowed_id
    )
    assert set(integ) >= {
        "store_id",
        "slug",
        "pixel_connected",
        "meta_ads_connected",
        "google_status",
        "whatsapp_channels",
        "failures",
    }
    assert integ["pixel_connected"] is False

    client.cookies.clear()
    _login(client, "gestor.dashboard@revy.local", "senha-gestor-dashboard")
    gestor_response = client.get("/control/v1/dashboard")

    assert gestor_response.status_code == 200
    gestor_body = gestor_response.json()
    gestor_items = gestor_body["items"]
    assert [item["store_id"] for item in gestor_items] == [allowed_id]
    assert other_id not in {item["store_id"] for item in gestor_items}
    assert [item["store_id"] for item in gestor_body["pending_readiness"]] == [
        allowed_id
    ]
    assert other_id not in {
        item["store_id"] for item in gestor_body["integrations"]
    }
    for event in gestor_body["recent_audit"]:
        assert event["store_id"] in {None, allowed_id}
        assert event["store_id"] != other_id


def test_dashboard_overview_counts_e_isolamento_gestor():
    from app.control.types import StoreRef

    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    configuring = stores.create(
        admin,
        CreateStore(name="Dash Config", slug="dash-config"),
    )
    suspended = stores.create(
        admin,
        CreateStore(name="Dash Suspensa", slug="dash-suspensa"),
    )
    stores.transition(
        admin,
        TransitionStore(
            store=StoreRef(id=configuring.id),
            target=StoreStatus.CONFIGURING,
        ),
    )
    # Suspensa via DB para não depender do caminho pronta→ativa.
    with SessionLocal() as db:
        row = db.query(Loja).filter(Loja.id == suspended.id).one()
        row.status = StoreStatus.SUSPENDED.value
        db.commit()

    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.counts@revy.local",
            nome="Gestor Counts",
            senha_hash=hash_senha("senha-counts"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=configuring.id,
                gestor_id=manager.id,
                tipo="colaborador",
            )
        )
        db.commit()
        manager_actor = Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )

    dashboard = DashboardControl(SessionLocal)
    admin_overview = dashboard.overview(admin)
    assert admin_overview.counts.em_configuracao >= 1
    assert admin_overview.counts.suspensas >= 1
    admin_ids = {item.store_id for item in admin_overview.items}
    assert configuring.id in admin_ids
    assert suspended.id in admin_ids

    gestor_overview = dashboard.gestor_overview(manager_actor)
    assert [item.store_id for item in gestor_overview.items] == [configuring.id]
    assert gestor_overview.counts.em_configuracao == 1
    assert gestor_overview.counts.suspensas == 0
    assert suspended.id not in {
        item.store_id for item in gestor_overview.pending_readiness
    }


def test_dashboard_html_404_sem_flags(client, client_logado):
    response = client_logado.get("/app/control/dashboard")
    assert response.status_code == 404


def test_dashboard_html_lista_prontidao_no_escopo(client, monkeypatch):
    _, allowed_id, other_id = _seed_scoped_stores()
    _enable_control(monkeypatch, dashboard=True)
    _login(client, "trafego@revy.local", "secret-teste")

    admin_page = client.get("/app/control/dashboard")

    assert admin_page.status_code == 200
    assert "Revy Control" in admin_page.text
    # A tabela de cadastro e a faixa de contagens saíram: duplicavam a tela
    # Lojas, que é item de menu próprio. O escopo por gestor passou a ser
    # verificado pela tabela de pendências de prontidão, que ficou.
    assert 'id="tabela-dashboard-prontidao"' not in admin_page.text
    assert 'id="dashboard-counts"' not in admin_page.text
    assert 'id="dashboard-destaques"' not in admin_page.text
    assert "Alterações recentes" not in admin_page.text
    assert 'id="dashboard-pendencias"' in admin_page.text
    assert 'id="tabela-dashboard-pendencias"' in admin_page.text
    assert "Loja Dashboard Permitida" in admin_page.text
    assert "Loja Dashboard Alheia" in admin_page.text
    assert f'data-store-id="{allowed_id}"' in admin_page.text
    assert f'data-store-id="{other_id}"' in admin_page.text
    assert 'id="nav-control-dashboard"' in admin_page.text
    # Prontidão distingue bloqueio de alerta em vez de um chip só.
    assert "Bloqueio ·" in admin_page.text
    # Período declarado na tela (a venda é contada por confirmada_em).
    assert 'id="dashboard-periodo"' in admin_page.text
    assert "vendas contadas pela data de confirmação" in admin_page.text

    client.cookies.clear()
    _login(client, "gestor.dashboard@revy.local", "senha-gestor-dashboard")
    gestor_page = client.get("/app/control/dashboard")

    assert gestor_page.status_code == 200
    assert "Loja Dashboard Permitida" in gestor_page.text
    assert "Loja Dashboard Alheia" not in gestor_page.text


def test_dashboard_html_aceita_filtro_de_periodo(client, monkeypatch):
    _seed_scoped_stores()
    _enable_control(monkeypatch, dashboard=True)
    _login(client, "trafego@revy.local", "secret-teste")

    pagina = client.get("/app/control/dashboard?inicio=2026-01-01&fim=2026-01-31")

    assert pagina.status_code == 200
    assert "Período de 01/01/2026 a 31/01/2026" in pagina.text
    assert 'name="inicio" value="2026-01-01"' in pagina.text
    assert 'name="fim" value="2026-01-31"' in pagina.text


def test_dashboard_html_ignora_periodo_invalido(client, monkeypatch):
    """Data quebrada na query não pode derrubar a página — cai na janela padrão."""
    _seed_scoped_stores()
    _enable_control(monkeypatch, dashboard=True)
    _login(client, "trafego@revy.local", "secret-teste")

    pagina = client.get("/app/control/dashboard?inicio=31-01-2026&fim=abacaxi")

    assert pagina.status_code == 200
    assert 'id="dashboard-periodo"' in pagina.text


def test_dashboard_overview_modulos_gestor_e_auditoria_escopada():
    from app.control.portfolio import PortfolioControl
    from app.control.types import StoreRef
    from app.models import AuditoriaEvento, ModuloRevy

    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    allowed = stores.create(
        admin,
        CreateStore(name="Dash Rico Permitida", slug="dash-rico-ok"),
    )
    other = stores.create(
        admin,
        CreateStore(name="Dash Rico Alheia", slug="dash-rico-alheia"),
    )

    with SessionLocal() as db:
        if db.query(ModuloRevy).count() == 0:
            db.add_all(
                [
                    ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                    ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                ]
            )
            db.commit()

    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=allowed.id),
        {"vendas", "estoque"},
    )
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=other.id),
        {"vendas"},
    )
    PortfolioControl(SessionLocal).suspend(
        admin,
        StoreRef(id=allowed.id),
        "estoque",
        reason="manutenção programada",
    )

    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.rico@revy.local",
            nome="Gestor Rico",
            senha_hash=hash_senha("senha-rico"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=allowed.id,
                gestor_id=manager.id,
                tipo="responsavel",
            )
        )
        # Evento na loja alheia não deve vazar para o gestor.
        db.add(
            AuditoriaEvento(
                loja_id=other.id,
                ator_gestor_id=admin.id,
                ator_email=admin.email,
                acao="store.secret",
                recurso_tipo="loja",
                recurso_id=other.id,
                resultado="sucesso",
            )
        )
        db.commit()
        manager_actor = Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )

    dashboard = DashboardControl(SessionLocal)
    admin_overview = dashboard.overview(admin)
    admin_item = next(
        item for item in admin_overview.items if item.store_id == allowed.id
    )
    assert admin_item.gestor_responsavel is not None
    assert admin_item.gestor_responsavel.email == "gestor.rico@revy.local"
    assert admin_item.gestor_responsavel.name == "Gestor Rico"
    codes = {m.code: m.status for m in admin_item.modulos}
    assert codes["vendas"] == "ativo"
    assert codes["estoque"] == "suspenso"
    admin_audit_store_ids = {
        e.store_id for e in admin_overview.recent_audit if e.store_id
    }
    assert other.id in admin_audit_store_ids or allowed.id in admin_audit_store_ids

    gestor_overview = dashboard.gestor_overview(manager_actor)
    assert [item.store_id for item in gestor_overview.items] == [allowed.id]
    gestor_item = gestor_overview.items[0]
    assert gestor_item.gestor_responsavel is not None
    assert gestor_item.gestor_responsavel.email == "gestor.rico@revy.local"
    assert {m.code for m in gestor_item.modulos} == {"vendas", "estoque"}
    for event in gestor_overview.recent_audit:
        assert event.store_id != other.id
        assert event.action != "store.secret"
    assert any(e.action == "store_module.suspended" for e in gestor_overview.recent_audit)
