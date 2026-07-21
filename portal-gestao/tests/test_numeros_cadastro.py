"""BFF de números de cadastro: cliente Chatbot e página do Portal."""
from __future__ import annotations

import httpx

from app.clients.chatbot import ChatbotClient
from conftest import csrf_da_resposta, login


def _instalar_transporte(monkeypatch, handler) -> None:
    transporte = httpx.MockTransport(handler)
    cliente_original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return cliente_original(*args, **kwargs)

    monkeypatch.setattr("app.clients.chatbot.httpx.Client", fabrica)


def test_listar_numeros_cadastro(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/operacao/numeros-autorizados"
        assert request.method == "GET"
        return httpx.Response(
            200, json={"numeros": [{"telefone": "5511999", "nome": "Ana", "ativo": True}]}
        )

    _instalar_transporte(monkeypatch, handler)
    cliente = ChatbotClient("http://chatbot", "tok", retries=0)
    assert cliente.listar_numeros_cadastro()[0]["nome"] == "Ana"


def test_adicionar_numero_cadastro(monkeypatch):
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/operacao/numeros-autorizados"
        assert request.method == "POST"
        import json

        capturado.update(json.loads(request.content))
        return httpx.Response(201, json={"telefone": "5511999", "nome": "Ana", "ativo": True})

    _instalar_transporte(monkeypatch, handler)
    cliente = ChatbotClient("http://chatbot", "tok", retries=0)
    cliente.adicionar_numero_cadastro("5511999", "Ana")
    assert capturado["telefone"] == "5511999"
    assert capturado["nome"] == "Ana"


def test_remover_numero_cadastro(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v1/operacao/numeros-autorizados/5511999"
        return httpx.Response(200, json={"removido": True})

    _instalar_transporte(monkeypatch, handler)
    cliente = ChatbotClient("http://chatbot", "tok", retries=0)
    assert cliente.remover_numero_cadastro("5511999")["removido"] is True


def test_pagina_lista_numeros(client, chatbot_fake):
    login(client)
    chatbot_fake.numeros_cadastro = [
        {"telefone": "5511988887777", "nome": "Ana", "ativo": True}
    ]
    r = client.get("/app/operacao/numeros")
    assert r.status_code == 200
    assert "Ana" in r.text


def test_pagina_adiciona_numero(client, chatbot_fake):
    login(client)
    pagina = client.get("/app/operacao/numeros")
    r = client.post(
        "/app/operacao/numeros",
        data={
            "csrf": csrf_da_resposta(pagina),
            "telefone": "5511977776666",
            "nome": "Bruno",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert chatbot_fake.numeros_cadastro[0]["telefone"] == "5511977776666"
    assert chatbot_fake.numeros_cadastro[0]["nome"] == "Bruno"


def test_pagina_remove_numero(client, chatbot_fake):
    login(client)
    chatbot_fake.numeros_cadastro = [
        {"telefone": "5511977776666", "nome": "Bruno", "ativo": True}
    ]
    pagina = client.get("/app/operacao/numeros")
    r = client.post(
        "/app/operacao/numeros/remover",
        data={"csrf": csrf_da_resposta(pagina), "telefone": "5511977776666"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert chatbot_fake.numeros_cadastro == []
