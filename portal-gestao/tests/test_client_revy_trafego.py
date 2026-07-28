import httpx

from app.clients.revy_trafego import RevyTrafegoClient
from app.resultados_dono import resumo_from_api


def test_fetch_resultados_nao_configurado():
    client = RevyTrafegoClient(base_url="", token="")
    assert client.fetch_resultados(loja_slug="loja-x") is None


def test_fetch_resultados_ok(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Service-Token") == "tok"
        assert "/v1/lojas/loja-x/resultados" in str(request.url)
        return httpx.Response(
            200,
            json={
                "loja_slug": "loja-x",
                "periodo": {"chave": "7d", "inicio": "2026-07-21", "fim": "2026-07-28"},
                "totais": {
                    "gasto": "100.00",
                    "leads": 5,
                    "vendas": 1,
                    "faturamento": "5000.00",
                    "cpl": "20.00",
                    "cpa": "100.00",
                    "roas": "50.00",
                },
                "canais": [],
                "melhor_campanha": None,
                "tem_campanhas": True,
                "vendas_sem_campanha": 0,
                "leads_sem_campanha": 0,
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("app.clients.revy_trafego.httpx.Client", fabrica)

    client = RevyTrafegoClient(base_url="http://trafego.test", token="tok")
    data = client.fetch_resultados(loja_slug="loja-x", periodo="7d")
    assert data is not None
    assert data["totais"]["leads"] == 5
    view = resumo_from_api(data)
    assert view["totais"]["leads"] == 5
    assert view["fonte"] == "api"


def test_notificar_venda_confirmada(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "outbox_id": "o1"})

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("app.clients.revy_trafego.httpx.Client", fabrica)

    client = RevyTrafegoClient(base_url="http://trafego.test", token="tok")
    r = client.notificar_venda_confirmada(
        loja_slug="loja-x",
        payload={"venda_id": "v1", "valor": "10.00"},
    )
    assert r == {"ok": True, "outbox_id": "o1"}
    assert len(calls) == 1
