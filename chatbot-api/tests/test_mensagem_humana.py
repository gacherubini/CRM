"""POST /v1/conversas/{telefone}/mensagens — envio humano (Portal Atendimento)."""


def _seed_conversa(client, loja_a, telefone="5511987000001"):
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": telefone,
            "texto": "oi quero um carro",
            "provider_message_id": f"in-{telefone}",
            "from_me": False,
        },
    )
    assert r.status_code == 200
    return telefone


def test_envia_mensagem_humana_e_pausa_bot(client, loja_a):
    tel = _seed_conversa(client, loja_a)
    r = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_a["headers"],
        json={
            "texto": "Olá, sou o vendedor Ana.",
            "idempotency_key": "portal-msg-1",
            "ator": "ana@loja.test",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["duplicada"] is False
    assert body["bot_ativo"] is False
    assert body["status"] == "handoff"
    assert body["enviado"] is True

    estado = client.get(
        f"/v1/conversas/{tel}/estado", headers=loja_a["headers"]
    ).json()
    assert estado["bot_ativo"] is False

    msgs = client.get(
        f"/v1/conversas/{tel}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    textos = [m["texto"] for m in msgs]
    assert "Olá, sou o vendedor Ana." in textos
    assert any(m["direcao"] == "saida" for m in msgs)


def test_mensagem_humana_idempotente(client, loja_a):
    tel = _seed_conversa(client, loja_a, telefone="5511987000002")
    payload = {
        "texto": "Mensagem única",
        "idempotency_key": "same-key-xyz",
    }
    r1 = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_a["headers"],
        json=payload,
    )
    r2 = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_a["headers"],
        json=payload,
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    assert r1.json()["mensagem_id"] == r2.json()["mensagem_id"]

    msgs = client.get(
        f"/v1/conversas/{tel}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    saidas = [m for m in msgs if m["direcao"] == "saida" and m["texto"] == "Mensagem única"]
    assert len(saidas) == 1


def test_mensagem_humana_nao_cruza_loja(client, loja_a, loja_b):
    tel = _seed_conversa(client, loja_a, telefone="5511987000003")
    # Loja B tenta enviar no mesmo telefone — cria conversa dela, sem ver msgs da A.
    r = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_b["headers"],
        json={"texto": "da loja B", "idempotency_key": "b-1"},
    )
    assert r.status_code == 200

    msgs_a = client.get(
        f"/v1/conversas/{tel}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    textos_a = [m["texto"] for m in msgs_a]
    assert "da loja B" not in textos_a
    assert "oi quero um carro" in textos_a

    msgs_b = client.get(
        f"/v1/conversas/{tel}/mensagens", headers=loja_b["headers"]
    ).json()["mensagens"]
    assert any(m["texto"] == "da loja B" for m in msgs_b)


def test_mensagem_humana_exige_auth(client, loja_a):
    tel = _seed_conversa(client, loja_a, telefone="5511987000004")
    r = client.post(
        f"/v1/conversas/{tel}/mensagens",
        json={"texto": "sem token", "idempotency_key": "x"},
    )
    assert r.status_code in {401, 403}
