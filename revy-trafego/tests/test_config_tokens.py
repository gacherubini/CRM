from dataclasses import replace

from app.config import Settings, settings


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


def test_flags_futuras_do_control_iniciam_desligadas(monkeypatch):
    variables = (
        "GOOGLE_ADS_SYNC_ENABLED",
        "GOOGLE_CONVERSIONS_ENABLED",
        "MULTI_WHATSAPP_ENABLED",
        "REVY_CONTROL_DASHBOARD_ENABLED",
    )
    for variable in variables:
        monkeypatch.delenv(variable, raising=False)

    config = Settings()

    assert config.google_ads_sync_enabled is False
    assert config.google_conversions_enabled is False
    assert config.multi_whatsapp_enabled is False
    assert config.revy_control_dashboard_enabled is False


def test_flags_futuras_do_control_aceitam_valores_verdadeiros(monkeypatch):
    for variable in (
        "GOOGLE_ADS_SYNC_ENABLED",
        "GOOGLE_CONVERSIONS_ENABLED",
        "MULTI_WHATSAPP_ENABLED",
        "REVY_CONTROL_DASHBOARD_ENABLED",
    ):
        monkeypatch.setenv(variable, "true")

    config = Settings()

    assert config.google_ads_sync_enabled is True
    assert config.google_conversions_enabled is True
    assert config.multi_whatsapp_enabled is True
    assert config.revy_control_dashboard_enabled is True
