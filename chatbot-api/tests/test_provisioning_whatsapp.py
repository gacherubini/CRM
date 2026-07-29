"""Gates WhatsApp de captura passiva e bloqueio (ADR 0001)."""
from app import models_db, operacao, provisioning, servico


def _suspender_loja(db, loja_id: str, version: int = 99) -> None:
    proj = db.get(models_db.LojaOperacionalProjecao, (loja_id, "loja"))
    assert proj is not None, "fixture deve seedar projeção loja ativa"
    proj.state = "suspensa"
    proj.version = version
    db.commit()


def _suspender_estoque(db, loja_id: str, version: int = 50) -> None:
    proj = db.get(models_db.LojaOperacionalProjecao, (loja_id, "estoque"))
    assert proj is not None, "fixture deve seedar projeção estoque ativo"
    proj.state = "suspenso"
    proj.version = version
    db.commit()


def test_helpers_capture_only_e_outbound(db, loja_a):
    loja_id = loja_a["loja_id"]
    assert provisioning.is_store_operational(db, loja_id) is True
    assert provisioning.allows_outbound_whatsapp(db, loja_id) is True
    assert provisioning.capture_only(db, loja_id) is False
    assert provisioning.is_module_operational(db, loja_id, "estoque") is True
    assert provisioning.capture_only(db, loja_id, module="estoque") is False

    _suspender_loja(db, loja_id)
    assert provisioning.is_store_operational(db, loja_id) is False
    assert provisioning.allows_outbound_whatsapp(db, loja_id) is False
    assert provisioning.capture_only(db, loja_id) is True
    assert provisioning.is_module_operational(db, loja_id, "estoque") is False
    assert provisioning.capture_only(db, loja_id, module="estoque") is True


def test_registrar_mensagem_suspensa_captura_passiva_e_persiste(client, loja_a, db):
    loja_id = loja_a["loja_id"]
    _suspender_loja(db, loja_id)

    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": "5511981112222",
            "texto": "quero financiar",
            "provider_message_id": "CAP-SUSP-1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["duplicada"] is False
    assert body["bot_ativo"] is False
    assert body["captura_passiva"] is True
    assert body["loja_operacional"] is False
    assert body["conversa_id"]

    msg = (
        db.query(models_db.Mensagem)
        .filter(
            models_db.Mensagem.loja_id == loja_id,
            models_db.Mensagem.provider_message_id == "CAP-SUSP-1",
        )
        .first()
    )
    assert msg is not None
    assert msg.direcao == "entrada"
    assert "financiar" in (msg.texto or "")


def test_registrar_mensagem_suspensa_nao_reativa_autorizado(client, loja_a, db):
    loja_id = loja_a["loja_id"]
    tel = "5511983334444"
    client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": tel, "papel": "dono"},
        headers=loja_a["headers"],
    )
    # Pausa o bot na conversa antes da suspensão.
    client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": False},
        headers=loja_a["headers"],
    )
    _suspender_loja(db, loja_id)

    body = servico.registrar_mensagem(
        db,
        loja_a["instance"],
        tel,
        "menu",
        provider_message_id="CAP-AUTH-1",
        from_me=False,
    )
    assert body["bot_ativo"] is False
    assert body["captura_passiva"] is True

    estado = servico.obter_estado(db, loja_id, tel)
    # Não reativa bot para número autorizado durante captura passiva.
    assert estado["bot_ativo"] is False


def test_registrar_mensagem_duplicada_suspensa_forca_bot_false(client, loja_a, db):
    _suspender_loja(db, loja_a["loja_id"])
    payload = {
        "instance": loja_a["instance"],
        "telefone": "5511985556666",
        "texto": "oi",
        "provider_message_id": "CAP-DUP-1",
    }
    r1 = client.post("/webhook/mensagem", json=payload)
    r2 = client.post("/webhook/mensagem", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["duplicada"] is True
    assert r2.json()["bot_ativo"] is False
    assert r2.json()["captura_passiva"] is True


def test_decidir_roteamento_suspensa_ignorar(db, loja_a):
    _suspender_loja(db, loja_a["loja_id"])
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000099", "oi", False
    )
    assert d["acao"] == "ignorar"
    assert d["resposta"] is None
    assert d["captura_passiva"] is True
    assert d["loja_operacional"] is False


def test_decidir_roteamento_estoque_suspenso_bloqueia_operacao(client, loja_a, db):
    loja_id = loja_a["loja_id"]
    tel = "5511970000088"
    client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": tel, "papel": "dono"},
        headers=loja_a["headers"],
    )
    _suspender_estoque(db, loja_id)

    d = operacao.decidir_roteamento(db, loja_id, tel, "menu", True)
    assert d["acao"] == "ignorar"
    assert d["captura_passiva"] is True
    assert d["loja_operacional"] is True


def test_decidir_roteamento_estoque_suspenso_cliente_ainda_funciona(db, loja_a):
    loja_id = loja_a["loja_id"]
    _suspender_estoque(db, loja_id)
    d = operacao.decidir_roteamento(db, loja_id, "5511970000077", "quero moto", False)
    assert d["acao"] == "cliente"
    assert d.get("captura_passiva") is None or d.get("captura_passiva") is False


def test_ativar_bot_ativo_quando_suspensa_retorna_423(client, loja_a, db):
    tel = "5511987778888"
    # Cria conversa pausada enquanto ainda operacional.
    client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": False},
        headers=loja_a["headers"],
    )
    _suspender_loja(db, loja_a["loja_id"])

    r = client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": True},
        headers=loja_a["headers"],
    )
    assert r.status_code == 423
    assert r.json()["detail"]["code"] == "store_not_operational"


def test_pausar_bot_ativo_quando_suspensa_ainda_permitido(client, loja_a, db):
    tel = "5511987779999"
    client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": True},
        headers=loja_a["headers"],
    )
    _suspender_loja(db, loja_a["loja_id"])

    r = client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": False},
        headers=loja_a["headers"],
    )
    assert r.status_code == 200
    assert r.json()["bot_ativo"] is False


def test_loja_ativa_projection_seeded_cliente_routing_works(db, loja_a):
    assert provisioning.is_store_operational(db, loja_a["loja_id"]) is True
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511971110000", "oi", False
    )
    assert d["acao"] == "cliente"
    assert d["resposta"] is None


def test_loja_ativa_registrar_mensagem_bot_ativo_normal(client, loja_a):
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": "5511980001111",
            "texto": "olá",
            "provider_message_id": "CAP-OK-1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bot_ativo"] is True
    assert body.get("captura_passiva") is not True
    assert body["duplicada"] is False


def test_webhook_audio_suspensa_sem_processar(client, loja_a, db):
    _suspender_loja(db, loja_a["loja_id"])
    r = client.post(
        "/webhook/audio/transcrever",
        json={
            "instance": loja_a["instance"],
            "provider_message_id": "AUD-SUSP-1",
            "mime_type": "audio/ogg",
            "duration_seconds": 5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["transcrito"] is False
    assert body["captura_passiva"] is True
    assert body["loja_operacional"] is False


def test_webhook_foto_suspensa_sem_processar(client, loja_a, db):
    _suspender_loja(db, loja_a["loja_id"])
    r = client.post(
        "/webhook/operacao/veiculos/foto",
        json={
            "instance": loja_a["instance"],
            "telefone_solicitante": "5511999990001",
            "provider_message_id": "FOTO-SUSP-1",
            "legenda": "ABC1D23",
            "mime_type": "image/jpeg",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["ignorar"] is True
    assert body["captura_passiva"] is True
    assert body["loja_operacional"] is False
