import uuid
from datetime import datetime, timezone

from app import models_db


def _conversa(loja_id, status, quando):
    return models_db.Conversa(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone="5511900000000",
        bot_ativo=(status != "handoff"),
        status=status,
        criada_em=quando,
        atualizada_em=quando,
    )


def test_resumo_conta_atendimentos_e_handoff(client, db, loja_a):
    loja_id = loja_a["loja_id"]
    dia = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    db.add(_conversa(loja_id, "aberta", dia))
    db.add(_conversa(loja_id, "handoff", dia))
    db.add(_conversa(loja_id, "encerrada", dia))
    db.commit()

    r = client.get(
        "/v1/atendimento/resumo?desde=2026-08-01&ate=2026-09-01",
        headers=loja_a["headers"],
    )

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["atendimentos"] == 3
    assert corpo["transferidos"] == 1
    assert round(corpo["transferidos_pct"], 3) == round(1 / 3, 3)
    assert corpo["simulacoes"] is None
    assert {"data": "2026-08-05", "atendimentos": 3} in corpo["por_dia"]


def test_resumo_escopo_por_loja(client, db, loja_a, loja_b):
    dia = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    db.add(_conversa(loja_a["loja_id"], "aberta", dia))
    db.add(_conversa(loja_b["loja_id"], "aberta", dia))
    db.commit()

    r = client.get(
        "/v1/atendimento/resumo?desde=2026-08-01&ate=2026-09-01",
        headers=loja_a["headers"],
    )

    assert r.json()["atendimentos"] == 1  # só a loja A


def test_resumo_zero_atendimentos(client, loja_a):
    """When loja_a has zero conversas, verify zero count, None percentage, empty series."""
    r = client.get(
        "/v1/atendimento/resumo?desde=2026-08-01&ate=2026-09-01",
        headers=loja_a["headers"],
    )

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["atendimentos"] == 0
    assert corpo["transferidos"] == 0
    assert corpo["transferidos_pct"] is None
    assert corpo["por_dia"] == []
    assert corpo["simulacoes"] is None


def test_resumo_janela_default_e_datas_invalidas(client, db, loja_a):
    """Test default window (current month) and invalid date fallback."""
    # Seed one conversa created "now"
    agora = datetime.now(timezone.utc)
    db.add(_conversa(loja_a["loja_id"], "aberta", agora))
    db.commit()

    # (a) No params: defaults to current calendar month
    r_default = client.get(
        "/v1/atendimento/resumo",
        headers=loja_a["headers"],
    )
    assert r_default.status_code == 200
    assert r_default.json()["atendimentos"] >= 1  # current month includes it

    # (b) Invalid dates: fallback to default window (should NOT error 500)
    r_invalid = client.get(
        "/v1/atendimento/resumo?desde=garbage&ate=also-garbage",
        headers=loja_a["headers"],
    )
    assert r_invalid.status_code == 200  # NOT 500; fallback to defaults
    assert r_invalid.json()["atendimentos"] >= 1  # same result as default
