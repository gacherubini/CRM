import pytest

from app.handoff_gatilhos import disparar_handoff
from app.models_db import FilaVendedor, OfertaLead


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _OutboundFake:
    def __init__(self):
        self.enviados = []

    def send_text(self, **kwargs):
        self.enviados.append(kwargs)
        return {}

    def send_template_button(self, **kwargs):
        self.enviados.append(kwargs)
        return {}

    def send_interactive_button(self, **kwargs):
        self.enviados.append(kwargs)
        return {}


def _fila(db, loja_id, quantos=2):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"{loja_id[:8]}-f{i}", loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
    db.commit()


def _abertas(db, loja_id):
    return (
        db.query(OfertaLead)
        .filter(OfertaLead.loja_id == loja_id, OfertaLead.estado == "aberta")
        .count()
    )


@pytest.mark.parametrize(
    "motivo", ["simulacao_pronta", "simulacao_falhou", "pediu_humano"]
)
def test_os_tres_gatilhos_abrem_oferta(db, loja_a, motivo):
    _fila(db, loja_a["loja_id"])

    resultado = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo=motivo, outbound=_OutboundFake(),
    )

    assert resultado == "ofertado"
    assert _abertas(db, loja_a["loja_id"]) == 1


def test_sem_vendedor_vira_aguardando_e_avisa_o_cliente(db, loja_a):
    fake = _OutboundFake()

    resultado = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo="pediu_humano", outbound=fake,
    )

    assert resultado == "aguardando"
    assert any("5511988887777" == e.get("number") for e in fake.enviados)


def test_segundo_gatilho_no_mesmo_lead_nao_duplica(db, loja_a):
    _fila(db, loja_a["loja_id"])
    fake = _OutboundFake()

    disparar_handoff(db, loja_a["loja_id"], "5511988887777", motivo="pediu_humano", outbound=fake)
    segundo = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777", motivo="simulacao_pronta", outbound=fake
    )

    assert segundo == "ja_em_andamento"
    assert _abertas(db, loja_a["loja_id"]) == 1
