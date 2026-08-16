from dataclasses import replace

from conftest import login

from app.config import settings as portal_settings
from app.main import app, get_chatbot_client


class _ChatbotAtend:
    def __init__(self, esgotadas=None, indisponivel=False):
        self.esgotadas = esgotadas or []
        self.indisponivel = indisponivel

    def listar_leads(self):
        if self.indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel
            raise ChatbotIndisponivel("offline")
        return []

    def listar_conversas(self, limit=100, canal_id=None):
        if self.indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel
            raise ChatbotIndisponivel("offline")
        return []

    def listar_canais_whatsapp(self):
        return []

    def listar_ofertas(self, estado=None):
        if self.indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel
            raise ChatbotIndisponivel("offline")
        if estado == "esgotada":
            return self.esgotadas
        return []


def _ligar(monkeypatch):
    enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)


def _override(fake):
    app.dependency_overrides[get_chatbot_client] = lambda: fake


def teardown_function():
    app.dependency_overrides.pop(get_chatbot_client, None)


def test_dono_ve_faixa_com_contagem(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono-faixa@loja.test")
    _override(_ChatbotAtend(esgotadas=[
        {"id": "of-a", "telefone_cliente": "5511111111111", "estado": "esgotada"},
        {"id": "of-b", "telefone_cliente": "5511222222222", "estado": "esgotada"},
    ]))

    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "2 sem vendedor" in r.text
    assert "estado=aguardando_vendedor" in r.text


def test_vendedor_nao_ve_faixa(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="vend-faixa@loja.test")
    _override(_ChatbotAtend(esgotadas=[
        {"id": "of-a", "telefone_cliente": "5511111111111", "estado": "esgotada"},
    ]))

    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "sem vendedor" not in r.text


def test_filtro_aguardando_lista_esgotadas(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono-filtro@loja.test")
    _override(_ChatbotAtend(esgotadas=[
        {"id": "of-a", "telefone_cliente": "5511988887777", "estado": "esgotada"},
    ]))

    r = client.get("/app/loja/atendimento", params={"estado": "aguardando_vendedor"})
    assert r.status_code == 200
    assert "5511988887777" in r.text or "8888-7777" in r.text or "8777" in r.text


def test_modo1_sem_ofertas_nao_mostra_faixa(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono-m1@loja.test")
    _override(_ChatbotAtend(esgotadas=[]))

    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "sem vendedor" not in r.text


def test_chatbot_fora_nao_derruba_pagina(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono-off@loja.test")
    _override(_ChatbotAtend(indisponivel=True))

    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "sem vendedor" not in r.text
    assert "Dados parciais" in r.text or "atendimento" in r.text.lower()
