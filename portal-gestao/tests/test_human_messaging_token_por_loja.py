"""O envio do Atendimento tem de usar o token da loja da SESSÃO.

A tela usa dois clientes: `get_chatbot_client(request)`, que resolve o token
pela loja selecionada, e `get_human_messaging_port()`, que não recebia o
`Request` e usava o token global. Resultado em produção (29/08): o GET do
histórico respondia 200 pela loja `teste` e o POST do envio devolvia 404,
porque o chatbot via o `ctx.loja_id` do token fixo e o canal pertencia a outra
loja.

O 404 foi sorte: falhou fechado. Se o token fixo pertencesse a uma loja que
**tem** aquele canal, o portal mandaria a mensagem pela loja errada, sem erro —
que é o mesmo vazamento que `chatbot_token_para` existe para estancar.

Nenhum token real: valores sintéticos.
"""
import dataclasses
import json

import pytest

from app import config
from app.loja import routes as loja_routes

MAPA = json.dumps({"teste": "tok-teste", "moto-center": "tok-moto"})


class _RequestFake:
    """Só o que a dependência lê: a sessão."""

    def __init__(self, slug):
        self.session = {"loja_slug": slug} if slug else {}


@pytest.fixture(autouse=True)
def _mapa_de_tokens(monkeypatch):
    """`Settings` é dataclass congelada: troca-se o objeto, não o campo."""
    falso = dataclasses.replace(
        config.settings, chatbot_tokens_json=MAPA, chatbot_token="tok-global"
    )
    monkeypatch.setattr(loja_routes, "settings", falso)


def test_usa_o_token_da_loja_da_sessao():
    porta = loja_routes.get_human_messaging_port(_RequestFake("teste"))

    assert porta.token == "tok-teste"


def test_outra_loja_na_sessao_muda_o_token():
    """O defeito: as duas lojas recebiam o mesmo token global."""
    porta = loja_routes.get_human_messaging_port(_RequestFake("moto-center"))

    assert porta.token == "tok-moto"


def test_sessao_sem_loja_falha_fechado():
    """Sem slug, `chatbot_token_para` devolve "" e a porta fica desconfigurada.

    Melhor a tela dizer "indisponível" do que mandar mensagem pela loja errada.
    """
    porta = loja_routes.get_human_messaging_port(_RequestFake(None))

    assert porta.token == ""
    assert porta.configurado is False
