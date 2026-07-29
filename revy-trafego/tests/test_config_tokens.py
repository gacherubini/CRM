from dataclasses import replace

from app.config import settings


def test_token_chatbot_por_loja_isola_credenciais():
    config = replace(
        settings,
        chatbot_token="token-legado",
        chatbot_token_loja="",
        chatbot_tokens_json='{"loja-a":"token-a","loja-b":"token-b"}',
    )

    assert config.chatbot_token_para("loja-a") == "token-a"
    assert config.chatbot_token_para("loja-b") == "token-b"
    assert config.chatbot_token_para("loja-c") == ""


def test_token_chatbot_mapeamento_invalido_falha_fechado():
    config = replace(
        settings,
        chatbot_token="token-legado",
        chatbot_token_loja="",
        chatbot_tokens_json="nao-e-json",
    )

    assert config.chatbot_token_para("loja-a") == ""
