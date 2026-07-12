from app import config, servico


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


def test_webhook_sem_token_configurado_permanece_aberto(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "")
    r = client.post("/webhook/mensagem", json=_msg(loja_a["instance"]))
    assert r.status_code == 200


def test_webhook_com_token_exige_header(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "segredo-123")
    sem = client.post("/webhook/mensagem", json=_msg(loja_a["instance"]))
    assert sem.status_code == 401


def test_webhook_com_token_e_header_correto(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "segredo-123")
    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"]),
        headers={"X-Webhook-Token": "segredo-123"},
    )
    assert r.status_code == 200
    assert r.json()["duplicada"] is False


def test_webhook_com_token_e_header_errado_401(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "segredo-123")
    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"]),
        headers={"X-Webhook-Token": "errado"},
    )
    assert r.status_code == 401


def test_webhook_corrida_retorna_duplicada_nao_500(client, loja_a, monkeypatch):
    inst = loja_a["instance"]
    # Grava a primeira mensagem normalmente.
    r1 = client.post("/webhook/mensagem", json=_msg(inst, provider_message_id="RACE-1"))
    assert r1.json()["duplicada"] is False

    # Simula a corrida: o SELECT rápido "não vê" a linha concorrente; a UNIQUE
    # do banco arbitra no commit e o serviço responde idempotente (sem 500).
    monkeypatch.setattr(servico, "_mensagem_existente", lambda *a, **k: None)
    r2 = client.post("/webhook/mensagem", json=_msg(inst, provider_message_id="RACE-1"))
    assert r2.status_code == 200
    assert r2.json()["duplicada"] is True
    assert r2.json()["conversa_id"] == r1.json()["conversa_id"]
