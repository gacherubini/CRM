from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import login

from app.config import settings as portal_settings
from app.main import app, get_chatbot_client
from app.loja import routes as loja_routes  # noqa: F401  (garante registro das rotas)


@pytest.fixture
def atendimento_on(monkeypatch):
    enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)
    yield


class _FakeChatbot:
    def __init__(self, resumo=None, indisponivel=False):
        self._resumo = resumo
        self._indisponivel = indisponivel

    def resumo_atendimento(self, desde=None, ate=None):
        if self._indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel

            raise ChatbotIndisponivel("offline")
        return self._resumo


def _override(fake):
    app.dependency_overrides[get_chatbot_client] = lambda: fake


def teardown_function():
    app.dependency_overrides.pop(get_chatbot_client, None)


def test_agente_flag_off_404(client):
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 404


def test_agente_mostra_cards(client, atendimento_on):
    _override(
        _FakeChatbot(
            resumo={
                "atendimentos": 65,
                "transferidos": 38,
                "transferidos_pct": 0.58,
                "por_dia": [{"data": "2026-08-05", "atendimentos": 12}],
                "simulacoes": None,
            }
        )
    )
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "Agente de atendimento" in r.text
    assert "65" in r.text
    assert "Transferidos" in r.text
    assert "em construção" in r.text  # card de simulações placeholder


def test_agente_degrada_quando_chatbot_offline(client, atendimento_on):
    _override(_FakeChatbot(indisponivel=True))
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "indisponível" in r.text.lower()


def test_agente_mostra_divisao_entre_agente_e_handoff(client, atendimento_on):
    _override(
        _FakeChatbot(
            resumo={
                "atendimentos": 10,
                "transferidos": 4,
                "transferidos_pct": 0.4,
                "por_dia": [],
                "simulacoes": None,
            }
        )
    )
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "Só com o agente" in r.text
    assert "<strong>6</strong>" in r.text  # 10 atendimentos - 4 transferidos
    assert "40% das conversas" in r.text


def test_agente_sem_atendimentos_mostra_estado_vazio(client, atendimento_on):
    _override(
        _FakeChatbot(
            resumo={
                "atendimentos": 0,
                "transferidos": 0,
                "transferidos_pct": None,
                "por_dia": [],
                "simulacoes": None,
            }
        )
    )
    login(client)
    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "Nenhum atendimento neste mês." in r.text
    assert "split-bar" not in r.text


def test_visao_agente_preenche_dias_sem_atendimento():
    """por_dia do Chatbot só traz dias com conversa; a série tem de ter todos."""
    from datetime import date

    from app.loja.routes import montar_visao_agente

    visao = montar_visao_agente(
        {
            "atendimentos": 10,
            "transferidos": 4,
            "transferidos_pct": 0.4,
            "por_dia": [
                {"data": "2026-08-01", "atendimentos": 6},
                {"data": "2026-08-03", "atendimentos": 4},
            ],
        },
        date(2026, 8, 3),
    )
    assert [d["dia"] for d in visao["serie"]] == ["01", "02", "03"]
    assert [d["atendimentos"] for d in visao["serie"]] == [6, 0, 4]
    assert [d["altura"] for d in visao["serie"]] == [100, 0, 67]
    assert visao["so_agente"] == 6
    assert visao["maximo"] == 6
    assert visao["pico"]["dia"] == "01"


def test_visao_agente_sem_resumo():
    from datetime import date

    from app.loja.routes import montar_visao_agente

    assert montar_visao_agente(None, date(2026, 8, 3)) is None
