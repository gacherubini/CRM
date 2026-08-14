from datetime import datetime, timedelta, timezone

import pytest

from app.models_db import Conversa, FilaVendedor, Mensagem
from app.oferta_envio import enviar_oferta, janela_aberta
from app.rodizio import abrir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


def _inbound_do_vendedor(db, loja_id, telefone, *, horas_atras):
    """Inbound do vendedor = o que abre a janela de 24 h.

    Mensagem não tem telefone (models_db.py:103): o número mora na Conversa.
    """
    prefixo = loja_id[:8]
    conversa = Conversa(
        id=f"{prefixo}-c-{horas_atras}", loja_id=loja_id, telefone=telefone
    )
    db.add(conversa)
    db.add(Mensagem(
        id=f"{prefixo}-m-{horas_atras}", loja_id=loja_id, conversa_id=conversa.id,
        direcao="entrada", texto="peguei",
        criada_em=datetime.now(timezone.utc) - timedelta(hours=horas_atras),
    ))
    db.commit()


class _OutboundFake:
    def __init__(self):
        self.templates = []
        self.interativas = []

    def send_template_button(self, **kwargs):
        self.templates.append(kwargs)
        return {"messages": [{"id": "wamid.T"}]}

    def send_interactive_button(self, **kwargs):
        self.interativas.append(kwargs)
        return {"messages": [{"id": "wamid.I"}]}


def _fila(db, loja_id):
    db.add(FilaVendedor(
        id=f"{loja_id[:8]}-f0", loja_id=loja_id, nome="Ana",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()


def test_janela_fechada_usa_template(db, loja_a):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    assert enviar_oferta(db, oferta, outbound=fake) == "template"
    assert fake.templates[0]["oferta_id"] == oferta.id
    assert fake.interativas == []


def test_janela_aberta_usa_interativa(db, loja_a):
    _fila(db, loja_a["loja_id"])
    _inbound_do_vendedor(db, loja_a["loja_id"], "5511999990000", horas_atras=2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    assert enviar_oferta(db, oferta, outbound=fake) == "interativa"
    assert fake.templates == []


def test_inbound_de_25h_nao_abre_janela(db, loja_a):
    _inbound_do_vendedor(db, loja_a["loja_id"], "5511999990000", horas_atras=25)
    assert janela_aberta(db, loja_a["loja_id"], "5511999990000") is False


def test_oferta_nao_leva_wa_me(db, loja_a):
    """Spec §5.7: o contato do cliente só vai DEPOIS do clique."""
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    enviar_oferta(db, oferta, outbound=fake)

    enviado = str(fake.templates[0])
    assert "wa.me" not in enviado
    assert "5511988887777" not in enviado


def test_janela_abre_mesmo_sem_o_9o_digito(db, loja_a):
    """Bug de dinheiro: o `wa_id` da Meta costuma vir SEM o 9º dígito no Brasil.

    Comparando string crua, a janela parece sempre fechada e o Revy paga
    template em toda oferta em vez de um por vendedor por dia (spec §5.7/§9).
    """
    _inbound_do_vendedor(db, loja_a["loja_id"], "551199998888", horas_atras=2)
    assert janela_aberta(db, loja_a["loja_id"], "5511999998888") is True


def test_janela_abre_mesmo_sem_o_ddi(db, loja_a):
    _inbound_do_vendedor(db, loja_a["loja_id"], "11988887777", horas_atras=1)
    assert janela_aberta(db, loja_a["loja_id"], "5511988887777") is True


def test_numero_de_outro_vendedor_nao_abre_a_janela(db, loja_a):
    """A tolerância é de formato, não de identidade."""
    _inbound_do_vendedor(db, loja_a["loja_id"], "5511977776666", horas_atras=1)
    assert janela_aberta(db, loja_a["loja_id"], "5511999998888") is False
