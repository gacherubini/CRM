"""PATCH /v1/conversas/{telefone}/estado na credencial de integração (spec §6.2).

Sem resolver a loja pela instância, o pause do handoff caía em 404
"instância não reconhecida" — `ctx.loja_id` é None na integração e o canal
nunca bate. Foi o que calou o handoff do Modo 2 no smoke e2e de 18/09: a tool
`solicitar_handoff1` pausa antes de abrir o rodízio, e o catch dela virava o
"não consegui encaminhar agora".

Nenhum número real aqui: tudo é rótulo sintético (``pnid-…``).
"""
import uuid

import pytest

from app import servico
from app.models_db import Conversa, LojaOperacionalProjecao, WhatsAppCanal
from app.whatsapp_provider import ESTADO_CLOUD_ATIVO


def _canal_cloud(db, loja_id):
    pnid = f"pnid-est-{uuid.uuid4().hex[:8]}"
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
def cenario(db, loja_a, loja_b):
    """Duas lojas Cloud no mesmo processo — o cenário que o bug exige."""
    pnid_a = _canal_cloud(db, loja_a["loja_id"])
    pnid_b = _canal_cloud(db, loja_b["loja_id"])
    yield {
        "a": {**loja_a, "pnid": pnid_a},
        "b": {**loja_b, "pnid": pnid_b},
        "token": {"Authorization": f"Bearer {servico.criar_credencial_integracao(db)}"},
    }
    db.query(Conversa).filter(
        Conversa.telefone.like("5511977720%")
    ).delete(synchronize_session=False)
    for canal in db.query(WhatsAppCanal).filter(
        WhatsAppCanal.estado == ESTADO_CLOUD_ATIVO
    ).all():
        db.delete(canal)
    db.commit()


def test_pause_com_integracao_pausa_na_loja_da_instance(client, db, cenario):
    tel = "5511977720101"
    r = client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": False, "instance": cenario["b"]["pnid"]},
        headers=cenario["token"],
    )

    assert r.status_code == 200, r.text
    assert r.json()["bot_ativo"] is False
    conversa = (
        db.query(Conversa)
        .filter(Conversa.loja_id == cenario["b"]["loja_id"], Conversa.telefone == tel)
        .one()
    )
    assert conversa.bot_ativo is False
    assert conversa.status == "handoff"
    assert (
        db.query(Conversa)
        .filter(Conversa.loja_id == cenario["a"]["loja_id"], Conversa.telefone == tel)
        .count()
    ) == 0


def test_pause_com_integracao_sem_instance_e_400(client, cenario):
    r = client.patch(
        "/v1/conversas/5511977720102/estado",
        json={"bot_ativo": False},
        headers=cenario["token"],
    )

    assert r.status_code == 400


def test_pause_com_token_de_loja_segue_sem_instance(client, cenario):
    """Expand-only: o corpo de hoje, sem instância, continua valendo."""
    r = client.patch(
        "/v1/conversas/5511977720103/estado",
        json={"bot_ativo": False},
        headers=cenario["a"]["headers"],
    )

    assert r.status_code == 200, r.text
    assert r.json()["bot_ativo"] is False
