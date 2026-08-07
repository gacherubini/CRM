"""Navegação do Control: /app deixou de ser tela e Integrações virou página.

Cobre a remoção da tela "Escolha a loja" (que duplicava o seletor da sidebar) e
a paridade de Ajustes › Integrações com a Revy Loja.
"""
from dataclasses import replace

from app.config import settings
from app.db import SessionLocal
from app.models import Loja
from app import main as main_mod
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod


def _enable_control(monkeypatch, *, dashboard: bool = False) -> None:
    patched = replace(
        settings,
        revy_control_enabled=True,
        revy_control_dashboard_enabled=dashboard,
        revy_control_rbac_enabled=False,
    )
    monkeypatch.setattr(main_mod, "settings", patched)
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


def _disable_control(monkeypatch) -> None:
    patched = replace(
        settings,
        revy_control_enabled=False,
        revy_control_dashboard_enabled=False,
        revy_control_rbac_enabled=False,
    )
    monkeypatch.setattr(main_mod, "settings", patched)
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


def _login(client) -> None:
    r = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _seed_loja(slug="loja-nav", nome="Loja Nav", status="ativa") -> str:
    with SessionLocal() as db:
        loja = Loja(nome=nome, slug=slug, status=status)
        db.add(loja)
        db.commit()
        return loja.id


def _selecionar_loja(client, slug="loja-nav") -> None:
    import re

    pagina = client.get("/app/control/lojas")
    csrf = re.search(r'name="csrf" value="([^"]+)"', pagina.text).group(1)
    client.post(
        "/app/loja",
        data={"csrf": csrf, "loja_slug": slug},
        follow_redirects=False,
    )


def test_app_redireciona_para_visao_geral_com_dashboard(client, monkeypatch):
    _seed_loja()
    _enable_control(monkeypatch, dashboard=True)
    _login(client)

    r = client.get("/app", follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"].endswith("/app/control/dashboard")


def test_app_redireciona_para_lojas_sem_dashboard(client, monkeypatch):
    _seed_loja()
    _enable_control(monkeypatch, dashboard=False)
    _login(client)

    r = client.get("/app", follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"].endswith("/app/control/lojas")


def test_app_sem_control_e_sem_loja_nao_entra_em_laco(client, monkeypatch):
    """exigir_loja manda todo mundo para /app: aqui não pode haver redirect."""
    _disable_control(monkeypatch)
    _login(client)

    r = client.get("/app", follow_redirects=False)

    assert r.status_code == 200
    assert "Selecione uma loja" in r.text
    # O formulário duplicado e o campo livre de slug saíram.
    assert "loja_slug_manual" not in r.text
    assert "Outra loja" not in r.text


def test_integracoes_e_pagina_propria_no_control(client, monkeypatch):
    _seed_loja()
    _enable_control(monkeypatch, dashboard=True)
    _login(client)
    _selecionar_loja(client)

    r = client.get("/app/control/integracoes")

    assert r.status_code == 200
    assert 'id="integracoes-health"' in r.text
    assert "Testar agora" in r.text
    assert "Loja Nav" in r.text
    # Entrada no menu, na mesma seção Ajustes que a Revy Loja usa.
    assert 'id="nav-control-integracoes"' in r.text


def test_integracoes_sem_loja_selecionada_orienta(client, monkeypatch):
    _seed_loja()
    _enable_control(monkeypatch, dashboard=True)
    _login(client)

    r = client.get("/app/control/integracoes")

    assert r.status_code == 200
    assert "Escolha uma loja" in r.text
    assert 'id="integracoes-health"' not in r.text


def test_integracoes_404_sem_control(client, monkeypatch):
    _disable_control(monkeypatch)
    _login(client)

    r = client.get("/app/control/integracoes")

    assert r.status_code == 404


def test_titulos_de_midia_casam_com_o_menu(client, monkeypatch):
    """base.html mostrava "Control" na topbar em ~6 telas de mídia."""
    _seed_loja()
    _enable_control(monkeypatch, dashboard=True)
    _login(client)
    _selecionar_loja(client)

    medicao = client.get("/app/trafego")
    assert medicao.status_code == 200
    assert "<h1>Medição</h1>" in medicao.text
    assert "<strong>Medição</strong>" in medicao.text  # topbar

    ctwa = client.get("/app/trafego/ctwa-auditoria")
    assert ctwa.status_code == 200
    assert "<h1>Cliques do WhatsApp</h1>" in ctwa.text
    assert "Auditoria CTWA" not in ctwa.text

    campanhas = client.get("/app/campanhas")
    assert campanhas.status_code == 200
    assert "<strong>Campanhas</strong>" in campanhas.text
