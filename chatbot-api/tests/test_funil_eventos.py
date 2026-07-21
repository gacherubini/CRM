def _registrar_lead(client, loja, telefone, nome):
    resposta = client.post(
        "/v1/leads",
        headers=loja["headers"],
        json={"telefone": telefone, "nome": nome, "interesse": "veículo"},
    )
    assert resposta.status_code == 201
    return resposta.json()


def _mensagem(client, loja, telefone, *, texto, message_id, from_me=False):
    resposta = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja["instance"],
            "telefone": telefone,
            "texto": texto,
            "provider_message_id": message_id,
            "from_me": from_me,
            "origem_bot": from_me,
        },
    )
    assert resposta.status_code == 200


def test_exporta_lead_e_primeira_resposta_sem_pii(client, loja_a):
    telefone = "5511998877665"
    lead = _registrar_lead(client, loja_a, telefone, "Cliente Sigiloso")
    _mensagem(
        client,
        loja_a,
        telefone,
        texto="Meu CPF não deve sair daqui",
        message_id="FUNIL-IN-1",
    )
    _mensagem(
        client,
        loja_a,
        telefone,
        texto="Resposta reservada",
        message_id="FUNIL-OUT-1",
        from_me=True,
    )

    primeira = client.get("/v1/funil/eventos", headers=loja_a["headers"])
    segunda = client.get("/v1/funil/eventos", headers=loja_a["headers"])

    assert primeira.status_code == 200
    assert primeira.json() == segunda.json()
    eventos = [
        evento
        for evento in primeira.json()["eventos"]
        if evento["lead_ref"] == lead["id"]
    ]
    assert [evento["tipo"] for evento in eventos] == [
        "lead_criado",
        "primeira_resposta",
    ]
    assert all(evento["payload"] is None for evento in eventos)
    serializado = primeira.text
    for sensivel in (telefone, "Cliente Sigiloso", "Meu CPF", "Resposta reservada"):
        assert sensivel not in serializado


def test_exportacao_do_funil_isola_lojas(client, loja_a, loja_b):
    lead_a = _registrar_lead(client, loja_a, "5511988877001", "Pessoa A")
    lead_b = _registrar_lead(client, loja_b, "5511988877002", "Pessoa B")

    eventos_a = client.get(
        "/v1/funil/eventos", headers=loja_a["headers"]
    ).json()["eventos"]

    refs = {evento["lead_ref"] for evento in eventos_a}
    assert lead_a["id"] in refs
    assert lead_b["id"] not in refs
