"""O portao do Control (spec §9).

Liberar a loja e projetar whatsapp_modo=2. O canal Cloud que nasceu pendente
vira ativo junto — uma decisao, um lugar, sem segunda rota de escrita.
"""
import uuid

from app import provisioning
from app.models_db import WhatsAppCanal


def _canal_pendente(db, loja_id, instance):
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label="linha-cloud",
        evolution_instance=instance,
        waba_id="waba-1",
        estado="cloud_pendente",
    )
    db.add(canal)
    db.commit()
    return canal


def test_projecao_modo_2_ativa_o_canal_pendente(db, loja_a):
    canal = _canal_pendente(db, loja_a["loja_id"], "1227059273831584")

    resultado = provisioning._apply_envelope(
        db,
        loja_a["loja_id"],
        {"version": 99, "state": "2", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert resultado == "applied"
    assert canal.estado == "cloud_ativo"


def test_projecao_modo_1_nao_mexe_no_canal(db, loja_a):
    """Modo 1 nao desativa: quem barra o Modo 2 e loja_opera_modo2, que ja le a
    projecao. Mexer no canal aqui seria um segundo gate dizendo a mesma coisa."""
    canal = _canal_pendente(db, loja_a["loja_id"], "1227059273831585")

    provisioning._apply_envelope(
        db,
        loja_a["loja_id"],
        {"version": 99, "state": "1", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert canal.estado == "cloud_pendente"


def test_envelope_velho_nao_ativa(db, loja_b):
    """Stale nao aplica projecao, entao nao pode ativar canal tambem."""
    canal = _canal_pendente(db, loja_b["loja_id"], "1227059273831586")
    provisioning._apply_envelope(
        db,
        loja_b["loja_id"],
        {"version": 99, "state": "1", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()

    resultado = provisioning._apply_envelope(
        db,
        loja_b["loja_id"],
        {"version": 2, "state": "2", "event_id": "e0"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert resultado == "stale"
    assert canal.estado == "cloud_pendente"


def test_loja_sem_canal_nao_estoura(db, loja_sem_projecao):
    resultado = provisioning._apply_envelope(
        db,
        loja_sem_projecao["loja_id"],
        {"version": 99, "state": "2", "event_id": "e1"},
        "whatsapp_modo",
    )

    assert resultado == "applied"


def test_loja_ja_projetada_ativa_ao_virar_modo_2(db, loja_sem_projecao):
    """O caminho de UPDATE, que os testes acima nao alcancam.

    O conftest semeia projecao dos aggregates `loja`, `vendas` e `estoque` — nunca
    `whatsapp_modo`. Entao todo primeiro envelope de whatsapp_modo cai no INSERT, e
    sem este teste o gancho do caminho de update podia sumir sem ninguem ver.

    E o caso real da loja que ja opera no Modo 1 e e promovida: a projecao dela ja
    existe, e a liberacao passa pelo update.
    """
    canal = _canal_pendente(db, loja_sem_projecao["loja_id"], "1227059273831587")

    provisioning._apply_envelope(
        db,
        loja_sem_projecao["loja_id"],
        {"version": 1, "state": "1", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)
    assert canal.estado == "cloud_pendente", "modo 1 nao pode ativar nada"

    resultado = provisioning._apply_envelope(
        db,
        loja_sem_projecao["loja_id"],
        {"version": 2, "state": "2", "event_id": "e2"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert resultado == "applied"
    assert canal.estado == "cloud_ativo"
