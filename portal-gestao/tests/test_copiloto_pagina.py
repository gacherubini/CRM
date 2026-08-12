import pytest
from conftest import csrf_da_resposta, login

from app.db import SessionLocal
from app.loja.copiloto.cache import cache_overview
from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.models import CopilotoSinal


@pytest.fixture(autouse=True)
def _cache_overview_isolado():
    """cache_overview é TTL global por processo: isola os testes desta rota
    de sobra de outro teste que rodou antes com o mesmo loja_slug/papel."""
    cache_overview.invalidar()
    yield
    cache_overview.invalidar()


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _semear_sinal(loja="loja-teste"):
    db = SessionLocal()
    try:
        sincronizar_sinais(
            db,
            loja,
            [
                SinalCandidato(
                    regra="estoque_parado",
                    severidade="atencao",
                    titulo="Honda CB 500F parada há 70 dias",
                    detalhe="R$ 25.000,00 de capital preso.",
                    entidade_ref="v1",
                    dados={"veiculo_id": "v1"},
                )
            ],
        )
        return db.query(CopilotoSinal).one().id
    finally:
        db.close()


def test_flag_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404


def test_shell_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404


def test_vendedor_recebe_403(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    assert client.get("/app/loja/copiloto").status_code == 403


def test_dono_abre_a_pagina_com_resumo(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/loja/copiloto")
    assert r.status_code == 200
    assert "Copiloto de Vendas" in r.text
    assert "Resumo de hoje" in r.text


def test_pagina_lista_o_sinal_aberto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _semear_sinal()
    r = client.get("/app/loja/copiloto")
    assert "Honda CB 500F parada há 70 dias" in r.text


def test_nav_mostra_a_secao_copiloto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app")
    assert 'href="/app/loja/copiloto"' in r.text
    assert "Agente do WhatsApp" in r.text


def test_dispensar_sinal_exige_csrf(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": "invalido"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 403)
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


def test_dispensar_sinal_com_csrf_valido(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
    finally:
        db.close()


def test_sinal_de_outra_loja_nao_e_dispensavel(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal(loja="outra-loja")
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()
