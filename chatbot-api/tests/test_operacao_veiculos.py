"""E5 — cadastro de veículo via WhatsApp: autorização, validação e proxy Estoque."""
from app.inventory import HttpInventoryWriteClient, get_inventory_write_client
from app.main import app


def _payload(**overrides):
    base = {
        "telefone_solicitante": "5511999990001",
        "tipo": "moto",
        "marca": "Honda",
        "modelo": "CG 160",
        "ano_modelo": 2023,
        "preco": 16000,
        "km": 12000,
        "placa": "ABC1D23",
    }
    base.update(overrides)
    return base


def test_numero_autorizado_guarda_nome(client, loja_a):
    r = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "5511988887777", "nome": "João Vendedor"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["nome"] == "João Vendedor"
    lista = client.get(
        "/v1/operacao/numeros-autorizados", headers=loja_a["headers"]
    ).json()["numeros"]
    assert any(n["nome"] == "João Vendedor" for n in lista)


def _autorizar(client, loja, telefone="5511999990001", papel="dono"):
    r = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": telefone, "papel": papel},
        headers=loja["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


class _FakeWriteClient:
    """Captura chamadas ao Estoque sem HTTP real."""

    def __init__(self, resposta=None, raise_exc=None):
        self.chamadas = []
        self._resposta = resposta or {
            "id": "veh-1",
            "tipo": "moto",
            "marca": "Honda",
            "modelo": "CG 160",
            "ano_modelo": 2023,
            "preco": 16000.0,
            "km": 12000,
            "placa": "ABC1D23",
            "status": "disponivel",
            "publicado": False,
            "foto_url": None,
        }
        self._raise = raise_exc

    def disponivel(self) -> bool:
        return True

    def criar_veiculo(self, dados: dict, idempotency_key: str | None = None) -> dict:
        self.chamadas.append({"dados": dados, "idempotency_key": idempotency_key})
        if self._raise is not None:
            raise self._raise
        return {**self._resposta, **{k: dados.get(k, self._resposta.get(k)) for k in dados}}


# --- números autorizados ------------------------------------------------------


def test_crud_numeros_autorizados(client, loja_a):
    h = loja_a["headers"]
    r = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "+55 (11) 99999-0001", "papel": "dono"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["telefone"] == "5511999990001"
    assert r.json()["papel"] == "dono"
    assert r.json()["ativo"] is True

    lista = client.get("/v1/operacao/numeros-autorizados", headers=h).json()["numeros"]
    assert len(lista) == 1
    assert lista[0]["telefone"] == "5511999990001"

    rem = client.delete("/v1/operacao/numeros-autorizados/5511999990001", headers=h)
    assert rem.status_code == 200
    assert rem.json()["removido"] is True
    assert client.get("/v1/operacao/numeros-autorizados", headers=h).json()["numeros"] == []


def test_numeros_isolamento_entre_lojas(client, loja_a, loja_b):
    _autorizar(client, loja_a, "5511888000001")
    lista_b = client.get(
        "/v1/operacao/numeros-autorizados", headers=loja_b["headers"]
    ).json()["numeros"]
    assert lista_b == []


# --- criar veículo ------------------------------------------------------------


def test_autorizado_cria_veiculo(client, loja_a):
    _autorizar(client, loja_a)
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(),
            headers={**loja_a["headers"], "Idempotency-Key": "key-abc"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["ok"] is True
        assert "Honda CG 160" in body["mensagem"]
        assert body["veiculo"]["placa"] == "ABC1D23"
        assert body["solicitante"] == "5511999990001"
        assert len(fake.chamadas) == 1
        assert fake.chamadas[0]["idempotency_key"] == "key-abc"
        assert fake.chamadas[0]["dados"]["marca"] == "Honda"
        assert fake.chamadas[0]["dados"]["preco"] == 16000.0
        assert fake.chamadas[0]["dados"]["publicado"] is True
        assert body["veiculo"]["publicado"] is True
        assert "envie as fotos" in body["mensagem"]
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_cadastro_ativa_sessao_para_primeira_foto_sem_legenda(client, loja_a):
    from app.vehicle_photo import get_vehicle_photo_processor

    class _PhotoFake:
        def __init__(self):
            self.chamadas = []

        def processar(self, instancia, message_id, placa, mime_type):
            self.chamadas.append((instancia, message_id, placa, mime_type))
            return {
                "ok": True,
                "mensagem": "Foto adicionada ao estoque e ao catálogo.",
                "publicado": True,
            }

    _autorizar(client, loja_a)
    write_fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: write_fake
    try:
        criada = client.post(
            "/v1/operacao/veiculos",
            json=_payload(),
            headers=loja_a["headers"],
        )
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)
    assert criada.status_code == 201

    photo_fake = _PhotoFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: photo_fake
    try:
        foto = client.post(
            "/webhook/operacao/veiculos/foto",
            json={
                "instance": loja_a["instance"],
                "telefone_solicitante": "5511999990001",
                "provider_message_id": "MSG-SEM-LEGENDA-1",
                "legenda": None,
                "mime_type": "image/jpeg",
            },
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert foto.json()["ok"] is True
    assert photo_fake.chamadas[0][2] == "ABC1D23"


def test_nao_autorizado_recusa_sem_chamar_estoque(client, loja_a):
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(telefone_solicitante="5511000000999"),
            headers=loja_a["headers"],
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "não autorizado"
        assert fake.chamadas == []
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_numero_inativo_nao_autoriza(client, loja_a):
    client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "5511999990001", "papel": "vendedor", "ativo": False},
        headers=loja_a["headers"],
    )
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(),
            headers=loja_a["headers"],
        )
        assert r.status_code == 403
        assert fake.chamadas == []
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_dados_incompletos_422(client, loja_a):
    _autorizar(client, loja_a)
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(preco=0),
            headers=loja_a["headers"],
        )
        assert r.status_code == 422
        assert "valor" in r.json()["detail"].lower()
        assert fake.chamadas == []

        r2 = client.post(
            "/v1/operacao/veiculos",
            json=_payload(placa="INVALID"),
            headers=loja_a["headers"],
        )
        assert r2.status_code == 422
        assert "placa" in r2.json()["detail"].lower()
        assert fake.chamadas == []
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_idempotency_key_gerada_quando_ausente(client, loja_a):
    _autorizar(client, loja_a)
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(),
            headers=loja_a["headers"],
        )
        assert r.status_code == 201
        key = fake.chamadas[0]["idempotency_key"]
        assert key is not None
        assert "ABC1D23" in key
        assert loja_a["loja_id"] in key
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_tenancy_numero_de_outra_loja_nao_autoriza(client, loja_a, loja_b):
    _autorizar(client, loja_a, "5511777000001")
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(telefone_solicitante="5511777000001"),
            headers=loja_b["headers"],
        )
        assert r.status_code == 403
        assert fake.chamadas == []
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_foto_url_opcional_encaminhada(client, loja_a):
    _autorizar(client, loja_a)
    fake = _FakeWriteClient()
    app.dependency_overrides[get_inventory_write_client] = lambda: fake
    try:
        r = client.post(
            "/v1/operacao/veiculos",
            json=_payload(foto_url="https://cdn.example/moto.jpg"),
            headers=loja_a["headers"],
        )
        assert r.status_code == 201
        assert fake.chamadas[0]["dados"]["foto_url"] == "https://cdn.example/moto.jpg"
    finally:
        app.dependency_overrides.pop(get_inventory_write_client, None)


def test_http_write_client_encaminha_idempotency_e_token(monkeypatch):
    capturado = {}

    class _FakeResp:
        status_code = 201

        def json(self):
            return {"id": "v1", "marca": "Honda", "modelo": "CG", "placa": "ABC1D23"}

    def _fake_post(url, json=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
        capturado["headers"] = headers
        capturado["timeout"] = timeout
        return _FakeResp()

    monkeypatch.setattr("app.inventory.httpx.post", _fake_post)
    client = HttpInventoryWriteClient(
        base_url="http://estoque:8000", token="tok-secreto", timeout=3.0
    )
    out = client.criar_veiculo(
        {"tipo": "moto", "marca": "Honda", "modelo": "CG", "ano_modelo": 2023, "preco": 1, "placa": "ABC1D23"},
        idempotency_key="idem-1",
    )
    assert out["id"] == "v1"
    assert capturado["url"] == "http://estoque:8000/v1/veiculos"
    assert capturado["headers"]["Authorization"] == "Bearer tok-secreto"
    assert capturado["headers"]["Idempotency-Key"] == "idem-1"


def test_http_write_client_sem_config_503():
    client = HttpInventoryWriteClient(base_url="", token="")
    assert client.disponivel() is False
    try:
        client.criar_veiculo({"tipo": "moto"})
        assert False, "deveria levantar"
    except Exception as exc:
        from fastapi import HTTPException

        assert isinstance(exc, HTTPException)
        assert exc.status_code == 503


def test_http_write_client_busca_placa_e_envia_bytes_da_foto(monkeypatch):
    chamadas = []

    class _FakeResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("erro")

    def _fake_get(url, headers=None, timeout=None):
        chamadas.append(("get", url, headers, timeout))
        return _FakeResp(200, {"id": "veh-1", "placa": "ABC1D23"})

    def _fake_post(url, **kwargs):
        chamadas.append(("post", url, kwargs))
        return _FakeResp(
            201,
            {
                "id": "veh-1",
                "placa": "ABC1D23",
                "fotos": ["https://estoque.example/foto.jpg"],
                "publicado": True,
            },
        )

    monkeypatch.setattr("app.inventory.httpx.get", _fake_get)
    monkeypatch.setattr("app.inventory.httpx.post", _fake_post)
    inventory = HttpInventoryWriteClient(
        base_url="http://estoque:8000", token="tok-estoque", timeout=3
    )

    assert inventory.obter_por_placa("ABC1D23")["id"] == "veh-1"
    resposta = inventory.adicionar_foto(
        "veh-1",
        b"\xff\xd8\xfffoto",
        "image/jpeg",
        "wa-foto:MSG-1",
        publicar=True,
    )

    assert resposta["publicado"] is True
    metodo, url, kwargs = chamadas[1]
    assert metodo == "post"
    assert url.endswith("/v1/veiculos/veh-1/fotos/upload")
    assert kwargs["content"] == b"\xff\xd8\xfffoto"
    assert kwargs["params"] == {"publicar": "true"}
    assert kwargs["headers"]["Authorization"] == "Bearer tok-estoque"
    assert kwargs["headers"]["Idempotency-Key"] == "wa-foto:MSG-1"
