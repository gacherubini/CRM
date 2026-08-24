import json
import httpx

from app.whatsapp_outbound import CloudWhatsAppOutbound


def _cloud(handler):
    return CloudWhatsAppOutbound(
        base_url="https://graph.test/v21.0",
        token="tok",
        transport=httpx.MockTransport(handler),
    )


def test_send_text_usa_o_phone_number_id_como_instancia():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["json"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    _cloud(handler).send_text(instance="1234567890", number="5511988887777", text="oi")

    assert "/1234567890/messages" in capturado["url"]
    assert b'"type": "text"' in capturado["json"] or b'"type":"text"' in capturado["json"]


def test_template_carrega_o_oferta_id_no_payload_do_botao():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["json"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.Y"}]})

    _cloud(handler).send_template_button(
        instance="123", number="5511999990000",
        template="chama_vendedor", variaveis=["Ana", "Biz 125"],
        oferta_id="of-42",
    )

    assert b"pego:of-42" in capturado["json"]


def test_interativo_carrega_o_mesmo_id():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["json"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.Z"}]})

    _cloud(handler).send_interactive_button(
        instance="123", number="5511999990000",
        texto="Lead novo: Ana, Biz 125", oferta_id="of-42",
    )

    assert b"pego:of-42" in capturado["json"]


def test_digitando_vai_no_endpoint_de_messages_com_o_wamid_do_cliente():
    """O indicador não é parâmetro de envio: é um POST próprio, com o wamid.

    Se algum dia isto virar campo do ``send_text``, o teste quebra — e é para
    quebrar: na Cloud API os dois são chamadas distintas.
    """
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["json"] = json.loads(request.read())
        return httpx.Response(200, json={"success": True})

    _cloud(handler).marcar_lido_e_digitando(
        instance="1227059273831581", wamid="wamid.CLIENTE"
    )

    assert "/1227059273831581/messages" in capturado["url"]
    assert capturado["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.CLIENTE",
        "typing_indicator": {"type": "text"},
    }
