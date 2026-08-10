"""POST /v1/operacao/solicitacoes-simulacao-humana — alerta no grupo de estoque."""

from datetime import date

from app import models_db
from app.models_db import NotificacaoOperacional
from app.solicitacoes_simulacao import (
    _MENSAGEM_MENOR_IDADE,
    _calcular_idade,
    _cnh_confirmada,
    _parse_nascimento,
)


GRUPO = "120363001@g.us"


def _selecionar_grupo(client, loja):
    r = client.put(
        "/v1/operacao/grupo-estoque",
        json={"grupo_jid": GRUPO, "grupo_nome": "Equipe Estoque"},
        headers=loja["headers"],
    )
    assert r.status_code == 200, r.text


def _payload_base(loja, **overrides):
    body = {
        "telefone": "5511999001122",
        "interesse": "Honda CG 160 2024 preta",
        "tem_cnh": "sim",
        "instance": loja["instance"],
        "cpf": "52998224725",
        "nascimento": "1990-05-15",
        "entrada": 3500,
        "cpf_recebido": True,
        "nascimento_recebido": True,
    }
    body.update(overrides)
    return body


def test_helpers_idade_e_cnh():
    assert _parse_nascimento("15/05/1990") == date(1990, 5, 15)
    assert _parse_nascimento("1990-05-15") == date(1990, 5, 15)
    assert _parse_nascimento("32/13/1990") is None
    assert _calcular_idade(date(2010, 1, 1), ref=date(2026, 8, 10)) == 16
    assert _calcular_idade(date(2008, 8, 10), ref=date(2026, 8, 10)) == 18
    assert _calcular_idade(date(2008, 8, 11), ref=date(2026, 8, 10)) == 17
    assert _cnh_confirmada("sim") == "SIM"
    assert _cnh_confirmada("não") == "NÃO"
    assert _cnh_confirmada("nao tenho") == "NÃO"
    assert _cnh_confirmada("talvez") is None
    assert _cnh_confirmada(None) is None
    assert _cnh_confirmada("") is None


def test_solicita_simula_alerta_grupo_e_pausa_bot(
    client, loja_a, db, _fake_whatsapp_outbound
):
    _selecionar_grupo(client, loja_a)
    tel = "5511999001122"
    cpf = "52998224725"
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={
            **loja_a["headers"],
            "Idempotency-Key": "WA-MSG-SIM-1",
        },
        json=_payload_base(loja_a, telefone=tel, cpf=cpf),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["simulacao_humana_solicitada"] is True
    assert body["duplicada"] is False
    assert body["alerta_enviado"] is True
    assert body["status_alerta"] == "sent"
    assert "encaminhar pro setor de simulação" in body["mensagem"]

    assert len(_fake_whatsapp_outbound.calls) == 1
    call = _fake_whatsapp_outbound.calls[0]
    assert call["instance"] == loja_a["instance"]
    assert call["number"] == GRUPO
    assert call["number"].endswith("@g.us")
    texto = call["text"]
    assert "PRECISA DE SIMULAÇÃO HUMANA" in texto
    assert f"Cliente final: {tel}" in texto
    assert "CPF: 529.982.247-25" in texto
    assert "Data de nascimento: 15/05/1990" in texto
    assert "CNH: SIM" in texto
    assert "Vendedor de origem:" in texto
    assert "Honda CG 160 2024 preta" in texto
    assert "Faça a simulação no portal e responda ao cliente:" in texto
    assert "atendimento" in texto
    assert tel in texto
    assert "****" not in texto
    assert "***" not in texto

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
    payload = _payload_base(
        loja_a,
        telefone="5511999003344",
        interesse="Yamaha Factor",
    )
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


def test_dedupe_mesmo_cliente_outra_mensagem_nao_reenvia(
    client, loja_a, _fake_whatsapp_outbound
):
    """Mesmo telefone com Idempotency-Key diferente reutiliza o atendimento."""
    _selecionar_grupo(client, loja_a)
    payload = _payload_base(loja_a, telefone="5511999011223")
    r1 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-CLIENTE-A"},
        json=payload,
    )
    r2 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-CLIENTE-B"},
        json=payload,
    )
    assert r1.status_code == 202, r1.text
    assert r2.status_code == 202, r2.text
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    assert r1.json()["notificacao_id"] == r2.json()["notificacao_id"]
    assert len(_fake_whatsapp_outbound.calls) == 1


def test_dedupe_mesmo_cpf_telefone_diferente_nao_reenvia(
    client, loja_a, _fake_whatsapp_outbound
):
    _selecionar_grupo(client, loja_a)
    cpf = "52998224725"
    r1 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-CPF-1"},
        json=_payload_base(loja_a, telefone="5511999010001", cpf=cpf),
    )
    r2 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-CPF-2"},
        json=_payload_base(loja_a, telefone="5511999010002", cpf=cpf),
    )
    assert r1.status_code == 202, r1.text
    assert r2.status_code == 202, r2.text
    assert r2.json()["duplicada"] is True
    assert r1.json()["notificacao_id"] == r2.json()["notificacao_id"]
    assert len(_fake_whatsapp_outbound.calls) == 1


def test_bloqueia_menor_de_idade(client, loja_a, _fake_whatsapp_outbound, db):
    _selecionar_grupo(client, loja_a)
    tel = "5511999006677"
    # 16 anos em 2026-08-10
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-MENOR-1"},
        json=_payload_base(
            loja_a,
            telefone=tel,
            nascimento="10/08/2010",
        ),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["bloqueado"] is True
    assert body["motivo_bloqueio"] == "menor_de_idade"
    assert body["simulacao_humana_solicitada"] is False
    assert body["mensagem"] == _MENSAGEM_MENOR_IDADE
    assert _fake_whatsapp_outbound.calls == []
    assert (
        db.query(NotificacaoOperacional)
        .filter(NotificacaoOperacional.idempotency_key == "WA-MENOR-1")
        .count()
        == 0
    )
    estado = client.get(
        f"/v1/conversas/{tel}/estado", headers=loja_a["headers"]
    ).json()
    # Menor: não pausa o bot (não há atendimento de simulação).
    assert estado["bot_ativo"] is True


def test_bloqueia_sem_cnh_confirmada(client, loja_a, _fake_whatsapp_outbound, db):
    _selecionar_grupo(client, loja_a)
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-SEM-CNH"},
        json=_payload_base(loja_a, tem_cnh=None),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["bloqueado"] is True
    assert body["motivo_bloqueio"] == "cnh_nao_confirmada"
    assert "cnh" in body["faltando"]
    assert "sim ou não" in body["mensagem"].lower() or "sim ou nao" in body["mensagem"].lower()
    assert _fake_whatsapp_outbound.calls == []
    assert (
        db.query(NotificacaoOperacional)
        .filter(NotificacaoOperacional.idempotency_key == "WA-SEM-CNH")
        .count()
        == 0
    )


def test_bloqueia_cnh_ambigua(client, loja_a, _fake_whatsapp_outbound):
    _selecionar_grupo(client, loja_a)
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-CNH-TALVEZ"},
        json=_payload_base(loja_a, tem_cnh="talvez depois"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["motivo_bloqueio"] == "cnh_nao_confirmada"
    assert _fake_whatsapp_outbound.calls == []


def test_bloqueia_nascimento_invalido(client, loja_a, _fake_whatsapp_outbound):
    _selecionar_grupo(client, loja_a)
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-NASC-BAD"},
        json=_payload_base(loja_a, nascimento="ontem"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["motivo_bloqueio"] == "nascimento_invalido"
    assert "data de nascimento" in body["faltando"]
    assert _fake_whatsapp_outbound.calls == []


def test_aceita_cnh_nao(client, loja_a, _fake_whatsapp_outbound):
    """CNH=não é confirmação válida e deve seguir para o grupo."""
    _selecionar_grupo(client, loja_a)
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-CNH-NAO"},
        json=_payload_base(loja_a, telefone="5511999022334", tem_cnh="não"),
    )
    assert r.status_code == 202, r.text
    assert r.json()["ok"] is True
    assert "CNH: NÃO" in _fake_whatsapp_outbound.calls[0]["text"]


def test_sem_grupo_aceita_mas_marca_failed(client, loja_a, _fake_whatsapp_outbound, db):
    tel = "5511999005566"
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers={**loja_a["headers"], "Idempotency-Key": "WA-SEM-GRUPO"},
        json=_payload_base(loja_a, telefone=tel, interesse="Moto X"),
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


def test_reenvia_quando_tentativa_anterior_falhou(
    client, loja_a, _fake_whatsapp_outbound
):
    """Rechamada com a mesma Idempotency-Key reenvia se o 1º envio falhou."""
    _selecionar_grupo(client, loja_a)
    _fake_whatsapp_outbound.fail = True
    headers = {**loja_a["headers"], "Idempotency-Key": "WA-RETRY-1"}
    payload = _payload_base(
        loja_a,
        telefone="5511988887777",
        interesse="Honda Biz 2023",
    )
    r1 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana", headers=headers, json=payload
    )
    assert r1.status_code == 202, r1.text
    assert r1.json()["alerta_enviado"] is False
    assert r1.json()["status_alerta"] == "failed"
    assert len(_fake_whatsapp_outbound.calls) == 1

    _fake_whatsapp_outbound.fail = False
    r2 = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana", headers=headers, json=payload
    )
    assert r2.status_code == 202, r2.text
    body = r2.json()
    assert body["duplicada"] is True
    assert body["alerta_enviado"] is True
    assert body["status_alerta"] == "sent"
    assert len(_fake_whatsapp_outbound.calls) == 2
    # Reenvio por rechamada mantém o CPF completo (dados frescos da requisição).
    assert "CPF: 529.982.247-25" in _fake_whatsapp_outbound.calls[1]["text"]


def test_drenador_reenvia_alerta_pendente(
    client, loja_a, _fake_whatsapp_outbound, db
):
    """O worker reprocessa alertas failed cujo next_attempt_at venceu."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.orm import sessionmaker

    from app.solicitacoes_simulacao import processar_pendentes

    _selecionar_grupo(client, loja_a)
    _fake_whatsapp_outbound.fail = True
    headers = {**loja_a["headers"], "Idempotency-Key": "WA-DRAIN-1"}
    tel = "5511977776666"
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers=headers,
        json=_payload_base(
            loja_a,
            telefone=tel,
            interesse="Yamaha Fazer 250",
            nascimento="1988-03-10",
            tem_cnh="nao",
        ),
    )
    assert r.status_code == 202, r.text
    assert r.json()["status_alerta"] == "failed"
    assert len(_fake_whatsapp_outbound.calls) == 1

    notif = (
        db.query(NotificacaoOperacional)
        .filter(NotificacaoOperacional.idempotency_key == "WA-DRAIN-1")
        .one()
    )
    notif.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    _fake_whatsapp_outbound.fail = False
    resultado = processar_pendentes(sessionmaker(bind=db.get_bind()))
    assert resultado["encontrados"] == 1
    assert resultado["enviados"] == 1
    assert len(_fake_whatsapp_outbound.calls) == 2

    db.refresh(notif)
    assert notif.status == "sent"
    texto = _fake_whatsapp_outbound.calls[1]["text"]
    assert f"Cliente final: {tel}" in texto
    assert "Faça a simulação no portal" in texto
    # CPF completo não é persistido; o reenvio pelo drenador o omite.
    assert "CPF: não informado" in texto


def test_exige_idempotency_key(client, loja_a):
    r = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        headers=loja_a["headers"],
        json=_payload_base(loja_a, telefone="5511999007788", interesse="CG"),
    )
    assert r.status_code == 422
