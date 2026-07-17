"""Warm session paths + classificação browser (plano batch 2)."""
from pathlib import Path

from app.sessao_browser import (
    browser_concurrency,
    driver_usa_browser,
    path_storage_state,
    path_storage_state_gravacao,
    sanitizar_segmento,
    sessao_parece_quente,
)


def test_sanitizar_segmento_bloqueia_traversal():
    assert ".." not in sanitizar_segmento("../etc/passwd")
    assert "/" not in sanitizar_segmento("a/b")
    assert sanitizar_segmento("") == "x"


def test_path_storage_canonic_por_cliente(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.STORAGE_STATE_DIR", str(tmp_path))
    p = path_storage_state_gravacao("cli-uuid-1", "santander")
    assert p == tmp_path / "cli-uuid-1" / "santander.json"


def test_path_storage_le_legado_se_canonic_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.STORAGE_STATE_DIR", str(tmp_path))
    legado = tmp_path / "fontecred.json"
    legado.write_text('{"cookies":[]}', encoding="utf-8")
    lido = path_storage_state("cli-1", "fontecred")
    assert lido == legado
    # gravação continua canônica
    assert path_storage_state_gravacao("cli-1", "fontecred") == tmp_path / "cli-1" / "fontecred.json"


def test_sessao_parece_quente(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.STORAGE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.WARM_SESSION", True)
    assert sessao_parece_quente("c1", "santander") is False
    dest = path_storage_state_gravacao("c1", "santander")
    dest.parent.mkdir(parents=True)
    dest.write_text('{"cookies":[{"name":"x"}]}', encoding="utf-8")
    assert sessao_parece_quente("c1", "santander") is True
    monkeypatch.setattr("app.config.WARM_SESSION", False)
    assert sessao_parece_quente("c1", "santander") is False


def test_driver_usa_browser_flag():
    class A:
        usa_browser = True

    class B:
        usa_browser = False

    def f():
        pass

    f.usa_browser = True
    assert driver_usa_browser(A()) is True
    assert driver_usa_browser(B()) is False
    assert driver_usa_browser(f) is True
    assert driver_usa_browser(lambda s: None) is False


def test_browser_concurrency_minimo_1(monkeypatch):
    monkeypatch.setattr("app.config.MAX_BROWSER_WORKERS", 2)
    monkeypatch.setattr("app.config.BROWSER_CONCURRENCY", 2)
    assert browser_concurrency() == 2
    monkeypatch.setattr("app.config.MAX_BROWSER_WORKERS", 0)
    monkeypatch.setattr("app.config.BROWSER_CONCURRENCY", 0)
    assert browser_concurrency() == 1
