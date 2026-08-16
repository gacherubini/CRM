"""Os workers do Modo 2 têm que subir com a app.

Existe porque `RodizioWorker` e `FollowupWorker` foram escritos, testados
por `run_once` direto, e nunca ligados ao lifespan: o prazo de 10 min nunca
disparava e o cutucão de silêncio nunca acontecia. Suíte verde, produto
morto.
"""
from app import modo2_workers


def test_start_sobe_os_dois(monkeypatch):
    monkeypatch.setattr("app.modo2_workers.config.MODO2_ENABLED", True)
    modo2_workers.stop_workers()

    workers = modo2_workers.start_workers(lambda: None, enabled=True)

    assert {"rodizio", "followup"} <= set(workers)
    modo2_workers.stop_workers()


def test_flag_off_nao_sobe_nada(monkeypatch):
    """Flag OFF é invariante do projeto: nem thread deve nascer."""
    monkeypatch.setattr("app.modo2_workers.config.MODO2_ENABLED", False)
    modo2_workers.stop_workers()

    assert modo2_workers.start_workers(lambda: None, enabled=True) == {}


def test_desligado_por_env_nao_sobe(monkeypatch):
    monkeypatch.setattr("app.modo2_workers.config.MODO2_ENABLED", True)
    modo2_workers.stop_workers()

    assert modo2_workers.start_workers(lambda: None, enabled=False) == {}


def test_lifespan_da_app_chama_o_start(monkeypatch):
    """O teste que faltava: a app sobe os workers, não só a função existe."""
    chamadas = []
    monkeypatch.setattr(
        "app.modo2_workers.start_workers",
        lambda factory, *, enabled: chamadas.append(enabled) or {},
    )
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app):
        pass

    assert chamadas, "o lifespan não chamou start_workers"
