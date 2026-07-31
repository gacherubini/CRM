from dataclasses import replace

import pytest

from app.auth import hash_senha
from app.config import settings
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    CreateStore,
    StoreRef,
    StoreStatus,
)
from app.db import SessionLocal
from app.models import AuditoriaEvento, GestorRevy, Loja, agora
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
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _force_status(loja_id: str, status: StoreStatus) -> None:
    with SessionLocal() as db:
        store = db.query(Loja).filter(Loja.id == loja_id).one()
        store.status = status.value
        db.commit()


# --- Domínio -----------------------------------------------------------------

def test_apagar_rascunho_remove_loja_e_filhos():
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(admin, CreateStore(name="Loja Rascunho", slug="loja-rascunho"))

    outcome = stores.delete(admin, StoreRef(id=store.id))

    assert outcome == "deleted"
    with SessionLocal() as db:
        assert db.query(Loja).filter(Loja.id == store.id).first() is None
        # o evento store.created (RESTRICT) tinha de ter sido removido junto
        assert (
            db.query(AuditoriaEvento)
            .filter(AuditoriaEvento.loja_id == store.id)
            .count()
            == 0
        )
        # fica um rastro sem loja_id de que a loja foi apagada
        assert (
            db.query(AuditoriaEvento)
            .filter(AuditoriaEvento.acao == "store.deleted")
            .count()
            == 1
        )


def test_apagar_loja_com_historico_arquiva_em_vez_de_remover():
    admin = _admin_actor()
    stores = StoreControl(SessionLocal)
    store = stores.create(admin, CreateStore(name="Loja Viva", slug="loja-viva"))
    _force_status(store.id, StoreStatus.ACTIVE)

    outcome = stores.delete(admin, StoreRef(id=store.id))

    assert outcome == "archived"
    with SessionLocal() as db:
        row = db.query(Loja).filter(Loja.id == store.id).one()
        assert row.status == StoreStatus.CLOSED.value


def test_apagar_exige_admin():
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin, CreateStore(name="Loja Protegida", slug="loja-protegida")
    )
    gestor = Actor(id="g-1", email="g@revy.local", name="Gestor", role="gestor")

    with pytest.raises(AccessDenied):
        StoreControl(SessionLocal).delete(gestor, StoreRef(id=store.id))


# --- UI ----------------------------------------------------------------------

def test_zona_de_risco_aparece_so_para_admin(client, monkeypatch):
    store = StoreControl(SessionLocal).create(
        _admin_actor(), CreateStore(name="Loja Zona", slug="loja-zona")
    )
    with SessionLocal() as db:
        db.add(
            GestorRevy(
                email="gestor.zona@revy.local",
                nome="Gestor Zona",
                senha_hash=hash_senha("senha-zona"),
                papel="gestor",
                ativo=True,
            )
        )
        db.commit()
    _enable_control_ui(monkeypatch)

    _login(client, "trafego@revy.local", "secret-teste")
    admin_page = client.get(f"/app/control/lojas/{store.id}")
    assert 'id="form-excluir-loja"' in admin_page.text

    client.cookies.clear()
    _login(client, "gestor.zona@revy.local", "senha-zona")
    # gestor sem vínculo não vê a loja; concede vínculo para poder abrir o detalhe
    from app.control.access import AccessControl
    from app.control.types import GrantTrafficAccess, TrafficRole

    with SessionLocal() as db:
        gestor = db.query(GestorRevy).filter(
            GestorRevy.email == "gestor.zona@revy.local"
        ).one()
        gestor_id = gestor.id
    AccessControl(SessionLocal).grant(
        _admin_actor(),
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=gestor_id,
            role=TrafficRole.COLLABORATOR,
        ),
    )
    manager_page = client.get(f"/app/control/lojas/{store.id}")
    assert 'id="form-excluir-loja"' not in manager_page.text


def test_post_excluir_com_nome_correto_apaga_rascunho(client, monkeypatch):
    store = StoreControl(SessionLocal).create(
        _admin_actor(), CreateStore(name="Loja Some", slug="loja-some")
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail = client.get(f"/app/control/lojas/{store.id}")

    excluida = client.post(
        f"/app/control/lojas/{store.id}/excluir",
        data={"csrf": csrf_da_resposta(detail), "confirmacao": "Loja Some"},
        follow_redirects=False,
    )

    assert excluida.status_code == 303
    assert "excluida=1" in excluida.headers["location"]
    with SessionLocal() as db:
        assert db.query(Loja).filter(Loja.id == store.id).first() is None


def test_post_excluir_com_nome_errado_nao_apaga(client, monkeypatch):
    store = StoreControl(SessionLocal).create(
        _admin_actor(), CreateStore(name="Loja Fica", slug="loja-fica")
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail = client.get(f"/app/control/lojas/{store.id}")

    recusada = client.post(
        f"/app/control/lojas/{store.id}/excluir",
        data={"csrf": csrf_da_resposta(detail), "confirmacao": "nome errado"},
        follow_redirects=False,
    )

    assert recusada.status_code == 422
    with SessionLocal() as db:
        assert db.query(Loja).filter(Loja.id == store.id).first() is not None
