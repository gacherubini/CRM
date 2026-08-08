"""Entrega do tracking pendente quando o mesmo telefone tem varias conversas.

`Conversa` e unica por `(canal_id, telefone)` com `canal_id` nullable, entao o
mesmo cliente pode ter uma linha por canal. A loja tem 7 canais e 492 conversas
para 243 identidades — um mesmo cliente ja apareceu em 3 canais em 2 dias.

Dois defeitos:
1. `_vincular_tracking_pendente_ao_lead` pegava a conversa com `.first()`, sem
   filtrar canal e sem ordenar: podia pegar justamente a que nao tem pendente.
2. Quando o lead ja existia, o pendente nunca era consumido.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.models_db import Conversa, Lead
from app.servico import _vincular_tracking_pendente_ao_lead, registrar_lead

TELEFONE = "5511977776666"
BASE = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)


def _conversa(db, loja_id, *, criada_em, pendente=None, telefone=TELEFONE) -> Conversa:
    conversa = Conversa(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        canal_id=None,
        telefone=telefone,
        criada_em=criada_em,
        atualizada_em=criada_em,
        tracking_pendente_json=json.dumps(pendente) if pendente else None,
    )
    db.add(conversa)
    db.flush()
    return conversa


def _lead(db, loja_id) -> Lead:
    lead = Lead(id=str(uuid.uuid4()), loja_id=loja_id, telefone=TELEFONE, etapa="novo")
    db.add(lead)
    db.flush()
    return lead


def test_pendente_e_encontrado_mesmo_com_conversa_sem_tracking_na_frente(db, loja_a):
    """A conversa sem pendente e criada PRIMEIRO: com .first() ela ganhava."""
    loja_id = loja_a["loja_id"]
    _conversa(db, loja_id, criada_em=BASE)  # sem pendente, mais antiga
    _conversa(
        db,
        loja_id,
        criada_em=BASE + timedelta(hours=1),
        pendente={"meta_ad_id": "120249613359810224", "ctwa_source_type": "FB_Ads"},
    )
    lead = _lead(db, loja_id)

    _vincular_tracking_pendente_ao_lead(db, loja_id, TELEFONE, lead)

    assert lead.meta_ad_id == "120249613359810224"
    assert lead.origem == "meta_ctwa"


def test_first_vem_da_conversa_mais_antiga(db, loja_a):
    """Ordem ASC e obrigatoria: aplicar_touch_ctwa so grava _first quando e nulo."""
    loja_id = loja_a["loja_id"]
    # Inseridas fora de ordem de propósito: quem manda é criada_em, não o insert.
    _conversa(
        db,
        loja_id,
        criada_em=BASE + timedelta(days=2),
        pendente={"meta_ad_id": "999", "meta_ad_id_first": "999"},
    )
    _conversa(
        db,
        loja_id,
        criada_em=BASE,
        pendente={"meta_ad_id": "111", "meta_ad_id_first": "111"},
    )
    lead = _lead(db, loja_id)

    _vincular_tracking_pendente_ao_lead(db, loja_id, TELEFONE, lead)

    assert lead.meta_ad_id_first == "111", "first vem da conversa mais antiga"
    assert lead.meta_ad_id == "999", "last vem da mais recente"


def test_pendente_de_todas_as_conversas_e_consumido(db, loja_a):
    loja_id = loja_a["loja_id"]
    a = _conversa(db, loja_id, criada_em=BASE, pendente={"ctwa_clid": "ARAclickAntigo"})
    b = _conversa(
        db,
        loja_id,
        criada_em=BASE + timedelta(hours=2),
        pendente={"meta_ad_id": "120249613359810224"},
    )
    lead = _lead(db, loja_id)

    _vincular_tracking_pendente_ao_lead(db, loja_id, TELEFONE, lead)

    assert lead.ctwa_clid == "ARAclickAntigo"
    assert lead.meta_ad_id == "120249613359810224"
    assert a.tracking_pendente_json is None, "pendente consumido nao pode reaparecer"
    assert b.tracking_pendente_json is None


def test_conversa_de_outro_telefone_nao_vaza(db, loja_a):
    loja_id = loja_a["loja_id"]
    _conversa(
        db,
        loja_id,
        criada_em=BASE,
        telefone="5511900000000",
        pendente={"meta_ad_id": "nao-e-desse-cliente"},
    )
    lead = _lead(db, loja_id)

    _vincular_tracking_pendente_ao_lead(db, loja_id, TELEFONE, lead)

    assert lead.meta_ad_id is None


def test_sem_pendente_e_no_op(db, loja_a):
    loja_id = loja_a["loja_id"]
    _conversa(db, loja_id, criada_em=BASE)
    lead = _lead(db, loja_id)

    _vincular_tracking_pendente_ao_lead(db, loja_id, TELEFONE, lead)

    assert lead.meta_ad_id is None
    assert lead.origem is None


def test_registrar_lead_existente_consome_o_pendente(db, loja_a):
    """POST /v1/leads sobre lead que ja existia tambem tem que colher o sinal."""
    loja_id = loja_a["loja_id"]
    conversa = _conversa(
        db,
        loja_id,
        criada_em=BASE,
        pendente={"meta_ad_id": "120249613359810224", "ctwa_source_type": "FB_Ads"},
    )
    _lead(db, loja_id)
    db.commit()

    lead = registrar_lead(db, loja_id, TELEFONE, etapa="qualificado")

    assert lead.meta_ad_id == "120249613359810224"
    assert lead.origem == "meta_ctwa"
    db.refresh(conversa)
    assert conversa.tracking_pendente_json is None


def test_webhook_com_lead_ja_existente_consome_o_pendente(client, loja_a, db):
    """O ramo idempotente do webhook lia o id do lead e largava o pendente la.

    Caminho real: 1a msg traz o anuncio (pendente na conversa, sem lead); o lead
    nasce por outro caminho; a 2a msg chega SEM sinal — cai no ramo do lead ja
    existente e, antes, ia embora sem colher nada.
    """
    inst, headers = loja_a["instance"], loja_a["headers"]
    telefone = "5511955554444"

    r1 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": telefone, "texto": "oi",
        "provider_message_id": "pend-1", "from_me": False,
        "ctwa_clid": "ARclidPend", "meta_ad_id": "120252470707220341"})
    assert r1.status_code == 200
    assert r1.json().get("ctwa_pendente") is True

    # Lead nasce sem passar por registrar_lead (nao consome o pendente).
    lead = Lead(
        id=str(uuid.uuid4()), loja_id=loja_a["loja_id"], telefone=telefone, etapa="novo"
    )
    db.add(lead)
    db.commit()

    r2 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": telefone, "texto": "quero saber o preço",
        "provider_message_id": "pend-2", "from_me": False})
    assert r2.status_code == 200

    salvo = client.get("/v1/leads", headers=headers).json()["leads"]
    alvo = next(l for l in salvo if l["telefone"] == telefone)
    assert alvo["meta_ad_id"] == "120252470707220341"
    assert alvo["ctwa_clid"] == "ARclidPend"
    assert alvo["origem"] == "meta_ctwa"
