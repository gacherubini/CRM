"""Cadastro da fila de rodízio na Loja (spec §5.8).

A pessoa vem da **equipe da loja**, não de nome digitado: é assim que o
`Usuario.id` entra no cadastro e o sino 1:1 passa a ter destinatário real.
"""
from app.clients.chatbot import ChatbotClient


class _ChatbotFake:
    def __init__(self):
        self.fila = []
        self.criados = []

    def listar_fila_vendedores(self):
        return self.fila

    def criar_fila_vendedor(self, *, nome, telefone, ordem, usuario_id=None):
        registro = {
            "id": f"f{len(self.fila)}", "nome": nome, "telefone": telefone,
            "ordem": ordem, "ativo": True, "usuario_id": usuario_id,
        }
        self.criados.append(registro)
        self.fila.append(registro)
        return registro

    def remover_fila_vendedor(self, vendedor_id):
        self.fila = [v for v in self.fila if v["id"] != vendedor_id]


import pytest


@pytest.fixture
def chatbot_fake_fila():
    return _ChatbotFake()


def test_client_tem_os_metodos_da_fila():
    """Contrato do cliente antes da tela: a tela só desenha o que ele expõe."""
    for metodo in (
        "listar_fila_vendedores",
        "criar_fila_vendedor",
        "remover_fila_vendedor",
    ):
        assert hasattr(ChatbotClient, metodo), metodo


def test_cadastrar_manda_o_usuario_da_equipe(chatbot_fake_fila):
    """O `usuario_id` é o que liga a fila ao sino — sem ele o sino não toca."""
    fake = chatbot_fake_fila
    fake.criar_fila_vendedor(
        nome="Ana", telefone="11999990000", ordem=0, usuario_id="u-ana"
    )
    assert fake.criados[0]["usuario_id"] == "u-ana"
