from urllib.parse import parse_qs, urlparse

from app.main import normalize_whatsapp


def test_normaliza_whatsapp_brasileiro_local_e_internacional():
    assert normalize_whatsapp("(11) 99999-9999") == "5511999999999"
    assert normalize_whatsapp("+55 (11) 99999-9999") == "5511999999999"
    assert normalize_whatsapp("sem-numero") is None


def test_health_e_version(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200
    version = client.get("/version").json()
    assert version["contrato_estoque"] == "public/v1"


def test_vitrine_renderiza_dados_e_preserva_filtros(client, fake_provider):
    response = client.get(
        "/l/moto-center?tipo=moto&marca=Honda&preco_min=10000&preco_max=30000&limit=1"
    )
    assert response.status_code == 200
    assert "Honda CG 160" in response.text
    assert 'value="Honda"' in response.text
    assert 'option value="moto" selected' in response.text
    assert "preco_min=10000.0" in response.text
    assert "preco_max=30000.0" in response.text
    assert fake_provider.last_filters == {
        "tipo": "moto",
        "marca": "Honda",
        "preco_min": 10000.0,
        "preco_max": 30000.0,
        "limit": 1,
        "offset": 0,
    }


def test_vitrine_estado_vazio(client, fake_provider):
    original = fake_provider.list_vehicles

    def empty(slug, **filters):
        page = original(slug, **filters)
        page.veiculos = []
        page.paginacao.quantidade = 0
        return page

    fake_provider.list_vehicles = empty
    response = client.get("/l/moto-center")
    assert response.status_code == 200
    assert "Nenhum veículo encontrado" in response.text


def test_detalhe_renderiza_galeria_e_cta(client):
    response = client.get(
        "/l/moto-center/veiculos/vehicle-1?utm_source=instagram&utm_campaign=ofertas"
    )
    assert response.status_code == 200
    assert response.text.count("https://images.example/vehicle-1") >= 2
    assert "Tenho interesse pelo WhatsApp" in response.text
    assert "utm_source=instagram" in response.text


def test_detalhe_tem_fallback_sem_imagem(client, fake_provider):
    fake_provider.vehicle.fotos = []
    fake_provider.vehicle.foto_url = None
    response = client.get("/l/moto-center/veiculos/vehicle-1")
    assert "Veículo sem foto" in response.text


def test_404_e_503_sao_paginas_controladas(client, fake_provider):
    assert client.get("/l/moto-center/veiculos/outro").status_code == 404
    fake_provider.fail = True
    response = client.get("/l/moto-center")
    assert response.status_code == 503
    assert "temporariamente indisponível" in response.text
    assert "Traceback" not in response.text


def test_interesse_grava_evento_e_redireciona_somente_para_whatsapp(
    client, interest_store
):
    response = client.get(
        "/l/moto-center/interesse/vehicle-1"
        "?origem=detalhe&utm_source=instagram&redirect=https://evil.example",
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    assert parsed.scheme == "https"
    assert parsed.netloc == "wa.me"
    assert parsed.path == "/5511999999999"
    assert "vehicle-1" in parse_qs(parsed.query)["text"][0]
    message = parse_qs(parsed.query)["text"][0]
    assert "CAT-" in message
    assert "evil.example" not in location
    assert interest_store.count() == 1
    pending = interest_store.pending_outbox()
    assert len(pending) == 1
    assert pending[0]["event_id"]
    assert "visitante_id" not in pending[0]["payload"]
    assert "telefone" not in pending[0]["payload"]
    assert "catalog_visitor=" in response.headers["set-cookie"]


def test_interesse_sem_whatsapp_valido_nao_grava_nem_redireciona(
    client, fake_provider, interest_store
):
    fake_provider.store.whatsapp = "sem-numero"
    response = client.get(
        "/l/moto-center/interesse/vehicle-1", follow_redirects=False
    )
    assert response.status_code == 422
    assert "WhatsApp indisponível" in response.text
    assert interest_store.count() == 0
