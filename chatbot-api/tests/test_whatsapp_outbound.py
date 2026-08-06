"""EvolutionWhatsAppOutbound.send_text: erro do Evolution desmascarado e sem PII."""
import logging

import httpx
import pytest

from app.whatsapp_outbound import EvolutionWhatsAppOutbound, WhatsAppOutboundError


def _outbound(handler):
    return EvolutionWhatsAppOutbound(
        base_url="http://evo.local",
        api_key="k-secreta",
        timeout=2.0,
        transport=httpx.MockTransport(handler),
    )


def test_sucesso_retorna_payload_do_provedor():
    def handler(request):
        assert request.url.path == "/message/sendText/loja1-ab12"
        assert request.headers["apikey"] == "k-secreta"
        return httpx.Response(200, json={"key": {"id": "msg-1"}})

    dados = _outbound(handler).send_text(
        instance="loja1-ab12", number="120363@g.us", text="oi"
    )
    assert dados == {"key": {"id": "msg-1"}}


def test_grupo_sem_participante_classifica_forbidden():
    def handler(request):
        return httpx.Response(
            400, json={"status": 400, "error": "Bad Request", "message": "not-authorized"}
        )

    with pytest.raises(WhatsAppOutboundError) as exc:
        _outbound(handler).send_text(
            instance="loja1-ab12", number="120363@g.us", text="alerta"
        )
    assert exc.value.code == "evolution_group_forbidden"
    assert "HTTP 400" in str(exc.value)


def test_grupo_inexistente_classifica_target_not_found():
    def handler(request):
        return httpx.Response(400, json={"response": {"message": "item-not-found"}})

    with pytest.raises(WhatsAppOutboundError) as exc:
        _outbound(handler).send_text(
            instance="loja1-ab12", number="120363@g.us", text="alerta"
        )
    assert exc.value.code == "evolution_target_not_found"


def test_erro_desconhecido_mantem_code_generico():
    def handler(request):
        return httpx.Response(500, text="Internal Server Error")

    with pytest.raises(WhatsAppOutboundError) as exc:
        _outbound(handler).send_text(
            instance="loja1-ab12", number="120363@g.us", text="alerta"
        )
    assert exc.value.code == "evolution_send_failed"


def test_log_do_corpo_redige_pii_e_nao_vaza_apikey(caplog):
    # O provedor ecoa o texto enviado (com CPF/nascimento) no corpo do erro.
    def handler(request):
        return httpx.Response(
            400,
            text='{"error":"forbidden","echo":"CPF 12345678901 nasc 01011990 k-secreta"}',
        )

    with caplog.at_level(logging.WARNING, logger="chatbot.whatsapp_outbound"):
        with pytest.raises(WhatsAppOutboundError):
            _outbound(handler).send_text(
                instance="loja1-ab12", number="120363@g.us", text="alerta"
            )

    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "12345678901" not in registro  # CPF redigido
    assert "01011990" not in registro  # nascimento redigido
    assert "[num]" in registro
    assert "k-secreta" not in registro  # apikey nunca no log
