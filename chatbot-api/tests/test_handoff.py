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
