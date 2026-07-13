from app.inventory import get_inventory_provider
from app.main import app
from app.simulation import (
    HttpSimulationProvider,
    MockSimulationProvider,
    NoSimulationProvider,
    get_simulation_provider,
)


def _payload(**extra):
    base = {
        "cpf": "529.982.247-25",
        "nascimento": "1990-05-20",
        "valor": 20000,
        "entrada": 5000,
        "prazo_meses": 48,
    }
    base.update(extra)
    return base


class _FakeInventory:
    def __init__(self, veiculo=None):
        self._veiculo = veiculo

    def buscar(self, slug, termo=None):
        return []

    def obter_por_placa(self, placa):
        return self._veiculo


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


def test_simular_por_placa_usa_preco_do_estoque(client, loja_a):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeInventory(
        {
            "id": "v1",
            "placa": "ABC1D23",
            "preco": 18000.0,
            "tipo": "moto",
            "marca": "Honda",
            "modelo": "CG",
        }
    )
    try:
        r = client.post(
            "/v1/simular",
            json={
                "cpf": "529.982.247-25",
                "nascimento": "1990-05-20",
                "placa": "ABC1D23",
                "telefone": "11999990000",
                "entrada": 3000,
                "prazo_meses": 36,
            },
            headers=loja_a["headers"],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "concluida"
        assert all(v["valor_financiado"] == 15000 for v in body["resultados"])
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_simular_placa_nao_encontrada_404(client, loja_a):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    app.dependency_overrides[get_inventory_provider] = lambda: _FakeInventory(None)
    try:
        r = client.post(
            "/v1/simular",
            json={
                "cpf": "529.982.247-25",
                "nascimento": "1990-05-20",
                "placa": "ZZZ9Z99",
                "entrada": 0,
            },
            headers=loja_a["headers"],
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)
        app.dependency_overrides.pop(get_inventory_provider, None)


def test_simular_sem_placa_nem_valor_422(client, loja_a):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post(
            "/v1/simular",
            json={
                "cpf": "529.982.247-25",
                "nascimento": "1990-05-20",
                "entrada": 0,
                "prazo_meses": 48,
            },
            headers=loja_a["headers"],
        )
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_simular_prazos_padrao_multi(client, loja_a):
    """Sem prazo_meses/prazos_meses → 24/36/48/60 (2 bancos × 4 prazos)."""
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post(
            "/v1/simular",
            json={
                "cpf": "529.982.247-25",
                "nascimento": "1990-05-20",
                "valor": 20000,
                "entrada": 5000,
            },
            headers=loja_a["headers"],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "concluida"
        assert body["prazos_meses"] == [24, 36, 48, 60]
        assert len(body["resultados"]) == 8  # 2 bancos × 4 prazos
        prazos_nos_resultados = {r["prazo_meses"] for r in body["resultados"]}
        assert prazos_nos_resultados == {24, 36, 48, 60}
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_simular_prazos_meses_lista_explicita(client, loja_a):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post(
            "/v1/simular",
            json={
                "cpf": "529.982.247-25",
                "nascimento": "1990-05-20",
                "valor": 20000,
                "entrada": 0,
                "prazos_meses": [12, 24],
            },
            headers=loja_a["headers"],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["prazos_meses"] == [12, 24]
        assert len(body["resultados"]) == 4
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_simular_sem_renda_no_payload_motor(client, loja_a, monkeypatch):
    capturados = []

    class _Spy(MockSimulationProvider):
        def simular(self, payload, idempotency_key):
            capturados.append(payload)
            return super().simular(payload, idempotency_key)

    app.dependency_overrides[get_simulation_provider] = lambda: _Spy()
    try:
        r = client.post("/v1/simular", json=_payload(), headers=loja_a["headers"])
        assert r.status_code == 200
        assert "renda" not in capturados[0]["pessoa"]
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
    out = prov.simular(
        {"veiculo": {"valor": 20000}, "condicoes": {"entrada": 5000, "prazo_meses": 48}},
        "key",
    )
    assert out["status"] == "falhou"
    assert out["resultados"] == []
    assert "demorando" in out["mensagem"]
