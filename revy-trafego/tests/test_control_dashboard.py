from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.control.dashboard import DashboardControl
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore
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
    admin_ids = {item["store_id"] for item in admin_response.json()["items"]}
    assert allowed_id in admin_ids
    assert other_id in admin_ids
    sample = next(
        item
        for item in admin_response.json()["items"]
        if item["store_id"] == allowed_id
    )
    assert set(sample) == {"store_id", "slug", "name", "status", "ready"}
    assert sample["slug"] == "loja-dashboard-permitida"
    assert sample["name"] == "Loja Dashboard Permitida"
    assert sample["status"] == "rascunho"
    assert sample["ready"] is False

    client.cookies.clear()
    _login(client, "gestor.dashboard@revy.local", "senha-gestor-dashboard")
    gestor_response = client.get("/control/v1/dashboard")

    assert gestor_response.status_code == 200
    gestor_items = gestor_response.json()["items"]
    assert [item["store_id"] for item in gestor_items] == [allowed_id]
    assert other_id not in {item["store_id"] for item in gestor_items}


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
    assert 'id="tabela-dashboard-prontidao"' in admin_page.text
    assert "Loja Dashboard Permitida" in admin_page.text
    assert "Loja Dashboard Alheia" in admin_page.text
    assert f'data-store-id="{allowed_id}"' in admin_page.text
    assert f'data-store-id="{other_id}"' in admin_page.text
    assert 'id="nav-control-dashboard"' in admin_page.text

    client.cookies.clear()
    _login(client, "gestor.dashboard@revy.local", "senha-gestor-dashboard")
    gestor_page = client.get("/app/control/dashboard")

    assert gestor_page.status_code == 200
    assert "Loja Dashboard Permitida" in gestor_page.text
    assert "Loja Dashboard Alheia" not in gestor_page.text
