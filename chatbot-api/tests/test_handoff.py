def test_estado_default_ativo(client, loja_a):
    r = client.get("/v1/conversas/5511000000000/estado", headers=loja_a["headers"])
    assert r.status_code == 200
    assert r.json() == {"bot_ativo": True, "status": "aberta"}


def test_pausar_e_devolver(client, loja_a):
    tel, h = "5511988887777", loja_a["headers"]
    pausar = client.patch(
        f"/v1/conversas/{tel}/estado", json={"bot_ativo": False}, headers=h
    )
    assert pausar.json() == {"bot_ativo": False, "status": "handoff"}
    assert client.get(f"/v1/conversas/{tel}/estado", headers=h).json()["bot_ativo"] is False

    devolver = client.patch(
        f"/v1/conversas/{tel}/estado", json={"bot_ativo": True}, headers=h
    )
    assert devolver.json() == {"bot_ativo": True, "status": "aberta"}


def test_webhook_respeita_handoff(client, loja_a):
    inst, tel, h = loja_a["instance"], "5511988887777", loja_a["headers"]
    client.patch(f"/v1/conversas/{tel}/estado", json={"bot_ativo": False}, headers=h)
    r = client.post(
        "/webhook/mensagem",
        json={"instance": inst, "telefone": tel, "texto": "oi", "provider_message_id": "X1"},
    )
    # a mensagem é registrada, mas o estado informa que o bot está pausado
    assert r.json()["bot_ativo"] is False


def test_estado_isolado_por_loja(client, loja_a, loja_b):
    tel = "5511988887777"
    client.patch(f"/v1/conversas/{tel}/estado", json={"bot_ativo": False}, headers=loja_a["headers"])
    # loja B não enxerga a pausa da loja A: seu próprio estado é o default
    r = client.get(f"/v1/conversas/{tel}/estado", headers=loja_b["headers"])
    assert r.json()["bot_ativo"] is True


def test_estado_exige_credencial(client):
    assert client.get("/v1/conversas/5511/estado").status_code == 401


def test_pode_responder_somente_a_ultima_entrada(client, loja_a):
    inst, tel, h = loja_a["instance"], "5511977700001", loja_a["headers"]
    client.post(
        "/webhook/mensagem",
        json={
            "instance": inst,
            "telefone": tel,
            "texto": "primeira parte",
            "provider_message_id": "DEBOUNCE-1",
        },
    )
    client.post(
        "/webhook/mensagem",
        json={
            "instance": inst,
            "telefone": tel,
            "texto": "segunda parte",
            "provider_message_id": "DEBOUNCE-2",
        },
    )

    antiga = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": inst, "provider_message_id": "DEBOUNCE-1"},
        headers=h,
    )
    atual = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": inst, "provider_message_id": "DEBOUNCE-2"},
        headers=h,
    )

    assert antiga.status_code == 200
    assert antiga.json() == {
        "pode_responder": False,
        "motivo": "mensagem_superada",
    }
    assert atual.json() == {"pode_responder": True, "motivo": "ultima_entrada"}


def test_pode_responder_bloqueia_saida_consecutiva_e_handoff(client, loja_a):
    inst, tel, h = loja_a["instance"], "5511977700002", loja_a["headers"]
    client.post(
        "/webhook/mensagem",
        json={
            "instance": inst,
            "telefone": tel,
            "texto": "quero saber da moto",
            "provider_message_id": "CLIENTE-1",
        },
    )
    client.post(
        "/webhook/mensagem",
        json={
            "instance": inst,
            "telefone": tel,
            "texto": "resposta já enviada",
            "provider_message_id": "BOT-RESPOSTA-1",
            "from_me": True,
            "origem_bot": True,
        },
    )

    ja_respondida = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": inst, "provider_message_id": "CLIENTE-1"},
        headers=h,
    )
    assert ja_respondida.json() == {
        "pode_responder": False,
        "motivo": "ultima_mensagem_saida",
    }

    client.post(
        "/webhook/mensagem",
        json={
            "instance": inst,
            "telefone": tel,
            "texto": "nova pergunta",
            "provider_message_id": "CLIENTE-2",
        },
    )
    client.patch(
        f"/v1/conversas/{tel}/estado",
        json={"bot_ativo": False, "instance": inst},
        headers=h,
    )
    handoff = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": inst, "provider_message_id": "CLIENTE-2"},
        headers=h,
    )
    assert handoff.json() == {"pode_responder": False, "motivo": "bot_inativo"}


def test_resposta_manual_pausa_o_bot(client, loja_a):
    tel = "5511977700011"
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": tel,
            "texto": "Eu continuo daqui",
            "provider_message_id": "MANUAL-1",
            "from_me": True,
        },
    )
    assert r.json()["bot_ativo"] is False
    estado = client.get(f"/v1/conversas/{tel}/estado", headers=loja_a["headers"])
    assert estado.json() == {"bot_ativo": False, "status": "handoff"}


def test_saida_do_bot_e_evento_duplicado_nao_acionam_handoff(client, loja_a):
    tel = "5511977700022"
    payload = {
        "instance": loja_a["instance"],
        "telefone": tel,
        "texto": "Mensagem automática",
        "provider_message_id": "BOT-1",
        "from_me": True,
    }
    registrada = client.post(
        "/webhook/mensagem", json={**payload, "origem_bot": True}
    )
    assert registrada.json()["bot_ativo"] is True

    # A Evolution reentrega a mesma saída como fromMe; a idempotência a reconhece.
    repetida = client.post("/webhook/mensagem", json=payload)
    assert repetida.json()["duplicada"] is True
    assert repetida.json()["bot_ativo"] is True


def test_from_me_vazio_ou_whitespace_nao_pausa(client, loja_a):
    """Ack/status sem corpo e from_me vazio não devem virar handoff (E3)."""
    inst, h = loja_a["instance"], loja_a["headers"]
    for i, texto in enumerate((None, "", "   ", "\n\t")):
        tel = f"55119777001{i:02d}"
        r = client.post(
            "/webhook/mensagem",
            json={
                "instance": inst,
                "telefone": tel,
                "texto": texto,
                "provider_message_id": f"EMPTY-{i}",
                "from_me": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["bot_ativo"] is True
        assert body.get("ignorada") is True
        estado = client.get(f"/v1/conversas/{tel}/estado", headers=h)
        assert estado.json() == {"bot_ativo": True, "status": "aberta"}


def test_ack_status_reaction_nao_pausam_o_bot(client, loja_a):
    """tipo=status|ack|reaction não altera bot_ativo mesmo com from_me."""
    inst, h = loja_a["instance"], loja_a["headers"]
    for i, tipo in enumerate(("status", "ack", "reaction", "messages.update", "receipt")):
        tel = f"55119777002{i:02d}"
        r = client.post(
            "/webhook/mensagem",
            json={
                "instance": inst,
                "telefone": tel,
                "texto": "READ",  # alguns provedores mandam placeholder
                "provider_message_id": f"EVT-{tipo}-{i}",
                "from_me": True,
                "tipo": tipo,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["bot_ativo"] is True
        assert body.get("ignorada") is True
        assert client.get(f"/v1/conversas/{tel}/estado", headers=h).json()["bot_ativo"] is True


def test_reativacao_apos_auto_pausa(client, loja_a):
    """PATCH bot_ativo=true devolve o bot depois da auto-pausa por from_me (standalone)."""
    tel, h = "5511977700033", loja_a["headers"]
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": tel,
            "texto": "Atendente no celular",
            "provider_message_id": "MANUAL-REATIVAR",
            "from_me": True,
        },
    )
    assert r.json()["bot_ativo"] is False

    devolver = client.patch(
        f"/v1/conversas/{tel}/estado", json={"bot_ativo": True}, headers=h
    )
    assert devolver.json() == {"bot_ativo": True, "status": "aberta"}

    # Próxima entrada do cliente ainda vê bot ativo (gate do n8n usaria bot_ativo).
    inbound = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": tel,
            "texto": "oi de novo",
            "provider_message_id": "IN-APOS-REATIVAR",
        },
    )
    assert inbound.json()["bot_ativo"] is True
