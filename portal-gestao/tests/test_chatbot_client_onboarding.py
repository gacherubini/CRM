"""O erro de elo tem de sobreviver a viagem ate a tela.

`_request` engole todo HTTPStatusError em ChatbotIndisponivel. Sem escape, o
502 com o elo vira "nao foi possivel acessar o chatbot agora", e o lojista le
"erro de conexao" quando a Meta e que recusou o registro do numero.
"""
import httpx
import pytest

from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel, OnboardingFalhou


def _cliente(handler):
    return ChatbotClient(
        base_url="http://chatbot.test",
        token="tok",
        transport=httpx.MockTransport(handler),
        retries=0,
    )


def test_erro_de_elo_chega_com_o_numero_do_elo():
    def handler(pedido):
        return httpx.Response(
            502,
            json={"detail": {"elo": 3, "mensagem": "a Meta bloqueou por 72 horas"}},
        )

    with pytest.raises(OnboardingFalhou) as erro:
        _cliente(handler).conectar_whatsapp_cloud(
            code="c", waba_id="w", phone_number_id="p", business_id="b"
        )

    assert erro.value.elo == 3
    assert "72 horas" in str(erro.value)


def test_chatbot_fora_do_ar_continua_indisponivel():
    """Regressao: falha de REDE nao pode virar erro de elo — sao coisas
    diferentes para quem le a tela."""
    def handler(pedido):
        raise httpx.ConnectError("sem rota")

    with pytest.raises(ChatbotIndisponivel):
        _cliente(handler).conectar_whatsapp_cloud(
            code="c", waba_id="w", phone_number_id="p", business_id="b"
        )


def test_sucesso_devolve_o_estado_do_canal():
    def handler(pedido):
        return httpx.Response(
            200, json={"canal_id": "c1", "estado": "cloud_pendente", "onboarding_elo": 5}
        )

    resposta = _cliente(handler).conectar_whatsapp_cloud(
        code="c", waba_id="w", phone_number_id="p", business_id="b"
    )

    assert resposta["estado"] == "cloud_pendente"
