from app import config


def test_config_browser_defaults():
    assert isinstance(config.PRAZOS_PADRAO, list) and config.PRAZOS_PADRAO
    assert config.BROWSER_TIMEOUT_MS >= 1000
    assert config.SANTANDER_LOGIN_URL.startswith("https://")
    assert "santander" in config.SANTANDER_LOGIN_URL.lower()
    # Decisão B+D: default de produto = 2 (sem env override no processo de teste).
    assert config.MAX_BROWSER_WORKERS >= 1
    assert config.BROWSER_CONCURRENCY == config.MAX_BROWSER_WORKERS
    assert config.WARM_SESSION is True or config.WARM_SESSION is False
