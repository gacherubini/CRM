"""BFF de números de cadastro: cliente Chatbot e página do Portal."""
from __future__ import annotations

import httpx

from app.clients.chatbot import ChatbotClient
from tests.conftest import login


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
