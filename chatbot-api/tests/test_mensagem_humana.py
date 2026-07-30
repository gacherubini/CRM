"""POST /v1/conversas/{telefone}/mensagens — envio humano (Portal Atendimento)."""
import json

import httpx

from app.whatsapp_outbound import (
    EvolutionWhatsAppOutbound,
    FakeWhatsAppOutbound,
    set_whatsapp_outbound,
)


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


def test_envia_mensagem_humana_e_pausa_bot(client, loja_a, _fake_whatsapp_outbound):
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
    assert body.get("evolution_instance") == loja_a["instance"]

    # Push Evolution com a instância da conversa/loja.
    assert len(_fake_whatsapp_outbound.calls) == 1
    call = _fake_whatsapp_outbound.calls[0]
    assert call["instance"] == loja_a["instance"]
    assert call["number"] == tel
    assert call["text"] == "Olá, sou o vendedor Ana."

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


def test_mensagem_humana_idempotente_nao_reenvia_evolution(
    client, loja_a, _fake_whatsapp_outbound
):
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

    # Uma única chamada Evolution (segunda é dedupe por provider_message_id).
    assert len(_fake_whatsapp_outbound.calls) == 1

    msgs = client.get(
        f"/v1/conversas/{tel}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    saidas = [m for m in msgs if m["direcao"] == "saida" and m["texto"] == "Mensagem única"]
    assert len(saidas) == 1


def test_mensagem_humana_nao_cruza_loja(client, loja_a, loja_b, _fake_whatsapp_outbound):
    tel = _seed_conversa(client, loja_a, telefone="5511987000003")
    # Loja B tenta enviar no mesmo telefone — cria conversa dela, sem ver msgs da A.
    r = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_b["headers"],
        json={"texto": "da loja B", "idempotency_key": "b-1"},
    )
    assert r.status_code == 200
    # Envios usam a instância da loja autenticada, nunca a da outra.
    instances = {c["instance"] for c in _fake_whatsapp_outbound.calls}
    assert loja_b["instance"] in instances
    assert loja_a["instance"] not in instances or any(
        c["text"] != "da loja B" for c in _fake_whatsapp_outbound.calls
    )
    envio_b = [c for c in _fake_whatsapp_outbound.calls if c["text"] == "da loja B"]
    assert len(envio_b) == 1
    assert envio_b[0]["instance"] == loja_b["instance"]

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


def test_mensagem_humana_evolution_down_preserva_historico_e_handoff(
    client, loja_a, _fake_whatsapp_outbound
):
    """Evolution fora: 502, mensagem no histórico, bot permanece pausado."""
    tel = _seed_conversa(client, loja_a, telefone="5511987000005")
    _fake_whatsapp_outbound.fail = True
    _fake_whatsapp_outbound.fail_code = "evolution_unreachable"
    _fake_whatsapp_outbound.fail_message = "não foi possível contatar a Evolution"

    r = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_a["headers"],
        json={
            "texto": "Tentativa com Evolution down",
            "idempotency_key": "fail-evo-1",
            "ator": "ana@loja.test",
        },
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "evolution_unreachable"
    assert detail["enviado"] is False
    assert detail["bot_ativo"] is False
    assert detail["status"] == "handoff"
    assert detail["preservado_no_historico"] is True
    assert detail["mensagem_id"]

    # Bot continua em handoff.
    estado = client.get(
        f"/v1/conversas/{tel}/estado", headers=loja_a["headers"]
    ).json()
    assert estado["bot_ativo"] is False
    assert estado["status"] == "handoff"

    # Mensagem permanece no histórico da loja.
    msgs = client.get(
        f"/v1/conversas/{tel}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    assert any(m["texto"] == "Tentativa com Evolution down" for m in msgs)

    # Retry com a mesma chave não reenvia (dedupe; não tenta Evolution de novo).
    _fake_whatsapp_outbound.fail = False
    r2 = client.post(
        f"/v1/conversas/{tel}/mensagens",
        headers=loja_a["headers"],
        json={
            "texto": "Tentativa com Evolution down",
            "idempotency_key": "fail-evo-1",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["duplicada"] is True
    # Apenas a tentativa original (falha) gerou call; retry não chama de novo.
    assert len(_fake_whatsapp_outbound.calls) == 1


def test_mensagem_humana_evolution_http_mocktransport_sucesso(client, loja_a):
    """Adapter HTTP real com MockTransport: path/body corretos."""
    tel = _seed_conversa(client, loja_a, telefone="5511987000006")
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        assert request.method == "POST"
        assert f"/message/sendText/{loja_a['instance']}" in str(request.url)
        assert request.headers.get("apikey") == "test-api-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["number"] == tel
        assert payload["text"] == "texto mock"
        return httpx.Response(200, json={"key": {"id": "evo-1"}})

    set_whatsapp_outbound(
        EvolutionWhatsAppOutbound(
            base_url="http://evolution.test",
            api_key="test-api-key",
            timeout=2.0,
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        r = client.post(
            f"/v1/conversas/{tel}/mensagens",
            headers=loja_a["headers"],
            json={
                "texto": "texto mock",
                "idempotency_key": "mock-transport-1",
            },
        )
        assert r.status_code == 200
        assert r.json()["enviado"] is True
        assert len(requests_seen) == 1
    finally:
        set_whatsapp_outbound(FakeWhatsAppOutbound())


def test_mensagem_humana_evolution_http_mocktransport_down(client, loja_a):
    tel = _seed_conversa(client, loja_a, telefone="5511987000007")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    set_whatsapp_outbound(
        EvolutionWhatsAppOutbound(
            base_url="http://evolution.test",
            api_key="test-api-key",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        r = client.post(
            f"/v1/conversas/{tel}/mensagens",
            headers=loja_a["headers"],
            json={
                "texto": "vai falhar na evolution",
                "idempotency_key": "mock-down-1",
            },
        )
        assert r.status_code == 502
        detail = r.json()["detail"]
        assert detail["enviado"] is False
        assert detail["preservado_no_historico"] is True
        assert detail["bot_ativo"] is False

        msgs = client.get(
            f"/v1/conversas/{tel}/mensagens", headers=loja_a["headers"]
        ).json()["mensagens"]
        assert any(m["texto"] == "vai falhar na evolution" for m in msgs)
    finally:
        set_whatsapp_outbound(FakeWhatsAppOutbound())
