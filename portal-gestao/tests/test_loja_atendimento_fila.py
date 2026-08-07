"""Fila de atendimento: tempo de espera e badge de canal legível nos dois temas."""
from datetime import datetime, timedelta, timezone

import pytest
from conftest import login

from app.main import tempo_relativo


@pytest.fixture
def atendimento_on(monkeypatch):
    from dataclasses import replace

    from app.config import settings as portal_settings

    enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)
    yield


def test_tempo_relativo_cobre_as_faixas():
    agora = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    def quando(**delta):
        return (agora - timedelta(**delta)).isoformat()

    assert tempo_relativo(quando(seconds=30), agora=agora) == "agora"
    assert tempo_relativo(quando(minutes=12), agora=agora) == "12 min"
    assert tempo_relativo(quando(hours=3), agora=agora) == "3 h"
    assert tempo_relativo(quando(days=2), agora=agora) == "2 d"
    assert tempo_relativo(quando(days=21), agora=agora) == "3 sem"
    assert tempo_relativo(None, agora=agora) == "—"
    assert tempo_relativo("nao-e-data", agora=agora) == "—"


def test_fila_mostra_quanto_o_cliente_esperou(client, atendimento_on):
    login(client)
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "Aguardando há" in r.text
    # O <style> inline escrito para o tema escuro saiu do template.
    assert "rgba(255,255,255,.08)" not in r.text
