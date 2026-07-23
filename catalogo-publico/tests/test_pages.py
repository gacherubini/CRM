from dataclasses import fields
from urllib.parse import parse_qs, urlparse

from app.config import settings
from app.main import normalize_whatsapp


def _settings_com_pixel(base, pixel_id: str):
    valores = {f.name: getattr(base, f.name) for f in fields(base)}
    valores["meta_pixel_id"] = pixel_id
    valores["meta_pixel_enabled_raw"] = "1"
    return type(base)(**valores)


def test_normaliza_whatsapp_brasileiro_local_e_internacional():
    assert normalize_whatsapp("(11) 99999-9999") == "5511999999999"
    assert normalize_whatsapp("+55 (11) 99999-9999") == "5511999999999"
    assert normalize_whatsapp("sem-numero") is None


def test_health_e_version(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200
    version = client.get("/version").json()
    assert version["contrato_estoque"] == "public/v1"


def test_raiz_redireciona_para_loja_padrao(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/l/moto-center"


def test_css_e_links_usam_prefixo_quando_configurado(client, monkeypatch):
    from app import main as main_mod
    from app.config import Settings

    base = settings
    valores = {f.name: getattr(base, f.name) for f in fields(base)}
    valores["url_prefix_raw"] = "/loja"
    valores["public_base_url"] = "https://app2037.fly.dev/loja"
    patched = Settings(**valores)
    monkeypatch.setattr(main_mod, "settings", patched)

    def _pp(path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        prefix = patched.url_prefix
        return f"{prefix}{path}" if prefix else path

    monkeypatch.setattr(main_mod, "public_path", _pp)
    main_mod.templates.env.globals["url_prefix"] = patched.url_prefix
    main_mod.templates.env.globals["public_path"] = _pp

    root = client.get("/", follow_redirects=False)
    assert root.headers["location"] == "/loja/l/moto-center"

    page = client.get("/l/moto-center")
    assert page.status_code == 200
    assert 'href="/loja/static/css/catalog.css"' in page.text
    assert 'href="/loja/l/moto-center/veiculos/vehicle-1"' in page.text
    assert "fonts.googleapis.com" in page.headers.get("content-security-policy", "")


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


def test_sem_pixel_por_padrao(client):
    response = client.get("/l/moto-center")
    assert response.status_code == 200
    assert "fbevents.js" not in response.text
    assert "fbq(" not in response.text


def test_pixel_presente_quando_meta_pixel_id_configurado(client, monkeypatch):
    from app.pixel import PixelResolver

    patched = _settings_com_pixel(settings, "112233445566778")
    monkeypatch.setattr("app.main.settings", patched)
    client.app.state.pixel_resolver = PixelResolver(
        "",
        fallback_pixel_id="112233445566778",
    )
    response = client.get("/l/moto-center")
    assert response.status_code == 200
    assert "fbevents.js" in response.text
    assert "112233445566778" in response.text
    assert "fbq('track', 'PageView')" in response.text
    assert "access_token" not in response.text.lower()
    assert "EAAB" not in response.text
    # CSP liberado para o Pixel quando ativo
    csp = response.headers.get("content-security-policy", "")
    assert "connect.facebook.net" in csp


def test_pixel_vem_do_portal_por_loja(client, monkeypatch):
    """Dono salva no Portal; catálogo puxa sem META_PIXEL_ID de env."""
    import httpx

    from app.config import Settings
    from app.pixel import PixelResolver

    base = settings
    valores = {f.name: getattr(base, f.name) for f in fields(base)}
    valores["portal_public_url"] = "http://portal.test"
    valores["meta_pixel_id"] = ""
    valores["meta_pixel_enabled_raw"] = ""
    patched = Settings(**valores)
    monkeypatch.setattr("app.main.settings", patched)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/public/v1/lojas/moto-center/pixel" in str(request.url)
        return httpx.Response(
            200,
            json={
                "loja_slug": "moto-center",
                "pixel_id": "555666777888999",
                "enabled": True,
            },
        )

    transport = httpx.MockTransport(handler)
    client.app.state.pixel_resolver = PixelResolver(
        "http://portal.test",
        transport=transport,
        fallback_pixel_id="",
        cache_ttl=60,
    )
    response = client.get("/l/moto-center")
    assert response.status_code == 200
    assert "555666777888999" in response.text
    assert "fbevents.js" in response.text
    assert "access_token" not in response.text.lower()


def test_pixel_fallback_env_se_portal_cai(client, monkeypatch):
    import httpx

    from app.config import Settings
    from app.pixel import PixelResolver

    base = settings
    valores = {f.name: getattr(base, f.name) for f in fields(base)}
    valores["portal_public_url"] = "http://portal.test"
    valores["meta_pixel_id"] = "111222333444555"
    patched = Settings(**valores)
    monkeypatch.setattr("app.main.settings", patched)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    client.app.state.pixel_resolver = PixelResolver(
        "http://portal.test",
        transport=httpx.MockTransport(handler),
        fallback_pixel_id="111222333444555",
    )
    response = client.get("/l/moto-center")
    assert response.status_code == 200
    assert "111222333444555" in response.text


def test_detalhe_propaga_fbclid_no_cta(client):
    r = client.get(
        "/l/moto-center/veiculos/vehicle-1"
        "?utm_source=meta&utm_campaign=ofertas&fbclid=IwAR0abc"
    )
    assert r.status_code == 200
    assert "fbclid=IwAR0abc" in r.text
    assert "utm_campaign=ofertas" in r.text


def test_detalhe_lead_event_id_no_cta_quando_pixel(client, monkeypatch):
    from app.pixel import PixelResolver

    monkeypatch.setattr(
        "app.main.settings",
        _settings_com_pixel(settings, "998877665544"),
    )
    client.app.state.pixel_resolver = PixelResolver(
        "",
        fallback_pixel_id="998877665544",
    )
    response = client.get(
        "/l/moto-center/veiculos/vehicle-1?utm_source=meta&utm_campaign=ofertas"
    )
    assert response.status_code == 200
    assert "data-lead-event-id=" in response.text
    assert "fbq('track', 'Lead'" in response.text
    assert "ViewContent" in response.text
    assert "event_id=" in response.text
    assert "utm_source=meta" in response.text


def test_interesse_reusa_event_id_do_query(client, interest_store):
    event_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    response = client.get(
        f"/l/moto-center/interesse/vehicle-1?event_id={event_id}&utm_source=meta",
        follow_redirects=False,
    )
    assert response.status_code == 302
    pending = interest_store.pending_outbox()
    assert len(pending) == 1
    assert pending[0]["event_id"] == event_id
    row = interest_store.get_interest(event_id)
    assert row is not None
    assert row["event_id"] == event_id
