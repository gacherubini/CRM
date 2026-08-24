"""`responder` e `handoff-humano` na credencial de integração (spec §6.2).

São as duas rotas que hoje não carregam instância nenhuma — e sem elas o bot
nem responde nem entrega o lead. Com um token por loja isso passava; com um
workflow para N lojas, a resposta de uma loja sai pelo número da outra.

Nenhum número real aqui: tudo é rótulo sintético (``pnid-…``).
"""
import uuid

import pytest

from app import servico
from app.models_db import LojaOperacionalProjecao, WhatsAppCanal
from app.whatsapp_provider import ESTADO_CLOUD_ATIVO


class _OutboundFake:
    def __init__(self):
        self.textos = []

    def send_text(self, **kwargs):
        self.textos.append(kwargs)
        return {"messages": [{"id": "wamid.X"}]}

    def send_template_button(self, **kwargs):
        return {"messages": [{"id": "wamid.T"}]}

    def send_interactive_button(self, **kwargs):
        return {"messages": [{"id": "wamid.I"}]}


def _modo2(db, loja_id):
    db.add(
        LojaOperacionalProjecao(
            loja_id=loja_id, aggregate="whatsapp_modo", version=1,
            state="2", event_id=f"e-int-{uuid.uuid4().hex[:8]}",
        )
    )
    db.commit()


def _canal_cloud(db, loja_id):
    """Central Cloud da loja. O pnid mora em ``evolution_instance`` (reuso deliberado)."""
    pnid = f"pnid-int-{uuid.uuid4().hex[:8]}"
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()), loja_id=loja_id, e164_or_label="central",
            evolution_instance=pnid, ativo=True, estado=ESTADO_CLOUD_ATIVO,
            waba_id=f"waba-{uuid.uuid4().hex[:8]}", template_oferta=None,
        )
    )
    db.commit()
    return pnid


@pytest.fixture
def cenario(db, loja_a, loja_b, monkeypatch):
    """Duas lojas Cloud no mesmo processo — o cenário que o bug exige."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _modo2(db, loja_a["loja_id"])
    _modo2(db, loja_b["loja_id"])
    pnid_a = _canal_cloud(db, loja_a["loja_id"])
    pnid_b = _canal_cloud(db, loja_b["loja_id"])
    fake = _OutboundFake()
    monkeypatch.setattr("app.main.outbound_para_loja", lambda *a, **k: fake)
    yield {
        "a": {**loja_a, "pnid": pnid_a},
        "b": {**loja_b, "pnid": pnid_b},
        "fake": fake,
        "token": {"Authorization": f"Bearer {servico.criar_credencial_integracao(db)}"},
    }
    for projecao in (
        db.query(LojaOperacionalProjecao)
        .filter(LojaOperacionalProjecao.aggregate == "whatsapp_modo")
        .all()
    ):
        db.delete(projecao)
    for canal in db.query(WhatsAppCanal).filter(
        WhatsAppCanal.estado == ESTADO_CLOUD_ATIVO
    ).all():
        db.delete(canal)
    db.commit()


def test_responder_sai_pelo_numero_da_loja_da_instance(client, cenario):
    r = client.post(
        "/v1/operacao/responder",
        json={
            "telefone": "5511977720001",
            "texto": "oi",
            "instance": cenario["b"]["pnid"],
        },
        headers=cenario["token"],
    )

    assert r.status_code == 200, r.text
    assert r.json()["enviado"] is True
    assert cenario["fake"].textos[-1]["instance"] == cenario["b"]["pnid"]


def test_responder_com_integracao_sem_instance_e_400(client, cenario):
    """Fail-closed: sem instância, responder por 'alguma' loja é o bug de volta."""
    r = client.post(
        "/v1/operacao/responder",
        json={"telefone": "5511977720002", "texto": "oi"},
        headers=cenario["token"],
    )

    assert r.status_code == 400


def test_responder_com_token_de_loja_segue_sem_instance(client, cenario):
    """Expand-only: o corpo de hoje, sem instância, continua valendo."""
    r = client.post(
        "/v1/operacao/responder",
        json={"telefone": "5511977720003", "texto": "oi"},
        headers=cenario["a"]["headers"],
    )

    assert r.status_code == 200, r.text
    assert cenario["fake"].textos[-1]["instance"] == cenario["a"]["pnid"]


def test_handoff_com_integracao_aciona_na_loja_da_instance(client, db, cenario):
    r = client.post(
        "/v1/operacao/handoff-humano",
        json={"telefone": "5511977720004", "instance": cenario["b"]["pnid"]},
        headers=cenario["token"],
    )

    assert r.status_code == 202, r.text
    assert r.json().get("motivo") != "loja_fora_do_modo_2"


def test_handoff_com_integracao_sem_instance_e_400(client, cenario):
    r = client.post(
        "/v1/operacao/handoff-humano",
        json={"telefone": "5511977720005"},
        headers=cenario["token"],
    )

    assert r.status_code == 400
