"""Ingestão efêmera de foto enviada por vendedor autorizado no WhatsApp."""
from __future__ import annotations

import base64
import binascii
import json
import logging
from typing import Protocol
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app import config
from app.inventory import InventoryWriteClient, get_inventory_write_client


logger = logging.getLogger("chatbot.vehicle_photo")
MIMES_IMAGEM = frozenset({"image/jpeg", "image/png", "image/webp"})


class ImagemIndisponivel(RuntimeError):
    pass


class ImageDownloader(Protocol):
    def baixar(
        self, instancia: str, message_id: str, mime_declarado: str | None = None
    ) -> tuple[bytes, str]: ...


def normalizar_mime(valor: object) -> str:
    mime = str(valor or "").split(";", 1)[0].strip().lower()
    if mime not in MIMES_IMAGEM:
        raise ImagemIndisponivel("tipo de imagem não permitido")
    return mime


class EvolutionImageDownloader:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or config.IMAGE_EVOLUTION_URL).rstrip("/")
        self.api_key = api_key or config.IMAGE_EVOLUTION_API_KEY
        self.timeout = timeout or config.IMAGE_DOWNLOAD_TIMEOUT
        self.transport = transport

    def baixar(
        self, instancia: str, message_id: str, mime_declarado: str | None = None
    ) -> tuple[bytes, str]:
        if not self.base_url or not self.api_key:
            raise ImagemIndisponivel("download de imagem não configurado")
        if mime_declarado:
            normalizar_mime(mime_declarado)
        limite_json = ((config.IMAGE_MAX_BYTES + 2) // 3 * 4) + 64 * 1024
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"apikey": self.api_key},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                with client.stream(
                    "POST",
                    f"/chat/getBase64FromMediaMessage/{quote(instancia, safe='')}",
                    json={
                        "message": {"key": {"id": message_id}},
                        "convertToMp4": False,
                    },
                ) as resposta:
                    resposta.raise_for_status()
                    bruto = bytearray()
                    for parte in resposta.iter_bytes():
                        bruto.extend(parte)
                        if len(bruto) > limite_json:
                            raise ImagemIndisponivel("resposta de imagem acima do limite")
        except ImagemIndisponivel:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ImagemIndisponivel("não foi possível obter a imagem") from exc
        try:
            payload = json.loads(bruto)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ImagemIndisponivel("resposta de imagem inválida") from exc
        return self._decodificar(payload, mime_declarado)

    @staticmethod
    def _decodificar(payload: object, mime_declarado: str | None) -> tuple[bytes, str]:
        if not isinstance(payload, dict):
            raise ImagemIndisponivel("resposta de imagem inválida")
        dados = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        base64_texto = dados.get("base64")
        if not isinstance(base64_texto, str) or not base64_texto:
            raise ImagemIndisponivel("imagem ausente na resposta")
        mime_data_uri = None
        if base64_texto.startswith("data:") and ";base64," in base64_texto[:160]:
            cabecalho, base64_texto = base64_texto.split(",", 1)
            mime_data_uri = cabecalho[5:].split(";", 1)[0]
        mime = normalizar_mime(
            dados.get("mimetype")
            or dados.get("mimeType")
            or mime_data_uri
            or mime_declarado
        )
        tamanho = dados.get("size")
        if isinstance(tamanho, dict):
            tamanho = tamanho.get("fileLength")
        if tamanho not in (None, ""):
            try:
                if int(tamanho) > config.IMAGE_MAX_BYTES:
                    raise ImagemIndisponivel("imagem acima do limite")
            except (TypeError, ValueError) as exc:
                raise ImagemIndisponivel("tamanho de imagem inválido") from exc
        limite_base64 = ((config.IMAGE_MAX_BYTES + 2) // 3 * 4) + 4
        if len(base64_texto) > limite_base64:
            raise ImagemIndisponivel("imagem acima do limite")
        try:
            conteudo = base64.b64decode(base64_texto, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImagemIndisponivel("base64 de imagem inválido") from exc
        if not conteudo or len(conteudo) > config.IMAGE_MAX_BYTES:
            raise ImagemIndisponivel("tamanho de imagem inválido")
        return conteudo, mime


class VehiclePhotoProcessor:
    def __init__(self, downloader: ImageDownloader, inventory: InventoryWriteClient):
        self.downloader = downloader
        self.inventory = inventory

    def processar(
        self,
        instancia: str,
        message_id: str,
        placa: str,
        mime_type: str | None,
    ) -> dict:
        try:
            veiculo = self.inventory.obter_por_placa(placa)
            if not veiculo:
                return {
                    "ok": False,
                    "mensagem": f"Não encontrei veículo com a placa {placa}. Cadastre o veículo primeiro e reenvie a foto com a placa na legenda.",
                }
            conteudo, mime = self.downloader.baixar(instancia, message_id, mime_type)
            atualizado = self.inventory.adicionar_foto(
                str(veiculo["id"]),
                conteudo,
                mime,
                idempotency_key=f"wa-foto:{message_id}",
                publicar=True,
            )
            quantidade = len(atualizado.get("fotos") or [])
            return {
                "ok": True,
                "mensagem": f"Foto adicionada ao veículo {placa}. Ele já está atualizado no estoque e no catálogo.",
                "veiculo_id": atualizado.get("id"),
                "placa": placa,
                "quantidade_fotos": quantidade,
                "publicado": bool(atualizado.get("publicado")),
            }
        except (ImagemIndisponivel, HTTPException, KeyError, TypeError, ValueError):
            logger.warning("foto de veículo não processada")
            return {
                "ok": False,
                "mensagem": "Não consegui salvar essa foto. Confira se é JPG, PNG ou WebP e tente novamente com a placa na legenda.",
            }


def get_vehicle_photo_processor() -> VehiclePhotoProcessor:
    return VehiclePhotoProcessor(
        EvolutionImageDownloader(),
        get_inventory_write_client(),
    )
