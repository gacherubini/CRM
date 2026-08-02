"""Painel de status das integrações na Loja (Ajustes) — página + endpoint proxy.

O badge consome o agregador do Revy Control via service token, mas server-side:
o navegador do dono/gerente fala só com o Portal. Cobrimos o gate (shell +
dono/gerente), o container/JS na página e o contrato do endpoint local
(200 do agregador; 502 quando o Control está indisponível/não configurado).
"""
from conftest import login

from app.clients.revy_trafego import RevyTrafegoClient

TELA = "/app/loja/integracoes"
HEALTH = "/app/loja/integracoes/health"

_FAKE = {
    "meta": {"status": "connected", "itens": []},
    "google": {"status": "missing", "itens": []},
    "whatsapp": {"status": "error", "itens": []},
    "checked_at": "2026-08-02T12:00:00+00:00",
    "cache_ttl_seg": 600,
}


def _ligar(monkeypatch, shell="1"):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", shell)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


def test_shell_off_esconde_pagina(client, monkeypatch):
    _ligar(monkeypatch, shell="0")
    login(client)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303


def test_vendedor_nao_acessa_pagina(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303


def test_pagina_renderiza_container_e_script(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get(TELA)
    assert r.status_code == 200
    assert 'id="integracoes-health"' in r.text
    assert f'data-integ-endpoint="{HEALTH}"' in r.text
    assert "Testar agora" in r.text
    assert "integracoes_health.js" in r.text


def test_health_endpoint_200_do_agregador(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setattr(
        RevyTrafegoClient, "fetch_integracoes_health", lambda self, **kw: _FAKE
    )
    login(client)
    r = client.get(HEALTH)
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["status"] == "connected"
    assert set(body.keys()) >= {"meta", "google", "whatsapp"}


def test_health_endpoint_502_quando_control_indisponivel(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setattr(
        RevyTrafegoClient, "fetch_integracoes_health", lambda self, **kw: None
    )
    login(client)
    r = client.get(HEALTH)
    assert r.status_code == 502


def test_health_endpoint_vendedor_403(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    r = client.get(HEALTH)
    assert r.status_code == 403


def test_health_endpoint_sem_login_401(client, monkeypatch):
    _ligar(monkeypatch)
    r = client.get(HEALTH)
    assert r.status_code == 401
