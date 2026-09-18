import logging
import uuid

import pytest

from app.handoff_gatilhos import disparar_handoff
from app.models_db import (
    Conversa,
    FilaVendedor,
    LojaOperacionalProjecao,
    Mensagem,
    OfertaLead,
    WhatsAppCanal,
)
from app.whatsapp_provider import ESTADO_CLOUD_ATIVO


def _canal_cloud(db, loja_id):
    pnid = f"pnid-hg-{uuid.uuid4().hex[:8]}"
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()), loja_id=loja_id, e164_or_label="central",
            evolution_instance=pnid, ativo=True, estado=ESTADO_CLOUD_ATIVO,
            waba_id=f"waba-{uuid.uuid4().hex[:8]}", template_oferta=None,
        )
    )
    db.commit()
    return pnid


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch, db, loja_a):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    db.add(LojaOperacionalProjecao(
        loja_id=loja_a["loja_id"], aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-modo-{loja_a['loja_id'][:8]}",
    ))
    # O aviso ao cliente grava a saída na conversa: sem canal, resolver vaza 404.
    _canal_cloud(db, loja_a["loja_id"])
    db.commit()


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


def test_avisar_cliente_desligado_nao_manda_texto_mas_oferta_o_lead(db, loja_a):
    """Quem chamou vai falar com o cliente por conta própria (o agente do Modo 2)."""
    _fila(db, loja_a["loja_id"])
    fake = _OutboundFake()

    resultado = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo="pediu_humano", outbound=fake, avisar_cliente=False,
    )

    assert resultado == "ofertado"
    assert _abertas(db, loja_a["loja_id"]) == 1
    assert [e for e in fake.enviados if e.get("number") == "5511988887777"] == []


def test_avisar_cliente_desligado_e_sem_fila_segue_calado(db, loja_a):
    fake = _OutboundFake()

    resultado = disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo="pediu_humano", outbound=fake, avisar_cliente=False,
    )

    assert resultado == "aguardando"
    assert fake.enviados == []


def _textos_saida(db, loja_id, telefone):
    return [
        m.texto or ""
        for m in (
            db.query(Mensagem)
            .join(Conversa, Mensagem.conversa_id == Conversa.id)
            .filter(
                Conversa.loja_id == loja_id,
                Conversa.telefone == telefone,
                Mensagem.direcao == "saida",
            )
            .all()
        )
    ]


def test_aviso_ao_cliente_ofertado_gravado_na_conversa(db, loja_a):
    """O aviso chega no WhatsApp E no banco — sem a linha, o Portal mostra
    o histórico pela metade (aviso de 18/09 existiu só no aparelho)."""
    _fila(db, loja_a["loja_id"])

    disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo="pediu_humano", outbound=_OutboundFake(),
    )

    assert any(
        "chamando um vendedor" in t
        for t in _textos_saida(db, loja_a["loja_id"], "5511988887777")
    )


def test_aviso_ao_cliente_aguardando_gravado_na_conversa(db, loja_a):
    disparar_handoff(
        db, loja_a["loja_id"], "5511988887777",
        motivo="pediu_humano", outbound=_OutboundFake(),
    )

    assert any(
        "passando seu atendimento" in t
        for t in _textos_saida(db, loja_a["loja_id"], "5511988887777")
    )


def test_envio_da_oferta_deixa_rastro_de_envelope_no_log(db, loja_a, caplog):
    """Sem o rastro, "o vendedor foi chamado?" não tem resposta no log."""
    _fila(db, loja_a["loja_id"])

    with caplog.at_level(logging.INFO, logger="chatbot.handoff_gatilhos"):
        disparar_handoff(
            db, loja_a["loja_id"], "5511988887777",
            motivo="pediu_humano", outbound=_OutboundFake(),
        )

    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "oferta enviada" in registro
    assert "envelope=" in registro
