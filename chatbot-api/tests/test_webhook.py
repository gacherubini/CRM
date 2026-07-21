import logging

import pytest

from app import config, servico
from app.hardening import webhook_rate_limiter


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


@pytest.mark.parametrize(
    "telefone",
    ["", "1234567", "1234567890123456", "55abc11999999999"],
)
def test_webhook_rejeita_telefone_invalido_sem_ecoa_lo(client, loja_a, telefone):
    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"], telefone=telefone),
    )

    assert r.status_code == 422
    assert r.json() == {"detail": "payload do webhook inválido"}
    if telefone:
        assert telefone not in r.text


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("+55 (11) 98888-7777", "5511988887777"),
        ("5511988887777@s.whatsapp.net", "5511988887777"),
    ],
)
def test_webhook_normaliza_telefone_antes_de_persistir(
    client, loja_a, entrada, esperado
):
    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"], telefone=entrada),
    )

    assert r.status_code == 200
    conversas = client.get(
        "/v1/conversas", headers=loja_a["headers"]
    ).json()["conversas"]
    assert conversas[0]["telefone"] == esperado


def test_webhook_limita_texto_sem_devolver_conteudo(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_MAX_TEXT_CHARS", 5)
    texto_sensivel = "segredo-pessoal"

    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"], texto=texto_sensivel),
    )

    assert r.status_code == 422
    assert r.json() == {"detail": "payload do webhook inválido"}
    assert texto_sensivel not in r.text


def test_webhook_rejeita_campos_fora_do_contrato(client, loja_a):
    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"], token="nao-deveria-estar-aqui"),
    )

    assert r.status_code == 422
    assert "nao-deveria-estar-aqui" not in r.text


def test_webhook_rejeita_payload_acima_do_limite_antes_do_parse(
    client, loja_a, monkeypatch
):
    monkeypatch.setattr(config, "WEBHOOK_MAX_PAYLOAD_BYTES", 128)
    texto_sensivel = "dado-pessoal-" * 40

    r = client.post(
        "/webhook/mensagem",
        json=_msg(loja_a["instance"], texto=texto_sensivel),
    )

    assert r.status_code == 413
    assert r.headers["content-type"].startswith("application/json")
    assert texto_sensivel not in r.text


def test_webhook_rate_limit_configuravel_retorna_retry_after(
    client, loja_a, monkeypatch
):
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_WINDOW_SECONDS", 60)
    webhook_rate_limiter.reset()

    try:
        primeira = client.post(
            "/webhook/mensagem",
            json=_msg(loja_a["instance"], provider_message_id="RL-1"),
        )
        segunda = client.post(
            "/webhook/mensagem",
            json=_msg(loja_a["instance"], provider_message_id="RL-2"),
        )
        bloqueada = client.post(
            "/webhook/mensagem",
            json=_msg(loja_a["instance"], provider_message_id="RL-3"),
        )
    finally:
        webhook_rate_limiter.reset()

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert bloqueada.status_code == 429
    assert int(bloqueada.headers["retry-after"]) >= 1


def test_webhook_rate_limit_pode_ser_desligado(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_REQUESTS", 0)
    webhook_rate_limiter.reset()

    respostas = [
        client.post(
            "/webhook/mensagem",
            json=_msg(loja_a["instance"], provider_message_id=f"OFF-{indice}"),
        )
        for indice in range(3)
    ]

    assert [r.status_code for r in respostas] == [200, 200, 200]


def test_tentativa_com_token_invalido_tambem_consome_rate_limit(
    client, loja_a, monkeypatch
):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "token-correto")
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_WINDOW_SECONDS", 60)
    webhook_rate_limiter.reset()

    try:
        invalida = client.post(
            "/webhook/mensagem",
            json=_msg(loja_a["instance"]),
            headers={"X-Webhook-Token": "token-incorreto"},
        )
        bloqueada = client.post(
            "/webhook/mensagem",
            json=_msg(loja_a["instance"]),
            headers={"X-Webhook-Token": "token-correto"},
        )
    finally:
        webhook_rate_limiter.reset()

    assert invalida.status_code == 401
    assert bloqueada.status_code == 429


def test_logs_de_bloqueio_nao_expoem_pii_instancia_ou_token(
    client, loja_a, monkeypatch, caplog
):
    token = "token-webhook-super-secreto"
    telefone = "5511987654321"
    texto = "Maria pediu proposta confidencial"
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", token)
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(config, "WEBHOOK_RATE_LIMIT_WINDOW_SECONDS", 60)
    webhook_rate_limiter.reset()
    caplog.set_level(logging.WARNING, logger="chatbot.webhook")
    headers = {"X-Webhook-Token": token}

    try:
        client.post(
            "/webhook/mensagem",
            json=_msg(
                loja_a["instance"],
                telefone=telefone,
                texto=texto,
                provider_message_id="LOG-1",
            ),
            headers=headers,
        )
        bloqueada = client.post(
            "/webhook/mensagem",
            json=_msg(
                loja_a["instance"],
                telefone=telefone,
                texto=texto,
                provider_message_id="LOG-2",
            ),
            headers=headers,
        )
    finally:
        webhook_rate_limiter.reset()

    assert bloqueada.status_code == 429
    assert "limite de requisições excedido" in caplog.text
    for sensivel in (token, telefone, texto, loja_a["instance"]):
        assert sensivel not in caplog.text
