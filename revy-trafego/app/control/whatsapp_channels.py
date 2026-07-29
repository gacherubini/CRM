"""Port de canais WhatsApp do Control → Chatbot (Fase 5 multi-WA skeleton).

O Chatbot é dono dos registros. O Control consulta via port; adapters HTTP
(produção) e em memória (testes). Número nunca muda de loja no Chatbot.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.clients._retry import requisicao_com_retry
from app.control.stores import StoreControl
from app.control.types import Actor, ControlError, StoreRef
from app.models import Loja


class WhatsAppChannelsError(ControlError):
    """Falha ao consultar canais WhatsApp."""


class WhatsAppChannelsUnavailable(WhatsAppChannelsError):
    """Chatbot indisponível ou integração não configurada."""


@dataclass(frozen=True)
class WhatsAppChannelView:
    id: str
    loja_id: str
    e164_or_label: str
    evolution_instance: str
    ativo: bool
    criado_em: str | None = None


class WhatsAppChannelsPort(Protocol):
    """Porta de consulta de canais WhatsApp (sem autorização de Control)."""

    def list_for_store(self, store_ref: StoreRef) -> list[WhatsAppChannelView]:
        """Lista canais da loja no Chatbot (ou memória)."""


@dataclass
class InMemoryWhatsAppChannels:
    """Adapter de teste: mapa loja_id → canais."""

    channels_by_store: dict[str, list[WhatsAppChannelView]] = field(
        default_factory=dict
    )

    def list_for_store(self, store_ref: StoreRef) -> list[WhatsAppChannelView]:
        return list(self.channels_by_store.get(store_ref.id, []))

    def seed(self, store_id: str, *channels: WhatsAppChannelView) -> None:
        self.channels_by_store[store_id] = list(channels)


@dataclass
class HttpWhatsAppChannels:
    """Adapter HTTP: GET /v1/whatsapp/canais no Chatbot com token da loja."""

    base_url: str
    token_for_slug: Callable[[str], str]
    session_factory: Callable[[], Any]
    timeout: float = 5.0
    retries: int = 1
    retry_backoff: float = 0.05

    def list_for_store(self, store_ref: StoreRef) -> list[WhatsAppChannelView]:
        slug, loja_id = self._resolve_store(store_ref)
        token = (self.token_for_slug(slug) or "").strip()
        base = (self.base_url or "").rstrip("/")
        if not base or not token:
            raise WhatsAppChannelsUnavailable(
                "integração chatbot de canais não configurada"
            )
        try:
            with httpx.Client(
                base_url=base,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            ) as client:
                resp = requisicao_com_retry(
                    client,
                    "GET",
                    "/v1/whatsapp/canais",
                    retries=self.retries,
                    backoff=self.retry_backoff,
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WhatsAppChannelsUnavailable(
                "não foi possível consultar canais no chatbot"
            ) from exc

        items = payload.get("canais") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise WhatsAppChannelsUnavailable("resposta inválida do chatbot")
        out: list[WhatsAppChannelView] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(
                WhatsAppChannelView(
                    id=str(item.get("id") or ""),
                    loja_id=str(item.get("loja_id") or loja_id),
                    e164_or_label=str(item.get("e164_or_label") or ""),
                    evolution_instance=str(item.get("evolution_instance") or ""),
                    ativo=bool(item.get("ativo", True)),
                    criado_em=item.get("criado_em"),
                )
            )
        return out

    def _resolve_store(self, store_ref: StoreRef) -> tuple[str, str]:
        with self.session_factory() as db:
            store = db.get(Loja, store_ref.id)
            if store is None:
                from app.control.types import StoreNotFound

                raise StoreNotFound("loja não encontrada")
            return store.slug, store.id


class WhatsAppChannelsControl:
    """Caso de uso: autoriza no Control e consulta canais via port."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        port: WhatsAppChannelsPort,
    ) -> None:
        self._stores = StoreControl(session_factory)
        self._port = port

    def list_channels(
        self, actor: Actor, store_ref: StoreRef
    ) -> list[WhatsAppChannelView]:
        # Reusa isolamento de loja do StoreControl (admin ou gestor vinculado).
        self._stores.get(actor, store_ref)
        return self._port.list_for_store(store_ref)
