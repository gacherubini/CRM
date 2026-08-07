"""Origem do lead no workspace de atendimento.

Nenhuma tela da Revy Loja dizia de qual anuncio a pessoa veio, embora o Portal
ja resolvesse a campanha do lead para gravar a atribuicao na venda.
"""
from __future__ import annotations

from conftest import login

from app.config import settings
from app.db import SessionLocal
from app.models import Campanha, novo_id


def _enable(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)
    object.__setattr__(settings, "revy_loja_atendimento_enabled", True)


def _criar_campanha(*, utm_campaign="seminovos-julho", nome="Promo de julho"):
    db = SessionLocal()
    campanha = Campanha(
        id=novo_id(),
        loja_slug="loja-teste",
        nome=nome,
        canal="meta",
        status="ativa",
        utm_campaign=utm_campaign,
        utm_campaign_norm=utm_campaign,
        criada_por_email="dono@loja.test",
    )
    db.add(campanha)
    db.commit()
    db.close()
    return campanha


def test_origem_do_lead_aparece_no_workspace(client, monkeypatch):
    _criar_campanha()
    _enable(monkeypatch)
    login(client)

    pagina = client.get("/app/loja/atendimento/5511987654321")

    assert pagina.status_code == 200
    assert "Promo de julho" in pagina.text


def test_workspace_sem_campanha_casada_nao_inventa_origem(client, monkeypatch):
    _enable(monkeypatch)
    login(client)

    pagina = client.get("/app/loja/atendimento/5511987654321")

    assert pagina.status_code == 200
    assert "Promo de julho" not in pagina.text
