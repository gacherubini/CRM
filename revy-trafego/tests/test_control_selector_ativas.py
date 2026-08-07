from dataclasses import replace
from types import SimpleNamespace

from app.auth import hash_senha
from app.config import settings as app_settings
from app.control.types import StoreStatus
from app.db import SessionLocal
from app.models import Loja, GestorRevy
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod


def _item(slug, status):
    return SimpleNamespace(store=SimpleNamespace(slug=slug, status=status), role=None)


def _patch_rbac(monkeypatch, enabled):
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(control_ui_mod.settings, revy_control_rbac_enabled=enabled),
    )


def test_selector_rbac_lista_so_ativas(monkeypatch):
    _patch_rbac(monkeypatch, True)
    scoped = [
        _item("viva", StoreStatus.ACTIVE),
        _item("suspensa", StoreStatus.SUSPENDED),
        _item("rascunho", StoreStatus.DRAFT),
    ]
    result = control_ui_mod._selector_stores(scoped)
    assert [i.store.slug for i in result] == ["viva"]


def test_selector_sem_rbac_devolve_slugs_ativas(monkeypatch):
    _patch_rbac(monkeypatch, False)
    scoped = [
        _item("viva", StoreStatus.ACTIVE),
        _item("config", StoreStatus.CONFIGURING),
    ]
    result = control_ui_mod._selector_stores(scoped)
    assert result == ["viva"]


def _enable(monkeypatch):
    patched = replace(
        app_settings,
        revy_control_enabled=True,
        revy_control_dashboard_enabled=True,
        revy_control_rbac_enabled=False,
    )
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


def test_gestao_lista_todas_seletor_so_ativas(client, monkeypatch):
    _enable(monkeypatch)
    with SessionLocal() as db:
        db.add(Loja(nome="Loja Viva", slug="loja-viva", status="ativa"))
        db.add(Loja(nome="Loja Parada", slug="loja-parada", status="suspensa"))
        db.commit()
    client.post("/login", data={"email": "trafego@revy.local", "senha": "secret-teste"},
                follow_redirects=False)

    pagina = client.get("/app/control/lojas")

    assert pagina.status_code == 200
    # Gestão mostra as duas lojas (nomes na tabela)
    assert "Loja Viva" in pagina.text
    assert "Loja Parada" in pagina.text
    # Seletor lateral (base.html) só oferece a ativa como <option value="slug">
    assert 'value="loja-viva"' in pagina.text
    assert 'value="loja-parada"' not in pagina.text
