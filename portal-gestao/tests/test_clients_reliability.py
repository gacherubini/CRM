from __future__ import annotations

import httpx
import pytest

from app.clients._retry import requisicao_com_retry
from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel
from app.clients.estoque import EstoqueClient, EstoqueIndisponivel


def _instalar_transporte(monkeypatch, modulo: str, handler) -> None:
    transporte = httpx.MockTransport(handler)
    cliente_original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return cliente_original(*args, **kwargs)

    monkeypatch.setattr(f"{modulo}.httpx.Client", fabrica)


def test_chatbot_repete_get_transitorio_com_backoff_sem_sleep_real(monkeypatch):
    tentativas = 0
    esperas: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tentativas
        tentativas += 1
        if tentativas == 1:
            return httpx.Response(503, json={"detail": "temporário"})
        return httpx.Response(200, json={"leads": [{"id": "l1"}]})

    _instalar_transporte(monkeypatch, "app.clients.chatbot", handler)
    cliente = ChatbotClient(
        "http://chatbot",
        "token-privado",
        retries=2,
        retry_backoff=0.25,
        sleeper=esperas.append,
    )

    assert cliente.listar_leads() == [{"id": "l1"}]
    assert tentativas == 2
    assert esperas == [0.25]


def test_estoque_repete_get_apos_falha_de_transporte(monkeypatch):
    tentativas = 0
    esperas: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tentativas
        tentativas += 1
        if tentativas < 3:
            raise httpx.ConnectError("indisponível", request=request)
        return httpx.Response(200, json={"veiculos": []})

    _instalar_transporte(monkeypatch, "app.clients.estoque", handler)
    cliente = EstoqueClient(
        "http://estoque",
        "token-privado",
        retries=2,
        retry_backoff=0.1,
        sleeper=esperas.append,
    )

    assert cliente.listar() == []
    assert tentativas == 3
    assert esperas == [0.1, 0.2]


def test_chatbot_nao_repete_patch_sem_chave_idempotente(monkeypatch):
    tentativas = 0
    esperas: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tentativas
        tentativas += 1
        return httpx.Response(503, json={"detail": "temporário"})

    _instalar_transporte(monkeypatch, "app.clients.chatbot", handler)
    cliente = ChatbotClient(
        "http://chatbot",
        "token-privado",
        retries=3,
        retry_backoff=0.1,
        sleeper=esperas.append,
    )

    with pytest.raises(ChatbotIndisponivel):
        cliente.definir_bot_ativo("5511999999999", False)

    assert tentativas == 1
    assert esperas == []


def test_estoque_nao_repete_post_sem_chave_idempotente(monkeypatch):
    tentativas = 0
    esperas: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tentativas
        tentativas += 1
        return httpx.Response(503, json={"detail": "temporário"})

    _instalar_transporte(monkeypatch, "app.clients.estoque", handler)
    cliente = EstoqueClient(
        "http://estoque",
        "token-privado",
        retries=3,
        retry_backoff=0.1,
        sleeper=esperas.append,
    )

    with pytest.raises(EstoqueIndisponivel):
        cliente.criar({"placa": "AAA0A00"})

    assert tentativas == 1
    assert esperas == []


def test_write_so_repete_com_chave_idempotente_explicita():
    tentativas = 0
    esperas: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tentativas
        tentativas += 1
        if tentativas == 1:
            return httpx.Response(503)
        return httpx.Response(201, json={"id": "v1"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resposta = requisicao_com_retry(
            client,
            "POST",
            "http://estoque/v1/veiculos",
            retries=1,
            backoff=0.2,
            sleeper=esperas.append,
            headers={"Idempotency-Key": "operacao-1"},
            json={"placa": "AAA0A00"},
        )

    assert resposta.status_code == 201
    assert tentativas == 2
    assert esperas == [0.2]


def test_falha_final_expoe_apenas_mensagem_publica_sanitizada(monkeypatch):
    segredo = "token-nao-pode-vazar"
    telefone = "5511987654321"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": segredo})

    _instalar_transporte(monkeypatch, "app.clients.chatbot", handler)
    cliente = ChatbotClient(
        "http://interno.example",
        segredo,
        retries=1,
        retry_backoff=0,
        sleeper=lambda _: None,
    )

    with pytest.raises(ChatbotIndisponivel) as capturada:
        cliente.obter_estado(telefone)

    mensagem = str(capturada.value)
    assert mensagem == "Não foi possível acessar o chatbot agora"
    assert segredo not in mensagem
    assert telefone not in mensagem
    assert "interno.example" not in mensagem
    assert capturada.value.__cause__ is None
