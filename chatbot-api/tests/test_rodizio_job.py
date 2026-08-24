from datetime import datetime, timedelta, timezone

import pytest

from app.models_db import FilaVendedor, LojaOperacionalProjecao, OfertaLead
from app.rodizio import abrir_oferta
from app.rodizio_job import RodizioWorker


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch, db, loja_a):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    db.add(LojaOperacionalProjecao(
        loja_id=loja_a["loja_id"], aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-modo-{loja_a['loja_id'][:8]}",
    ))
    db.commit()


def _fila(db, loja_id, quantos):
    ids = []
    for i in range(quantos):
        vid = f"{loja_id[:8]}-f{i}"
        db.add(FilaVendedor(
            id=vid, loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
        ids.append(vid)
    db.commit()
    return ids


class _OutboundFake:
    """`run_once` exige outbound: sem ele a reoferta não sai do banco.

    Aqui ele é só o mínimo para o worker rodar — quem prova que a mensagem
    chega ao vendedor é `test_rodizio_reoferta_envio.py`.
    """

    def __init__(self):
        self.textos = []
        self.ofertas = []

    def send_text(self, **kwargs):
        self.textos.append(kwargs)
        return {"messages": [{"id": "wamid.X"}]}

    def send_template_button(self, **kwargs):
        self.ofertas.append(kwargs)
        return {"messages": [{"id": "wamid.T"}]}

    def send_interactive_button(self, **kwargs):
        self.ofertas.append(kwargs)
        return {"messages": [{"id": "wamid.I"}]}


def _vencer(db, oferta):
    oferta.prazo_em = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()


def test_oferta_vencida_passa_para_o_proximo(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db, outbound=_OutboundFake())

    assert resultado["expiradas"] == 1
    assert resultado["reofertadas"] == 1
    nova = (
        db.query(OfertaLead)
        .filter(OfertaLead.estado == "aberta", OfertaLead.loja_id == loja_a["loja_id"])
        .one()
    )
    assert nova.vendedor_id != oferta.vendedor_id


def test_volta_completa_esgota(db, loja_a):
    _fila(db, loja_a["loja_id"], 1)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db, outbound=_OutboundFake())

    assert resultado["esgotadas"] == 1
    assert (
        db.query(OfertaLead)
        .filter(OfertaLead.estado == "aberta", OfertaLead.loja_id == loja_a["loja_id"])
        .count()
        == 0
    )


def test_oferta_travada_nao_expira(db, loja_a):
    """Pegou e não ligou: fica travado, não volta para a fila (spec §5.3)."""
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    oferta.estado = "travada"
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db, outbound=_OutboundFake())

    assert resultado["expiradas"] == 0
