"""Descoberta dos grupos da instancia Evolution sem expor a API key."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app import config


class GruposWhatsappIndisponiveis(RuntimeError):
    pass


def _lista_do_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for chave in ("chats", "groups", "grupos", "data", "records"):
        valor = payload.get(chave)
        if isinstance(valor, list):
            return [item for item in valor if isinstance(item, dict)]
        if isinstance(valor, dict):
            nested = _lista_do_payload(valor)
            if nested:
                return nested
    return []


def _jid_do_chat(chat: dict[str, Any]) -> str:
    for chave in ("remoteJid", "id", "jid"):
        valor = str(chat.get(chave) or "").strip().lower()
        if valor.endswith("@g.us"):
            return valor
    return ""


def _nome_do_chat(chat: dict[str, Any], jid: str) -> str:
    for chave in ("name", "subject", "pushName", "title"):
        valor = str(chat.get(chave) or "").strip()
        if valor:
            return valor[:160]
    return jid


def listar_grupos_whatsapp(instance: str) -> list[dict[str, str]]:
    base_url = str(config.IMAGE_EVOLUTION_URL or "").rstrip("/")
    api_key = str(config.IMAGE_EVOLUTION_API_KEY or "").strip()
    if not base_url or not api_key:
        raise GruposWhatsappIndisponiveis("Evolution nao configurada para listar grupos")

    url = f"{base_url}/chat/findChats/{quote(instance, safe='')}"
    try:
        with httpx.Client(timeout=max(1.0, config.IMAGE_DOWNLOAD_TIMEOUT)) as client:
            resposta = client.post(url, headers={"apikey": api_key}, json={})
            resposta.raise_for_status()
            payload = resposta.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GruposWhatsappIndisponiveis(
            "Nao foi possivel consultar os grupos do WhatsApp"
        ) from exc

    grupos: dict[str, dict[str, str]] = {}
    for chat in _lista_do_payload(payload):
        jid = _jid_do_chat(chat)
        if jid:
            grupos[jid] = {"jid": jid, "nome": _nome_do_chat(chat, jid)}
    return sorted(grupos.values(), key=lambda item: item["nome"].casefold())
