import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.auth import hash_senha
from app.config import settings
from app.control.access import AccessControl
from app.control.contracts import (
    ContractBillingStatus,
    ContractControl,
    UpsertContract,
)
from app.control.portfolio import PortfolioControl
from app.control.stores import StoreControl
from app.control.types import (
    Actor,
    CreateStore,
    GrantTrafficAccess,
    StoreRef,
    TrafficRole,
)
from app.db import SessionLocal
from app.models import GestorRevy, Loja, ModuloRevy, VinculoTrafego
from app.web import control_ui as control_ui_mod
from tests.conftest import csrf_da_resposta


def _enable_control_ui(monkeypatch):
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


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


def _seed_module_catalog() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
            ]
        )
        db.commit()


def test_control_ui_fica_oculta_e_redireciona_sem_sessao(client, monkeypatch):
    hidden = client.get("/app/control/lojas", follow_redirects=False)

    assert hidden.status_code == 404

    _enable_control_ui(monkeypatch)
    unauthenticated = client.get(
        "/app/control/lojas",
        follow_redirects=False,
    )

    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"].endswith("/login")


def test_control_ui_lista_escopo_e_mostra_formulario_somente_para_admin(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.ui@revy.local",
            nome="Gestor UI",
            senha_hash=hash_senha("senha-gestor-ui"),
            papel="gestor",
            ativo=True,
        )
        allowed = Loja(nome="Loja UI Permitida", slug="loja-ui-permitida")
        other = Loja(nome="Loja UI Alheia", slug="loja-ui-alheia")
        db.add_all([manager, allowed, other])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=allowed.id,
                gestor_id=manager.id,
                tipo="colaborador",
            )
        )
        db.commit()

    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    admin_page = client.get("/app/control/lojas")

    assert admin_page.status_code == 200
    assert "Loja UI Permitida" in admin_page.text
    assert "Loja UI Alheia" in admin_page.text
    assert 'id="form-criar-loja"' in admin_page.text
    assert 'id="nav-control-lojas"' in admin_page.text

    client.cookies.clear()
    _login(client, "gestor.ui@revy.local", "senha-gestor-ui")
    manager_page = client.get("/app/control/lojas")

    assert manager_page.status_code == 200
    assert "Loja UI Permitida" in manager_page.text
    assert "Loja UI Alheia" not in manager_page.text
    assert 'id="form-criar-loja"' not in manager_page.text


def test_lista_de_lojas_linka_cada_loja_ao_detalhe(client, monkeypatch):
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    first = stores.create(
        admin,
        CreateStore(name="Loja Navegável Um", slug="loja-navegavel-um"),
    )
    second = stores.create(
        admin,
        CreateStore(name="Loja Navegável Dois", slug="loja-navegavel-dois"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    page = client.get("/app/control/lojas")

    assert page.status_code == 200
    assert all(
        f'href="/app/control/lojas/{store.id}"' in page.text
        for store in (first, second)
    )


def test_admin_cria_loja_com_csrf_e_gestor_recebe_403(client, monkeypatch):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.post-ui@revy.local",
            nome="Gestor POST UI",
            senha_hash=hash_senha("senha-post-ui"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()

    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    admin_page = client.get("/app/control/lojas")

    invalid_csrf = client.post(
        "/app/control/lojas",
        data={"nome": "Loja Sem CSRF", "slug": "loja-sem-csrf"},
    )
    created = client.post(
        "/app/control/lojas",
        data={
            "csrf": csrf_da_resposta(admin_page),
            "nome": "Loja Criada na UI",
            "slug": "loja-criada-ui",
        },
        follow_redirects=False,
    )

    assert invalid_csrf.status_code == 403
    assert "CSRF" in invalid_csrf.text
    assert created.status_code == 303
    created_page = client.get(created.headers["location"])
    assert "Loja criada com sucesso" in created_page.text
    assert "Loja Criada na UI" in created_page.text

    client.cookies.clear()
    _login(client, "gestor.post-ui@revy.local", "senha-post-ui")
    manager_page = client.get("/app/control/lojas")
    forbidden = client.post(
        "/app/control/lojas",
        data={
            "csrf": csrf_da_resposta(manager_page),
            "nome": "Loja Proibida",
            "slug": "loja-proibida",
        },
    )

    assert forbidden.status_code == 403
    assert "permissão" in forbidden.text


def test_detalhe_mostra_estado_e_auditoria_somente_no_escopo(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.detalhe@revy.local",
            nome="Gestor Detalhe",
            senha_hash=hash_senha("senha-detalhe"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()
        manager_id = manager.id

    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    allowed = stores.create(
        admin,
        CreateStore(name="Loja Detalhada", slug="loja-detalhada"),
    )
    denied = stores.create(
        admin,
        CreateStore(name="Loja Alheia Detalhada", slug="loja-alheia-detalhada"),
    )
    AccessControl(SessionLocal).grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=allowed.id),
            manager_id=manager_id,
            role=TrafficRole.COLLABORATOR,
        ),
    )

    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    admin_page = client.get(f"/app/control/lojas/{allowed.id}")

    assert admin_page.status_code == 200
    assert "Loja Detalhada" in admin_page.text
    assert "rascunho" in admin_page.text
    assert "store.created" in admin_page.text
    assert "traffic_access.granted" in admin_page.text
    assert 'id="form-alterar-estado"' in admin_page.text
    assert 'id="form-conceder-gestor"' in admin_page.text
    assert 'id="form-revogar-gestor"' in admin_page.text

    client.cookies.clear()
    _login(client, "gestor.detalhe@revy.local", "senha-detalhe")
    manager_page = client.get(f"/app/control/lojas/{allowed.id}")
    hidden = client.get(f"/app/control/lojas/{denied.id}")

    assert manager_page.status_code == 200
    assert "Loja Detalhada" in manager_page.text
    assert "traffic_access.granted" in manager_page.text
    assert 'id="form-alterar-estado"' not in manager_page.text
    assert 'id="form-conceder-gestor"' not in manager_page.text
    assert 'id="form-revogar-gestor"' not in manager_page.text
    assert hidden.status_code == 404


def test_detalhe_exibe_versoes_modulos_e_contrato_ativo(client, monkeypatch):
    _seed_module_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Configurada", slug="loja-configurada"),
    )
    store_ref = StoreRef(id=store.id)
    portfolio = PortfolioControl(SessionLocal)
    portfolio.configure(admin, store_ref, {"vendas", "estoque"})
    portfolio.suspend(
        admin,
        store_ref,
        "estoque",
        reason="pausa de inventário",
    )
    ContractControl(SessionLocal).upsert(
        admin,
        UpsertContract(
            store=store_ref,
            monthly_amount=Decimal("1299.90"),
            starts_on=date(2026, 8, 1),
            ends_on=date(2027, 7, 31),
            due_day=12,
            billing_status=ContractBillingStatus.OVERDUE,
        ),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    page = client.get(f"/app/control/lojas/{store.id}")

    assert page.status_code == 200
    assert re.search(
        r'id="loja-versao"[^>]*>\s*Versão 1\s*<',
        page.text,
    )
    assert re.search(
        r'id="modulo-vendas".*?<td>Vendas</td>.*?<td>ativo</td>.*?<td>1</td>',
        page.text,
        re.DOTALL,
    )
    assert re.search(
        r'id="modulo-estoque".*?<td>Estoque</td>.*?<td>suspenso</td>.*?<td>2</td>',
        page.text,
        re.DOTALL,
    )
    assert 'id="contrato-ativo"' in page.text
    assert "R$ 1.299,90" in page.text
    assert "01/08/2026 a 31/07/2027" in page.text
    assert "Dia 12" in page.text
    assert "atrasada" in page.text


def test_admin_transiciona_concede_revoga_e_gestor_nao_muta(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        first = GestorRevy(
            email="gestor.ciclo-um@revy.local",
            nome="Gestor Ciclo Um",
            senha_hash=hash_senha("senha-ciclo-um"),
            papel="gestor",
            ativo=True,
        )
        second = GestorRevy(
            email="gestor.ciclo-dois@revy.local",
            nome="Gestor Ciclo Dois",
            senha_hash=hash_senha("senha-ciclo-dois"),
            papel="gestor",
            ativo=True,
        )
        db.add_all([first, second])
        db.commit()
        first_id = first.id
        second_id = second.id

    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Ciclo UI", slug="loja-ciclo-ui"),
    )

    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail = client.get(f"/app/control/lojas/{store.id}")
    csrf = csrf_da_resposta(detail)

    transitioned = client.post(
        f"/app/control/lojas/{store.id}/estado",
        data={
            "csrf": csrf,
            "estado": "em_configuracao",
            "motivo": "início do onboarding",
        },
        follow_redirects=False,
    )
    granted = client.post(
        f"/app/control/lojas/{store.id}/gestores",
        data={
            "csrf": csrf,
            "gestor_id": first_id,
            "tipo": "responsavel",
        },
        follow_redirects=False,
    )
    conflict = client.post(
        f"/app/control/lojas/{store.id}/gestores",
        data={
            "csrf": csrf,
            "gestor_id": second_id,
            "tipo": "responsavel",
        },
    )
    revoked = client.post(
        f"/app/control/lojas/{store.id}/gestores/{first_id}/revogar",
        data={"csrf": csrf, "motivo": "troca operacional"},
        follow_redirects=False,
    )

    assert transitioned.status_code == 303
    assert "ok=estado" in transitioned.headers["location"]
    assert granted.status_code == 303
    assert "ok=gestor" in granted.headers["location"]
    assert conflict.status_code == 409
    assert "Gestor Responsável ativo" in conflict.text
    assert revoked.status_code == 303
    assert "ok=revogado" in revoked.headers["location"]

    final_page = client.get(f"/app/control/lojas/{store.id}")
    assert "em_configuracao" in final_page.text
    assert "store.status_changed" in final_page.text
    assert "traffic_access.granted" in final_page.text
    assert "traffic_access.revoked" in final_page.text

    client.cookies.clear()
    _login(client, "gestor.ciclo-dois@revy.local", "senha-ciclo-dois")
    home = client.get("/app")
    forbidden = client.post(
        f"/app/control/lojas/{store.id}/estado",
        data={
            "csrf": csrf_da_resposta(home),
            "estado": "pronta",
        },
    )

    assert forbidden.status_code == 403
    assert "permissão" in forbidden.text
