def _msg(instance, **over):
    base = {
        "instance": instance,
        "telefone": "5511988887777",
        "texto": "quero financiar uma moto",
        "provider_message_id": "MSG-1",
    }
    base.update(over)
    return base


def test_webhook_cria_conversa_e_registra(client, loja_a):
    r = client.post("/webhook/mensagem", json=_msg(loja_a["instance"]))
    assert r.status_code == 200
    body = r.json()
    assert body["duplicada"] is False
    assert body["bot_ativo"] is True
    assert body["conversa_id"]


def test_webhook_idempotente_por_provider_message_id(client, loja_a):
    inst = loja_a["instance"]
    r1 = client.post("/webhook/mensagem", json=_msg(inst))
    r2 = client.post("/webhook/mensagem", json=_msg(inst))
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    # mesma conversa nas duas
    assert r1.json()["conversa_id"] == r2.json()["conversa_id"]


def test_webhook_instancia_desconhecida_404(client):
    r = client.post("/webhook/mensagem", json=_msg("instancia-fantasma"))
    assert r.status_code == 404
