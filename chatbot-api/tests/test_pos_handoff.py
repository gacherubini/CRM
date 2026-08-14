from datetime import datetime, timedelta, timezone

import pytest

from app.models_db import FilaVendedor
from app.pos_handoff import cliente_voltou_a_escrever
from app.rodizio import abrir_oferta, assumir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _OutboundFake:
    def __init__(self):
        self.textos = []
        self.templates = []

    def send_text(self, **kwargs):
        self.textos.append(kwargs)
        return {}

    def send_template_button(self, **kwargs):
        self.templates.append(kwargs)
        return {}

    def send_interactive_button(self, **kwargs):
        self.textos.append(kwargs)
        return {}


def _travado(db, loja_id):
    db.add(FilaVendedor(
        id=f"{loja_id[:8]}-f0", loja_id=loja_id, nome="Ana",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()
    oferta = abrir_oferta(db, loja_id, "5511988887777")
    assumir_oferta(db, oferta.id)
    return oferta


def test_primeiro_retorno_avisa_o_cliente_com_nome_do_vendedor(db, loja_a):
    _travado(db, loja_a["loja_id"])
    fake = _OutboundFake()

    assert cliente_voltou_a_escrever(
        db, loja_a["loja_id"], "5511988887777", outbound=fake
    ) == "avisou_cliente"
    assert "Ana" in fake.textos[0]["text"]


def test_segundo_retorno_em_menos_de_6h_fica_em_silencio(db, loja_a):
    _travado(db, loja_a["loja_id"])
    fake = _OutboundFake()

    cliente_voltou_a_escrever(db, loja_a["loja_id"], "5511988887777", outbound=fake)
    resultado = cliente_voltou_a_escrever(db, loja_a["loja_id"], "5511988887777", outbound=fake)

    assert resultado == "silencio"
    assert len(fake.textos) == 1


def test_nunca_gasta_template_na_renotificacao(db, loja_a):
    """Spec §5.4: re-notificação só em envelope grátis."""
    _travado(db, loja_a["loja_id"])
    fake = _OutboundFake()

    cliente_voltou_a_escrever(db, loja_a["loja_id"], "5511988887777", outbound=fake)

    assert fake.templates == []
