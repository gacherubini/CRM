import base64
import json
from datetime import datetime, timedelta, timezone

import httpx

from app.main import app
from app.vehicle_photo import (
    EvolutionImageDownloader,
    VehiclePhotoProcessor,
    get_vehicle_photo_processor,
)


def _autorizar(client, loja, telefone="5511999990001"):
    resposta = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": telefone, "papel": "vendedor"},
        headers=loja["headers"],
    )
    assert resposta.status_code == 201


def _payload(loja, **extra):
    body = {
        "instance": loja["instance"],
        "telefone_solicitante": "5511999990001",
        "provider_message_id": "MSG-FOTO-1",
        "legenda": "Foto frontal ABC1D23",
        "mime_type": "image/jpeg",
    }
    body.update(extra)
    return body


class ProcessorFake:
    def __init__(self):
        self.chamadas = []

    def processar(self, instancia, message_id, placa, mime_type):
        self.chamadas.append((instancia, message_id, placa, mime_type))
        return {
            "ok": True,
            "mensagem": f"Foto adicionada ao veículo {placa}. Ele já está atualizado no estoque e no catálogo.",
            "veiculo_id": "veh-1",
            "placa": placa,
            "quantidade_fotos": 1,
            "publicado": True,
        }


def test_webhook_foto_autorizada_extrai_placa_e_processa(client, loja_a):
    _autorizar(client, loja_a)
    fake = ProcessorFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: fake
    try:
        resposta = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(loja_a, legenda="Corolla placa abc-1d23 lateral"),
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert resposta.status_code == 200
    assert resposta.json()["ok"] is True
    assert resposta.json()["publicado"] is True
    assert fake.chamadas == [
        (loja_a["instance"], "MSG-FOTO-1", "ABC1D23", "image/jpeg")
    ]


def test_webhook_sessao_permite_fotos_seguintes_sem_repetir_placa(
    client, loja_a
):
    _autorizar(client, loja_a)
    fake = ProcessorFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: fake
    try:
        primeira = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(loja_a, provider_message_id="MSG-LOTE-1"),
        )
        segunda = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(
                loja_a,
                provider_message_id="MSG-LOTE-2",
                legenda=None,
            ),
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert primeira.json()["ok"] is True
    assert "sem repetir a placa" in primeira.json()["mensagem"]
    assert segunda.json()["ok"] is True
    assert fake.chamadas == [
        (loja_a["instance"], "MSG-LOTE-1", "ABC1D23", "image/jpeg"),
        (loja_a["instance"], "MSG-LOTE-2", "ABC1D23", "image/jpeg"),
    ]


def test_webhook_nao_usa_sessao_expirada(client, loja_a, db):
    from app.models_db import NumeroAutorizado

    _autorizar(client, loja_a)
    fake = ProcessorFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: fake
    try:
        client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(loja_a, provider_message_id="MSG-EXPIRA-1"),
        )
        numero = (
            db.query(NumeroAutorizado)
            .filter(NumeroAutorizado.loja_id == loja_a["loja_id"])
            .one()
        )
        numero.foto_sessao_expira_em = datetime.now(timezone.utc) - timedelta(
            seconds=1
        )
        db.commit()

        expirada = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(
                loja_a,
                provider_message_id="MSG-EXPIRA-2",
                legenda=None,
            ),
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert expirada.json()["ok"] is False
    assert "primeira foto" in expirada.json()["mensagem"]
    assert len(fake.chamadas) == 1


def test_sessao_de_fotos_e_isolada_por_numero_autorizado(client, loja_a):
    telefone_a = "5511999990001"
    telefone_b = "5511999990002"
    _autorizar(client, loja_a, telefone_a)
    _autorizar(client, loja_a, telefone_b)
    fake = ProcessorFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: fake
    try:
        client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(
                loja_a,
                telefone_solicitante=telefone_a,
                provider_message_id="MSG-SELLER-A",
            ),
        )
        vendedor_b = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(
                loja_a,
                telefone_solicitante=telefone_b,
                provider_message_id="MSG-SELLER-B",
                legenda=None,
            ),
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert vendedor_b.json()["ok"] is False
    assert len(fake.chamadas) == 1


def test_webhook_foto_recusa_numero_ou_legenda_antes_do_download(client, loja_a):
    fake = ProcessorFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: fake
    try:
        nao_autorizado = client.post(
            "/webhook/operacao/veiculos/foto", json=_payload(loja_a)
        )
        _autorizar(client, loja_a)
        sem_placa = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(loja_a, provider_message_id="MSG-FOTO-2", legenda="foto lateral"),
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert nao_autorizado.status_code == 200
    assert "Somente números autorizados" in nao_autorizado.json()["mensagem"]
    assert sem_placa.status_code == 200
    assert "placa" in sem_placa.json()["mensagem"].lower()
    assert fake.chamadas == []


def test_webhook_foto_mantem_autorizacao_isolada_por_loja(
    client, loja_a, loja_b
):
    _autorizar(client, loja_a)
    fake = ProcessorFake()
    app.dependency_overrides[get_vehicle_photo_processor] = lambda: fake
    try:
        resposta = client.post(
            "/webhook/operacao/veiculos/foto",
            json=_payload(loja_b),
        )
    finally:
        app.dependency_overrides.pop(get_vehicle_photo_processor, None)

    assert resposta.status_code == 200
    assert resposta.json()["ok"] is False
    assert fake.chamadas == []


class DownloaderFake:
    def __init__(self, conteudo=b"\xff\xd8\xfffoto", mime="image/jpeg"):
        self.conteudo = conteudo
        self.mime = mime
        self.chamadas = []

    def baixar(self, instancia, message_id, mime_declarado=None):
        self.chamadas.append((instancia, message_id, mime_declarado))
        return self.conteudo, self.mime


class InventoryFake:
    def __init__(self, veiculo=None):
        self.veiculo = veiculo
        self.uploads = []

    def obter_por_placa(self, placa):
        return self.veiculo

    def adicionar_foto(
        self, veiculo_id, conteudo, content_type, idempotency_key, publicar=True
    ):
        self.uploads.append(
            (veiculo_id, conteudo, content_type, idempotency_key, publicar)
        )
        return {
            "id": veiculo_id,
            "placa": "ABC1D23",
            "fotos": ["https://estoque.example/public/v1/media/foto.jpg"],
            "publicado": True,
        }


def test_processor_baixa_upload_e_publica_com_idempotencia():
    downloader = DownloaderFake()
    inventory = InventoryFake({"id": "veh-1", "placa": "ABC1D23"})
    resultado = VehiclePhotoProcessor(downloader, inventory).processar(
        "instancia-a", "MSG-FOTO-1", "ABC1D23", "image/jpeg"
    )

    assert resultado["ok"] is True
    assert resultado["publicado"] is True
    assert downloader.chamadas == [("instancia-a", "MSG-FOTO-1", "image/jpeg")]
    assert inventory.uploads == [
        (
            "veh-1",
            b"\xff\xd8\xfffoto",
            "image/jpeg",
            "wa-foto:MSG-FOTO-1",
            True,
        )
    ]


def test_processor_nao_baixa_se_placa_nao_existe():
    downloader = DownloaderFake()
    inventory = InventoryFake(None)
    resultado = VehiclePhotoProcessor(downloader, inventory).processar(
        "instancia-a", "MSG-FOTO-X", "ZZZ9Z99", "image/jpeg"
    )

    assert resultado["ok"] is False
    assert "Cadastre o veículo primeiro" in resultado["mensagem"]
    assert downloader.chamadas == []
    assert inventory.uploads == []


def test_downloader_imagem_usa_contrato_oficial_e_limita_tipo():
    conteudo = b"\xff\xd8\xfffoto"

    def handler(request: httpx.Request):
        assert request.url.path == "/chat/getBase64FromMediaMessage/instancia-a"
        assert request.headers["apikey"] == "segredo-evolution"
        assert json.loads(request.content) == {
            "message": {"key": {"id": "MSG-FOTO-1"}},
            "convertToMp4": False,
        }
        return httpx.Response(
            200,
            json={
                "mimetype": "image/jpeg",
                "size": {"fileLength": str(len(conteudo))},
                "base64": base64.b64encode(conteudo).decode(),
            },
        )

    downloader = EvolutionImageDownloader(
        "https://evolution.test",
        "segredo-evolution",
        transport=httpx.MockTransport(handler),
    )
    baixado, mime = downloader.baixar(
        "instancia-a", "MSG-FOTO-1", "image/jpeg"
    )

    assert baixado == conteudo
    assert mime == "image/jpeg"


def test_downloader_imagem_rejeita_base64_invalido():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"mimetype": "image/jpeg", "base64": "%%%invalido%%%"},
        )

    downloader = EvolutionImageDownloader(
        "https://evolution.test",
        "segredo",
        transport=httpx.MockTransport(handler),
    )
    try:
        downloader.baixar("instancia-a", "MSG-X", "image/jpeg")
        assert False, "base64 inválido deveria ser recusado"
    except Exception as exc:
        from app.vehicle_photo import ImagemIndisponivel

        assert isinstance(exc, ImagemIndisponivel)
