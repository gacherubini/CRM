"""POST /v1/operacao/solicitacoes-simulacao-humana — alerta no grupo de estoque."""

from app import models_db
from app.models_db import NotificacaoOperacional


GRUPO = "120363001@g.us"


def _selecionar_grupo(client, loja):
    r = client.put(
        "/v1/operacao/grupo-estoque",
        json={"grupo_jid": GRUPO, "grupo_nome": "Equipe Estoque"},
        headers=loja["headers"],
    )
    assert r.status_code == 200, r.text


def test_solicita_simula_alerta_grupo_e_pausa_bot(
    client, loja_a, db, _fake_whatsapp_outbound
):
    _selecionar_grupo(client, loja_a)
    tel = "5511999001122"
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={
            **loja_a["headers"],
            "Idempotency-Key": "WA-MSG-SIM-1",
        },
        json={
            "telefone": tel,
            "interesse": "Honda CG 160 2024",
            "tem_cnh": "sim",
            "instance": loja_a["instance"],
            "cpf_recebido": True,
            "nascimento_recebido": True,
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["simulacao_humana_solicitada"] is True
    assert body["duplicada"] is False
    assert body["alerta_enviado"] is True
    assert body["status_alerta"] == "sent"
    assert "certinho" in body["mensagem"]

    assert len(_fake_whatsapp_outbound.calls) == 1
    call = _fake_whatsapp_outbound.calls[0]
    assert call["instance"] == loja_a["instance"]
    assert call["number"] == GRUPO
    assert call["number"].endswith("@g.us")
    assert "cpf" not in call["text"].lower() or "recebidos" in call["text"].lower()
    assert "111" not in call["text"]  # não vaza dígitos de CPF
    assert "Honda CG 160" in call["text"]
    assert "atendimento" in call["text"]

    estado = client.get(
        f"/v1/conversas/{tel}/estado", headers=loja_a["headers"]
    ).json()
    assert estado["bot_ativo"] is False

    leads = (
        db.query(models_db.Lead)
        .filter(models_db.Lead.loja_id == loja_a["loja_id"], models_db.Lead.telefone == tel)
        .all()
    )
    assert len(leads) == 1
    assert leads[0].etapa == "qualificado"


def test_idempotencia_nao_reenvia(client, loja_a, _fake_whatsapp_outbound):
    _selecionar_grupo(client, loja_a)
    payload = {
        "telefone": "5511999003344",
        "interesse": "Yamaha Factor",
        "instance": loja_a["instance"],
        "cpf_recebido": True,
        "nascimento_recebido": True,
    }
    headers = {**loja_a["headers"], "Idempotency-Key": "WA-MSG-DUP"}
    r1 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana", headers=headers, json=payload
    )
    r2 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana", headers=headers, json=payload
    )
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    assert r1.json()["notificacao_id"] == r2.json()["notificacao_id"]
    assert len(_fake_whatsapp_outbound.calls) == 1


def test_sem_grupo_aceita_mas_marca_failed(client, loja_a, _fake_whatsapp_outbound, db):
    tel = "5511999005566"
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-SEM-GRUPO"},
        json={
            "telefone": tel,
            "interesse": "Moto X",
            "instance": loja_a["instance"],
            "cpf_recebido": True,
            "nascimento_recebido": True,
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["alerta_enviado"] is False
    assert body["status_alerta"] == "failed"
    assert body["last_error_code"] == "grupo_estoque_nao_configurado"
    assert _fake_whatsapp_outbound.calls == []

    notif = (
        db.query(NotificacaoOperacional)
        .filter(NotificacaoOperacional.idempotency_key == "WA-SEM-GRUPO")
        .one()
    )
    assert notif.status == "failed"

    estado = client.get(
        f"/v1/conversas/{tel}/estado", headers=loja_a["headers"]
    ).json()
    assert estado["bot_ativo"] is False


def test_exige_idempotency_key(client, loja_a):
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers=loja_a["headers"],
        json={"telefone": "5511999007788", "interesse": "CG"},
    )
    assert r.status_code == 422
