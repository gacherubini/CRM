"""Multi-WA: dois canais, conversas por canal, dedupe, instância desconhecida, QR."""
import uuid

import pytest

from app import channels, config, models_db, servico


def _register_two_channels(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    legado = channels.backfill_legacy_from_loja(db, loja_a["loja_id"])
    inst2 = f"inst-linha2-{uuid.uuid4().hex[:6]}"
    extra = channels.register_channel(
        db, loja_a["loja_id"], inst2, "linha-2"
    )
    return legado, extra


def test_dois_canais_mesmo_telefone_duas_conversas(db, loja_a, monkeypatch):
    legado, extra = _register_two_channels(db, loja_a, monkeypatch)
    tel = "5511988000001"

    r1 = servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "oi no 1", "MID-C1-1"
    )
    r2 = servico.registrar_mensagem(
        db, extra["evolution_instance"], tel, "oi no 2", "MID-C2-1"
    )

    assert r1["conversa_id"] != r2["conversa_id"]
    assert r1["canal_id"] == legado["id"]
    assert r2["canal_id"] == extra["id"]
    assert r1["evolution_instance"] == legado["evolution_instance"]
    assert r2["evolution_instance"] == extra["evolution_instance"]

    convs = (
        db.query(models_db.Conversa)
        .filter(
            models_db.Conversa.loja_id == loja_a["loja_id"],
            models_db.Conversa.telefone == tel,
        )
        .all()
    )
    assert len(convs) == 2
    canal_ids = {c.canal_id for c in convs}
    assert canal_ids == {legado["id"], extra["id"]}


def test_dedupe_provider_message_id_por_canal(db, loja_a, monkeypatch):
    legado, extra = _register_two_channels(db, loja_a, monkeypatch)
    tel = "5511988000002"
    same_mid = "SAME-PROVIDER-ID"

    a1 = servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "a", same_mid
    )
    a2 = servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "a-dup", same_mid
    )
    b1 = servico.registrar_mensagem(
        db, extra["evolution_instance"], tel, "b", same_mid
    )

    assert a1["duplicada"] is False
    assert a2["duplicada"] is True
    assert b1["duplicada"] is False
    assert a1["conversa_id"] != b1["conversa_id"]

    msgs = (
        db.query(models_db.Mensagem)
        .filter(models_db.Mensagem.provider_message_id == same_mid)
        .all()
    )
    assert len(msgs) == 2
    assert {m.canal_id for m in msgs} == {legado["id"], extra["id"]}


def test_instancia_desconhecida_rejeitada(db):
    with pytest.raises(Exception) as exc:
        servico.registrar_mensagem(
            db, "instancia-fantasma-xyz", "5511999", "oi", "M1"
        )
    # HTTPException 404
    assert getattr(exc.value, "status_code", None) == 404
    assert "não reconhecida" in str(exc.value.detail).lower()


def test_from_me_pausa_apenas_conversa_do_canal(db, loja_a, monkeypatch):
    legado, extra = _register_two_channels(db, loja_a, monkeypatch)
    tel = "5511988000003"

    servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "oi", "IN-1"
    )
    servico.registrar_mensagem(
        db, extra["evolution_instance"], tel, "oi", "IN-2"
    )

    # Atendente responde só no canal legado
    r = servico.registrar_mensagem(
        db,
        legado["evolution_instance"],
        tel,
        "humano no canal 1",
        "OUT-MANUAL-1",
        from_me=True,
    )
    assert r["bot_ativo"] is False

    conv_legado = (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.canal_id == legado["id"])
        .one()
    )
    conv_extra = (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.canal_id == extra["id"])
        .one()
    )
    assert conv_legado.bot_ativo is False
    assert conv_legado.status == "handoff"
    assert conv_extra.bot_ativo is True
    assert conv_extra.status == "aberta"


def test_patch_estado_com_instance_pausa_so_canal(db, loja_a, monkeypatch):
    """Handoff via PATCH /estado com instance escopa ao canal (tool n8n)."""
    legado, extra = _register_two_channels(db, loja_a, monkeypatch)
    tel = "5511988000004"
    servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "oi", "IN-H1"
    )
    servico.registrar_mensagem(
        db, extra["evolution_instance"], tel, "oi", "IN-H2"
    )

    r = servico.definir_bot_ativo(
        db,
        loja_a["loja_id"],
        tel,
        False,
        instance=legado["evolution_instance"],
    )
    assert r["bot_ativo"] is False
    assert r["status"] == "handoff"

    est_legado = servico.obter_estado(
        db, loja_a["loja_id"], tel, instance=legado["evolution_instance"]
    )
    est_extra = servico.obter_estado(
        db, loja_a["loja_id"], tel, instance=extra["evolution_instance"]
    )
    assert est_legado["bot_ativo"] is False
    assert est_extra["bot_ativo"] is True

    conv_legado = (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.canal_id == legado["id"])
        .one()
    )
    conv_extra = (
        db.query(models_db.Conversa)
        .filter(models_db.Conversa.canal_id == extra["id"])
        .one()
    )
    assert conv_legado.bot_ativo is False
    assert conv_extra.bot_ativo is True


def test_connect_qr_no_store(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    r = client.get("/v1/whatsapp/canais", headers=loja_a["headers"])
    assert r.status_code == 200
    canal_id = r.json()["canais"][0]["id"]

    # Desconecta para forçar novo QR no connect
    client.post(
        f"/v1/whatsapp/canais/{canal_id}/disconnect",
        headers=loja_a["headers"],
    )
    # Memory/stub: connect a partir de desconectado gera QR
    # (legado nasce conectado; disconnect → desconectado)
    r2 = client.post(
        f"/v1/whatsapp/canais/{canal_id}/connect",
        headers=loja_a["headers"],
    )
    assert r2.status_code == 200
    assert "no-store" in r2.headers.get("cache-control", "").lower()
    body = r2.json()
    assert body.get("qr_payload")
    assert "estado" in body


def test_listar_conversas_expoe_canal_e_filtra(client, db, loja_a, monkeypatch):
    """Saída de conversas inclui canal_id/label; filtro ?canal_id= isola o canal."""
    legado, extra = _register_two_channels(db, loja_a, monkeypatch)
    tel = "5511988000010"
    servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "no legado", "LIST-C1"
    )
    servico.registrar_mensagem(
        db, extra["evolution_instance"], tel, "no extra", "LIST-C2"
    )

    h = loja_a["headers"]
    todas = client.get("/v1/conversas", headers=h).json()["conversas"]
    do_tel = [c for c in todas if c["telefone"] == tel]
    assert len(do_tel) == 2
    for c in do_tel:
        assert c["canal_id"] in {legado["id"], extra["id"]}
        assert c["evolution_instance"]
        assert c["canal_label"]
        assert c["canal_ativo"] is True
        assert c["canal_estado"]

    filtradas = client.get(
        f"/v1/conversas?canal_id={extra['id']}", headers=h
    ).json()["conversas"]
    assert all(c["canal_id"] == extra["id"] for c in filtradas)
    assert any(c["telefone"] == tel for c in filtradas)
    assert not any(
        c["telefone"] == tel and c["canal_id"] == legado["id"] for c in filtradas
    )


def test_http_unknown_instance_webhook(client):
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": "desconhecida-999",
            "telefone": "5511988000099",
            "texto": "oi",
            "provider_message_id": "U1",
        },
    )
    assert r.status_code == 404


def test_listar_mensagens_isolado_por_canal(client, db, loja_a, monkeypatch):
    """Dois canais, mesmo telefone: histórico isolado por canal_id/instance."""
    legado, extra = _register_two_channels(db, loja_a, monkeypatch)
    tel = "5511988000020"
    servico.registrar_mensagem(
        db, legado["evolution_instance"], tel, "msg legado", "HIST-L1"
    )
    servico.registrar_mensagem(
        db, extra["evolution_instance"], tel, "msg extra", "HIST-E1"
    )

    h = loja_a["headers"]

    # Sem canal: ambíguo → 409
    r_amb = client.get(f"/v1/conversas/{tel}/mensagens", headers=h)
    assert r_amb.status_code == 409
    assert r_amb.json()["detail"]["code"] == "conversa_ambigua"

    # Por canal_id
    r_legado = client.get(
        f"/v1/conversas/{tel}/mensagens?canal_id={legado['id']}", headers=h
    )
    assert r_legado.status_code == 200
    textos_l = [m["texto"] for m in r_legado.json()["mensagens"]]
    assert textos_l == ["msg legado"]
    assert r_legado.json().get("canal_id") == legado["id"]

    r_extra = client.get(
        f"/v1/conversas/{tel}/mensagens?canal_id={extra['id']}", headers=h
    )
    assert r_extra.status_code == 200
    textos_e = [m["texto"] for m in r_extra.json()["mensagens"]]
    assert textos_e == ["msg extra"]

    # Por instance (mesmo isolamento)
    r_inst = client.get(
        f"/v1/conversas/{tel}/mensagens?instance={extra['evolution_instance']}",
        headers=h,
    )
    assert r_inst.status_code == 200
    assert [m["texto"] for m in r_inst.json()["mensagens"]] == ["msg extra"]

    # obter_estado também exige desambiguação
    assert client.get(f"/v1/conversas/{tel}/estado", headers=h).status_code == 409
    est = client.get(
        f"/v1/conversas/{tel}/estado?canal_id={legado['id']}", headers=h
    )
    assert est.status_code == 200
    assert "bot_ativo" in est.json()


def test_listar_mensagens_single_channel_sem_canal_ok(client, loja_a):
    """Single-channel: histórico por telefone continua sem canal_id/instance."""
    tel = "5511988000021"
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": tel,
            "texto": "unica",
            "provider_message_id": "HIST-S1",
        },
    )
    assert r.status_code == 200
    h = loja_a["headers"]
    body = client.get(f"/v1/conversas/{tel}/mensagens", headers=h).json()
    assert [m["texto"] for m in body["mensagens"]] == ["unica"]
    estado = client.get(f"/v1/conversas/{tel}/estado", headers=h)
    assert estado.status_code == 200
