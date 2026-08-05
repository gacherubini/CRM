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
    assert body["primeira_mensagem"] is True
    assert body["conversa_id"]


def test_webhook_marca_apenas_a_primeira_entrada_do_cliente(client, loja_a):
    inst = loja_a["instance"]

    primeira = client.post(
        "/webhook/mensagem",
        json=_msg(inst, provider_message_id="FIRST-1", texto="oi"),
    )
    segunda = client.post(
        "/webhook/mensagem",
        json=_msg(inst, provider_message_id="FIRST-2", texto="quero ver as motos"),
    )

    assert primeira.json()["primeira_mensagem"] is True
    assert segunda.json()["primeira_mensagem"] is False


def test_webhook_expoe_tem_saida_e_historico_recente(client, loja_a):
    """Gate n8n e prompt da IA usam tem_saida + historico_recente do registrar."""
    inst = loja_a["instance"]
    r1 = client.post(
        "/webhook/mensagem",
        json=_msg(inst, provider_message_id="HIST-1", texto="tem biz?"),
    )
    body1 = r1.json()
    assert body1["tem_saida"] is False
    assert body1["historico_recente"] == ""

    # Saída do bot
    client.post(
        "/webhook/mensagem",
        json=_msg(
            inst,
            provider_message_id="HIST-OUT",
            texto="tenho uma biz 2022",
            from_me=True,
            origem_bot=True,
        ),
    )
    r2 = client.post(
        "/webhook/mensagem",
        json=_msg(inst, provider_message_id="HIST-2", texto="qual o preco"),
    )
    body2 = r2.json()
    assert body2["tem_saida"] is True
    assert "[entrada] tem biz?" in body2["historico_recente"]
    assert "[saida] tenho uma biz 2022" in body2["historico_recente"]
    # histórico é anterior à msg atual
    assert "qual o preco" not in body2["historico_recente"]


def test_webhook_preserva_cpf_cliente_mascarado_no_historico(client, loja_a):
    """CPF real fica em cpf_cliente (tool); texto/histórico ficam mascarados (UI).

    Regressão 2026-08-05 ***2308: Agent lia só o histórico mascarado e o simular1
    rejeitava com faltando=cpf sem criar alerta no grupo.
    """
    inst = loja_a["instance"]
    tel = "5511912152308"
    r1 = client.post(
        "/webhook/mensagem",
        json=_msg(
            inst,
            telefone=tel,
            provider_message_id="CPF-TURN-1",
            texto="11144477735",
        ),
    )
    body1 = r1.json()
    assert body1["cpf_cliente"] == "11144477735"
    # histórico desta resposta é anterior à msg atual (ainda vazio de CPF)
    assert "11144477735" not in body1.get("historico_recente", "")

    r2 = client.post(
        "/webhook/mensagem",
        json=_msg(
            inst,
            telefone=tel,
            provider_message_id="CPF-TURN-2",
            texto="17/05/2005",
        ),
    )
    body2 = r2.json()
    # turn seguinte ainda expõe o CPF capturado, mesmo com texto mascarado no histórico
    assert body2["cpf_cliente"] == "11144477735"
    assert "*********35" in body2["historico_recente"]
    assert "11144477735" not in body2["historico_recente"]


def test_moto_escolhida_persiste_e_aparece_no_webhook(client, loja_a):
    """Moto única do estoque sobrevive em tracking e volta no registrar (simular1).

    Regressão 2026-08-05 ***9992: n8n static data sumiu entre consulta e simulação;
    simular1 falhou com precisa_escolher_moto e o agent confirmou à toa.
    """
    inst = loja_a["instance"]
    tel = "5511983189992"
    headers = loja_a["headers"]

    # conversa precisa existir
    r0 = client.post(
        "/webhook/mensagem",
        json=_msg(inst, telefone=tel, provider_message_id="MOTO-0", texto="oi"),
    )
    assert r0.status_code == 200
    assert r0.json().get("moto_escolhida") in (None, {})

    r_save = client.post(
        "/v1/operacao/moto-escolhida",
        headers=headers,
        json={
            "telefone": tel,
            "instance": inst,
            "id": "veh-twister-1",
            "placa": "ABC1D23",
            "valor": 21900,
            "categoria": "moto",
            "interesse": "honda cb 250 twister 2021",
        },
    )
    assert r_save.status_code == 200, r_save.text
    body_save = r_save.json()
    assert body_save["ok"] is True
    assert body_save["moto_escolhida"]["placa"] == "ABC1D23"
    assert body_save["moto_escolhida"]["valor"] == 21900

    r1 = client.post(
        "/webhook/mensagem",
        json=_msg(
            inst,
            telefone=tel,
            provider_message_id="MOTO-1",
            texto="quero simular",
        ),
    )
    assert r1.status_code == 200
    moto = r1.json().get("moto_escolhida")
    assert moto is not None
    assert moto["placa"] == "ABC1D23"
    assert moto["interesse"] == "honda cb 250 twister 2021"

    # limpar (busca ambígua / payload vazio)
    r_clear = client.post(
        "/v1/operacao/moto-escolhida",
        headers=headers,
        json={"telefone": tel, "instance": inst},
    )
    assert r_clear.status_code == 200
    assert r_clear.json()["moto_escolhida"] is None

    r2 = client.post(
        "/webhook/mensagem",
        json=_msg(
            inst,
            telefone=tel,
            provider_message_id="MOTO-2",
            texto="ainda quero",
        ),
    )
    assert r2.json().get("moto_escolhida") in (None, {})


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
