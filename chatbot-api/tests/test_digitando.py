"""O "digitando…" do Modo 2: acende, mas nunca às custas da resposta.

O indicador é enfeite. Estes testes existem para travar o comportamento que
importa quando ele falha — a resposta ao cliente segue — e para provar que o
Modo 1 não é tocado, porque lá quem mostra "digitando…" é a Evolution pelo
``delay`` que já viaja no envio.
"""
import httpx
import pytest

from app import servico, whatsapp_outbound
from app.whatsapp_outbound import CloudWhatsAppOutbound, acender_digitando


def _cloud(handler):
    return CloudWhatsAppOutbound(
        base_url="https://graph.test/v21.0",
        token="tok",
        transport=httpx.MockTransport(handler),
    )


def test_modo1_nao_acende_nada(db, loja_a):
    """Loja fora do Modo 2 devolve o port da Evolution: nada a fazer aqui."""
    assert acender_digitando(
        db, loja_a["loja_id"], instance=loja_a["instance"], wamid="wamid.X"
    ) is False


def test_acende_quando_a_loja_fala_pela_central_cloud(db, loja_a, monkeypatch):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(str(request.url))
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(
        whatsapp_outbound, "outbound_para_loja", lambda *a, **k: _cloud(handler)
    )

    assert acender_digitando(
        db, loja_a["loja_id"], instance="1227059273831581", wamid="wamid.CLIENTE"
    ) is True
    assert len(chamadas) == 1
    assert "/1227059273831581/messages" in chamadas[0]


def test_falha_da_meta_nao_propaga(db, loja_a, monkeypatch):
    """O ponto inteiro do módulo.

    Se a Meta recusar o indicador e isto levantar, o ``pode-responder`` devolve
    500, o n8n para e o cliente fica sem resposta — trocando uma mensagem por
    uma animação. Tem que degradar para ``False``.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "invalid wamid"}})

    monkeypatch.setattr(
        whatsapp_outbound, "outbound_para_loja", lambda *a, **k: _cloud(handler)
    )

    assert acender_digitando(
        db, loja_a["loja_id"], instance="123", wamid="wamid.VELHO"
    ) is False


def test_sem_wamid_nao_chama_a_meta(db, loja_a, monkeypatch):
    """Sem o wamid do cliente a chamada é inválida — não gaste o round-trip."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        pytest.fail("não deveria chamar a Meta sem wamid")

    monkeypatch.setattr(
        whatsapp_outbound, "outbound_para_loja", lambda *a, **k: _cloud(handler)
    )

    assert acender_digitando(db, loja_a["loja_id"], instance="123", wamid="") is False


def test_rota_pode_responder_segue_respondendo_o_mesmo(client, db, loja_b):
    """Regressão: o indicador entrou na rota sem mudar o contrato com o n8n."""
    tel = "5511977719001"
    client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_b["instance"],
            "telefone": tel,
            "texto": "tem a biz 125?",
            "provider_message_id": "DIGIT-1",
        },
    )
    token = servico.criar_credencial_integracao(db)

    r = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_b["instance"], "provider_message_id": "DIGIT-1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200
    assert r.json()["pode_responder"] is True
