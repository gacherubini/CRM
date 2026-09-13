from unittest.mock import MagicMock

from app import config
from app.motor.playwright_base import (
    aplicar_geolocalizacao,
    geolocalizacao_configurada,
)


def test_config_browser_defaults():
    assert isinstance(config.PRAZOS_PADRAO, list) and config.PRAZOS_PADRAO
    assert config.BROWSER_TIMEOUT_MS >= 1000
    assert config.SANTANDER_LOGIN_URL.startswith("https://")
    assert "santander" in config.SANTANDER_LOGIN_URL.lower()
    # Decisão B+D: default de produto = 2 (sem env override no processo de teste).
    assert config.MAX_BROWSER_WORKERS >= 1
    assert config.BROWSER_CONCURRENCY == config.MAX_BROWSER_WORKERS
    assert config.WARM_SESSION is True or config.WARM_SESSION is False


# --- geolocalizacao (Allow automatico; default OFF) ----------------------------


def test_geo_default_off(monkeypatch):
    """Sem MOTOR_GEO_*: contexto nem toca em permissoes (comportamento de antes)."""
    monkeypatch.setattr(config, "GEO_LATITUDE", "")
    monkeypatch.setattr(config, "GEO_LONGITUDE", "")
    assert geolocalizacao_configurada() is None
    assert aplicar_geolocalizacao(MagicMock()) is False


def test_geo_invalida_nao_aplica(monkeypatch):
    monkeypatch.setattr(config, "GEO_LATITUDE", "texto")
    monkeypatch.setattr(config, "GEO_LONGITUDE", "-51.16")
    assert geolocalizacao_configurada() is None
    monkeypatch.setattr(config, "GEO_LATITUDE", "-95.0")  # fora da faixa
    monkeypatch.setattr(config, "GEO_LONGITUDE", "-51.16")
    assert geolocalizacao_configurada() is None


def test_geo_valida_concede_permissao_e_posicao(monkeypatch):
    """Com as duas coords: grant geolocation + set_geolocation (equivale ao Allow)."""
    monkeypatch.setattr(config, "GEO_LATITUDE", "-30.1188")
    monkeypatch.setattr(config, "GEO_LONGITUDE", "-51.168")
    assert geolocalizacao_configurada() == (-30.1188, -51.168)
    ctx = MagicMock()
    assert aplicar_geolocalizacao(ctx) is True
    ctx.grant_permissions.assert_called_once_with(["geolocation"])
    pos = ctx.set_geolocation.call_args.args[0]
    assert pos["latitude"] == -30.1188
    assert pos["longitude"] == -51.168


def test_geo_erro_no_contexto_nao_levanta(monkeypatch):
    """Falha no grant nao pode quebrar a criacao do contexto."""
    monkeypatch.setattr(config, "GEO_LATITUDE", "-30.1188")
    monkeypatch.setattr(config, "GEO_LONGITUDE", "-51.168")
    ctx = MagicMock()
    ctx.grant_permissions.side_effect = RuntimeError("contexto fechado")
    assert aplicar_geolocalizacao(ctx) is False
