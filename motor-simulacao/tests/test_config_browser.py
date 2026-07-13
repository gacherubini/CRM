from app import config


def test_config_browser_defaults():
    assert isinstance(config.PRAZOS_PADRAO, list) and config.PRAZOS_PADRAO
    assert config.BROWSER_TIMEOUT_MS >= 1000
    assert config.SANTANDER_LOGIN_URL.startswith("https://")
    assert "santander" in config.SANTANDER_LOGIN_URL.lower()
