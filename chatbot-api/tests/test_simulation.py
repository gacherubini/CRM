from app.main import app
from app.simulation import (
    HttpSimulationProvider,
    MockSimulationProvider,
    NoSimulationProvider,
    get_simulation_provider,
)


def _payload():
    return {
        "cpf": "529.982.247-25",
        "nascimento": "1990-05-20",
        "valor": 20000,
        "entrada": 5000,
        "prazo_meses": 48,
    }


def test_simular_desabilitado_por_padrao_409(client, loja_a):
    # provider default = none
    r = client.post("/v1/simular", json=_payload(), headers=loja_a["headers"])
    assert r.status_code == 409


def test_simular_com_mock_retorna_resultados(client, loja_a):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post("/v1/simular", json=_payload(), headers=loja_a["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "concluida"
        assert len(body["resultados"]) == 2
        assert all(v["valor_parcela"] > 0 for v in body["resultados"])
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_no_provider_indisponivel():
    assert NoSimulationProvider().disponivel() is False


def test_mock_provider_desconta_entrada():
    out = MockSimulationProvider().simular(
        {"veiculo": {"valor": 20000}, "condicoes": {"entrada": 5000, "prazo_meses": 48}}, "k"
    )
    assert all(v["valor_financiado"] == 15000 for v in out["resultados"])


def test_http_provider_delega_ao_motor(monkeypatch):
    from app import simulation

    class _Resp:
        def __init__(self, d):
            self._d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    respostas = iter([
        {"id": "sim-1", "status": "processando", "resultados": []},
        {"id": "sim-1", "status": "concluida", "resultados": [{"provedor": "BV"}]},
    ])
    headers_vistos = []

    def _post(*args, **kwargs):
        headers_vistos.append(kwargs["headers"])
        return _Resp({"id": "sim-1", "status": "recebida"})

    def _get(*args, **kwargs):
        headers_vistos.append(kwargs["headers"])
        return _Resp(next(respostas))

    monkeypatch.setattr(simulation.httpx, "post", _post)
    monkeypatch.setattr(simulation.httpx, "get", _get)
    prov = HttpSimulationProvider(
        base_url="http://motor", token="token-motor", poll_interval=0
    )
    out = prov.simular({"veiculo": {"valor": 1}, "condicoes": {"prazo_meses": 12}}, "key")
    assert out["resultados"][0]["provedor"] == "BV"
    assert len(headers_vistos) == 3
    assert headers_vistos[0]["Idempotency-Key"] == "key"
    assert all(h["Authorization"] == "Bearer token-motor" for h in headers_vistos)


def test_http_provider_falha_gera_fallback(monkeypatch):
    from app import simulation

    def _boom(*a, **k):
        raise RuntimeError("motor fora do ar")

    monkeypatch.setattr(simulation.httpx, "post", _boom)
    prov = HttpSimulationProvider(base_url="http://motor", token="token-motor")
    out = prov.simular({"veiculo": {"valor": 1}, "condicoes": {"prazo_meses": 12}}, "key")
    assert out["status"] == "falhou"
    assert out["resultados"] == []


def test_http_provider_exige_url_e_token():
    assert HttpSimulationProvider(base_url="http://motor", token="").disponivel() is False
    assert HttpSimulationProvider(base_url="", token="token").disponivel() is False
    assert HttpSimulationProvider(base_url="http://motor", token="token").disponivel() is True


def test_http_provider_timeout_de_polling_gera_fallback(monkeypatch):
    from app import simulation

    class _Resp:
        def __init__(self, dados):
            self._dados = dados

        def raise_for_status(self):
            pass

        def json(self):
            return self._dados

    monkeypatch.setattr(
        simulation.httpx,
        "post",
        lambda *a, **k: _Resp({"id": "sim-lenta", "status": "recebida"}),
    )
    monkeypatch.setattr(
        simulation.httpx,
        "get",
        lambda *a, **k: _Resp({"id": "sim-lenta", "status": "processando", "resultados": []}),
    )
    prov = HttpSimulationProvider(
        base_url="http://motor", token="token", poll_timeout=0, poll_interval=0
    )
    out = prov.simular(_payload(), "key")
    assert out["status"] == "falhou"
    assert out["resultados"] == []
    assert "demorando" in out["mensagem"]
