"""Os quatro elos que falam com a Graph (spec §7).

Nenhum teste toca a rede: httpx.MockTransport, mesmo padrao de
CloudWhatsAppOutbound (app/whatsapp_outbound.py:238).

Os elos 2 e 4 sao IDEMPOTENTES de proposito. `subscribed_apps` repetido nao doi
e template ja existente e SUCESSO, nao erro: tratar isso como falha transforma
retry inofensivo em laco.
"""
import json

import httpx
import pytest

from app.meta_onboarding import MetaOnboarding, OnboardingErro


def _cliente(handler):
    return MetaOnboarding(
        base_url="https://graph.test/v21.0",
        app_id="app-1",
        app_secret="segredo-do-revy",
        transport=httpx.MockTransport(handler),
    )


def test_elo_1_troca_code_por_token():
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        return httpx.Response(200, json={"access_token": "EAAG-token-da-loja"})

    assert _cliente(handler).trocar_code_por_token("code-do-popup") == "EAAG-token-da-loja"
    assert "/oauth/access_token" in visto["url"]
    assert "client_id=app-1" in visto["url"]
    assert "code=code-do-popup" in visto["url"]


def test_elo_1_sem_token_na_resposta_e_erro_do_elo_1():
    """Resposta 200 sem access_token existe: o code expirou (TTL 30 s)."""
    handler = lambda pedido: httpx.Response(200, json={})

    with pytest.raises(OnboardingErro) as erro:
        _cliente(handler).trocar_code_por_token("code-velho")
    assert erro.value.elo == 1


def test_elo_1_nao_vaza_o_app_secret_na_mensagem_de_erro():
    """Corpo de erro da Meta ecoa parametros. A mensagem e nossa, nao a dela."""
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"message": "invalid client_secret segredo-do-revy"}}
    )

    with pytest.raises(OnboardingErro) as erro:
        _cliente(handler).trocar_code_por_token("code-do-popup")
    assert "segredo-do-revy" not in str(erro.value)


def test_elo_2_inscreve_o_app_na_waba():
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        visto["auth"] = pedido.headers.get("authorization")
        return httpx.Response(200, json={"success": True})

    _cliente(handler).inscrever_app(waba_id="waba-1", token="EAAG-token-da-loja")

    assert visto["url"].endswith("/waba-1/subscribed_apps")
    # O token e o DA LOJA, nao o global do Revy: e o que da escopo na WABA dela.
    assert visto["auth"] == "Bearer EAAG-token-da-loja"


def test_elo_2_ja_inscrito_nao_e_erro():
    """Idempotente: repetir nao doi. Foi este elo que falhou calado em 23/08."""
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"code": 100, "message": "already subscribed"}}
    )

    _cliente(handler).inscrever_app(waba_id="waba-1", token="tok")


def test_elo_3_registra_com_pin():
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        visto["corpo"] = json.loads(pedido.content)
        return httpx.Response(200, json={"success": True})

    _cliente(handler).registrar_numero(
        phone_number_id="123", pin="048512", token="tok"
    )

    assert visto["url"].endswith("/123/register")
    assert visto["corpo"] == {"messaging_product": "whatsapp", "pin": "048512"}


def test_elo_3_teto_da_meta_vira_erro_nomeado():
    """133016 = teto de 10/72h estourado. O numero fica travado por tres dias,
    entao quem chama precisa distinguir isto de uma falha qualquer."""
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"code": 133016, "message": "rate limit"}}
    )

    with pytest.raises(OnboardingErro) as erro:
        _cliente(handler).registrar_numero(phone_number_id="123", pin="048512", token="tok")
    assert erro.value.elo == 3
    assert "72" in str(erro.value), "a mensagem tem de dizer ao lojista quanto tempo"


def test_elo_4_cria_o_template_no_formato_do_envio():
    """Tem de casar com send_template_button (whatsapp_outbound.py:289): uma
    variavel no corpo e um QUICK_REPLY no indice 0. Divergiu, o envio falha."""
    visto = {}

    def handler(pedido: httpx.Request) -> httpx.Response:
        visto["url"] = str(pedido.url)
        visto["corpo"] = json.loads(pedido.content)
        return httpx.Response(200, json={"id": "tpl-1", "status": "PENDING"})

    _cliente(handler).criar_template(waba_id="waba-1", token="tok")

    assert visto["url"].endswith("/waba-1/message_templates")
    corpo = visto["corpo"]
    assert corpo["name"] == "chama_vendedor"
    assert corpo["language"] == "pt_BR"
    # UTILITY e o que segura o custo: como MARKETING cada oferta custa ~10x.
    assert corpo["category"] == "UTILITY"
    tipos = [c["type"] for c in corpo["components"]]
    assert "BODY" in tipos and "BUTTONS" in tipos
    corpo_txt = next(c for c in corpo["components"] if c["type"] == "BODY")["text"]
    assert "{{1}}" in corpo_txt
    botoes = next(c for c in corpo["components"] if c["type"] == "BUTTONS")["buttons"]
    assert botoes == [{"type": "QUICK_REPLY", "text": "Peguei"}]


def test_elo_4_template_ja_existente_e_sucesso():
    handler = lambda pedido: httpx.Response(
        400, json={"error": {"code": 100, "error_subcode": 2388023,
                             "message": "template name already exists"}}
    )

    _cliente(handler).criar_template(waba_id="waba-1", token="tok")
