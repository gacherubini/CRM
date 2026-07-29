"""Port de canais WhatsApp do Control → Chatbot (Fase 5 multi-WA).

O Chatbot é dono dos registros. O Control consulta/muta via port; adapters HTTP
(produção) e em memória (testes). Número nunca muda de loja no Chatbot.
Admin e Gestor Responsável mutam; colaborador só lê.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.clients._retry import requisicao_com_retry
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    ControlError,
    StoreNotFound,
    StoreRef,
    TrafficRole,
)
from app.models import Loja, VinculoTrafego


class WhatsAppChannelsError(ControlError):
    """Falha ao consultar/mutar canais WhatsApp."""


class WhatsAppChannelsUnavailable(WhatsAppChannelsError):
    """Chatbot indisponível ou integração não configurada."""


class WhatsAppChannelNotFound(WhatsAppChannelsError):
    """Canal inexistente na loja."""


@dataclass(frozen=True)
class WhatsAppChannelView:
    id: str
    loja_id: str
    e164_or_label: str
    evolution_instance: str
    ativo: bool
    estado: str = "pendente"
    criado_em: str | None = None
    qr_payload: str | None = None
    expires_in_seconds: int | None = None


class WhatsAppChannelsPort(Protocol):
    """Porta de canais WhatsApp (sem autorização de Control)."""

    def list_for_store(self, store_ref: StoreRef) -> list[WhatsAppChannelView]:
        """Lista canais da loja no Chatbot (ou memória)."""

    def register(
        self, store_ref: StoreRef, *, instance: str, label: str
    ) -> WhatsAppChannelView:
        """Cadastra canal na loja."""

    def connect(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        """Inicia conexão; pode devolver qr_payload."""

    def disconnect(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        """Desconecta o canal."""

    def inactivate(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        """Inativa o canal (sem apagar)."""


def _view_from_dict(item: dict[str, Any], loja_id: str) -> WhatsAppChannelView:
    return WhatsAppChannelView(
        id=str(item.get("id") or ""),
        loja_id=str(item.get("loja_id") or loja_id),
        e164_or_label=str(item.get("e164_or_label") or ""),
        evolution_instance=str(item.get("evolution_instance") or ""),
        ativo=bool(item.get("ativo", True)),
        estado=str(item.get("estado") or "pendente"),
        criado_em=item.get("criado_em"),
        qr_payload=item.get("qr_payload"),
        expires_in_seconds=(
            int(item["expires_in_seconds"])
            if item.get("expires_in_seconds") is not None
            else None
        ),
    )


@dataclass
class InMemoryWhatsAppChannels:
    """Adapter de teste: mapa loja_id → canais."""

    channels_by_store: dict[str, list[WhatsAppChannelView]] = field(
        default_factory=dict
    )

    def list_for_store(self, store_ref: StoreRef) -> list[WhatsAppChannelView]:
        return list(self.channels_by_store.get(store_ref.id or "", []))

    def seed(self, store_id: str, *channels: WhatsAppChannelView) -> None:
        self.channels_by_store[store_id] = list(channels)

    def register(
        self, store_ref: StoreRef, *, instance: str, label: str
    ) -> WhatsAppChannelView:
        store_id = store_ref.id or ""
        existing = self.channels_by_store.setdefault(store_id, [])
        for ch in existing:
            if ch.evolution_instance == instance:
                if ch.loja_id != store_id:
                    raise WhatsAppChannelsError("instância já vinculada a outra loja")
                return ch
        view = WhatsAppChannelView(
            id=f"mem-{len(existing)+1}-{instance[:8]}",
            loja_id=store_id,
            e164_or_label=label,
            evolution_instance=instance,
            ativo=True,
            estado="pendente",
        )
        existing.append(view)
        return view

    def connect(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        ch = self._get(store_ref, canal_id)
        if not ch.ativo:
            raise WhatsAppChannelsError("canal inativo")
        updated = WhatsAppChannelView(
            id=ch.id,
            loja_id=ch.loja_id,
            e164_or_label=ch.e164_or_label,
            evolution_instance=ch.evolution_instance,
            ativo=True,
            estado="conectado",
            criado_em=ch.criado_em,
            qr_payload="bWVtLXFyLXBheWxvYWQ=",  # "mem-qr-payload" b64-ish fake
            expires_in_seconds=60,
        )
        self._replace(store_ref, updated)
        return updated

    def disconnect(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        ch = self._get(store_ref, canal_id)
        if not ch.ativo:
            raise WhatsAppChannelsError("canal inativo")
        updated = WhatsAppChannelView(
            id=ch.id,
            loja_id=ch.loja_id,
            e164_or_label=ch.e164_or_label,
            evolution_instance=ch.evolution_instance,
            ativo=True,
            estado="desconectado",
            criado_em=ch.criado_em,
        )
        self._replace(store_ref, updated)
        return updated

    def inactivate(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        ch = self._get(store_ref, canal_id)
        updated = WhatsAppChannelView(
            id=ch.id,
            loja_id=ch.loja_id,
            e164_or_label=ch.e164_or_label,
            evolution_instance=ch.evolution_instance,
            ativo=False,
            estado="inativo",
            criado_em=ch.criado_em,
        )
        self._replace(store_ref, updated)
        return updated

    def _get(self, store_ref: StoreRef, canal_id: str) -> WhatsAppChannelView:
        store_id = store_ref.id or ""
        for ch in self.channels_by_store.get(store_id, []):
            if ch.id == canal_id:
                return ch
        raise WhatsAppChannelNotFound("canal não encontrado")

    def _replace(self, store_ref: StoreRef, updated: WhatsAppChannelView) -> None:
        store_id = store_ref.id or ""
        rows = self.channels_by_store.setdefault(store_id, [])
        for i, ch in enumerate(rows):
            if ch.id == updated.id:
                rows[i] = updated
                return
        rows.append(updated)


@dataclass
class HttpWhatsAppChannels:
    """Adapter HTTP para endpoints de canais do Chatbot."""

    base_url: str
    token_for_slug: Callable[[str], str]
    session_factory: Callable[[], Any]
    timeout: float = 5.0
    retries: int = 1
    retry_backoff: float = 0.05

    def list_for_store(self, store_ref: StoreRef) -> list[WhatsAppChannelView]:
        slug, loja_id = self._resolve_store(store_ref)
        payload = self._request(slug, "GET", "/v1/whatsapp/canais")
        items = payload.get("canais") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise WhatsAppChannelsUnavailable("resposta inválida do chatbot")
        out: list[WhatsAppChannelView] = []
        for item in items:
            if isinstance(item, dict):
                out.append(_view_from_dict(item, loja_id))
        return out

    def register(
        self, store_ref: StoreRef, *, instance: str, label: str
    ) -> WhatsAppChannelView:
        slug, loja_id = self._resolve_store(store_ref)
        payload = self._request(
            slug,
            "POST",
            "/v1/whatsapp/canais",
            json={"evolution_instance": instance, "e164_or_label": label},
        )
        if not isinstance(payload, dict):
            raise WhatsAppChannelsUnavailable("resposta inválida do chatbot")
        return _view_from_dict(payload, loja_id)

    def connect(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        slug, loja_id = self._resolve_store(store_ref)
        payload = self._request(
            slug, "POST", f"/v1/whatsapp/canais/{canal_id}/connect"
        )
        if not isinstance(payload, dict):
            raise WhatsAppChannelsUnavailable("resposta inválida do chatbot")
        return _view_from_dict(payload, loja_id)

    def disconnect(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        slug, loja_id = self._resolve_store(store_ref)
        payload = self._request(
            slug, "POST", f"/v1/whatsapp/canais/{canal_id}/disconnect"
        )
        if not isinstance(payload, dict):
            raise WhatsAppChannelsUnavailable("resposta inválida do chatbot")
        return _view_from_dict(payload, loja_id)

    def inactivate(
        self, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        slug, loja_id = self._resolve_store(store_ref)
        payload = self._request(
            slug, "POST", f"/v1/whatsapp/canais/{canal_id}/inativar"
        )
        if not isinstance(payload, dict):
            raise WhatsAppChannelsUnavailable("resposta inválida do chatbot")
        return _view_from_dict(payload, loja_id)

    def _request(
        self,
        slug: str,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
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
                    method,
                    path,
                    retries=self.retries,
                    backoff=self.retry_backoff,
                    json=json,
                )
                if resp.status_code == 404:
                    raise WhatsAppChannelNotFound("canal não encontrado")
                if resp.status_code == 409:
                    raise WhatsAppChannelsError(
                        resp.json().get("detail")
                        if resp.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else "conflito no chatbot"
                    )
                resp.raise_for_status()
                return resp.json()
        except WhatsAppChannelsError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise WhatsAppChannelsUnavailable(
                "não foi possível operar canais no chatbot"
            ) from exc

    def _resolve_store(self, store_ref: StoreRef) -> tuple[str, str]:
        with self.session_factory() as db:
            store = db.get(Loja, store_ref.id) if store_ref.id else None
            if store is None and store_ref.slug:
                store = (
                    db.query(Loja)
                    .filter(Loja.slug == store_ref.slug.strip().lower())
                    .first()
                )
            if store is None:
                raise StoreNotFound("loja não encontrada")
            return store.slug, store.id


class WhatsAppChannelsControl:
    """Caso de uso: autoriza no Control e opera canais via port."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        port: WhatsAppChannelsPort,
    ) -> None:
        self._stores = StoreControl(session_factory)
        self._port = port
        self._session_factory = session_factory

    def list_channels(
        self, actor: Actor, store_ref: StoreRef
    ) -> list[WhatsAppChannelView]:
        self._stores.get(actor, store_ref)
        return self._port.list_for_store(store_ref)

    def register(
        self,
        actor: Actor,
        store_ref: StoreRef,
        *,
        instance: str,
        label: str,
    ) -> WhatsAppChannelView:
        store = self._stores.get(actor, store_ref)
        self._require_can_manage(actor, store.id)
        return self._port.register(
            StoreRef(id=store.id), instance=instance, label=label
        )

    def connect(
        self, actor: Actor, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        store = self._stores.get(actor, store_ref)
        self._require_can_manage(actor, store.id)
        return self._port.connect(StoreRef(id=store.id), canal_id)

    def disconnect(
        self, actor: Actor, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        store = self._stores.get(actor, store_ref)
        self._require_can_manage(actor, store.id)
        return self._port.disconnect(StoreRef(id=store.id), canal_id)

    def inactivate(
        self, actor: Actor, store_ref: StoreRef, canal_id: str
    ) -> WhatsAppChannelView:
        store = self._stores.get(actor, store_ref)
        self._require_can_manage(actor, store.id)
        return self._port.inactivate(StoreRef(id=store.id), canal_id)

    def _require_can_manage(self, actor: Actor, loja_id: str) -> None:
        """Admin ou Gestor Responsável; colaborador → AccessDenied."""
        if actor.is_admin:
            return
        with self._session_factory() as db:
            link = (
                db.query(VinculoTrafego)
                .filter(
                    VinculoTrafego.loja_id == loja_id,
                    VinculoTrafego.gestor_id == actor.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .first()
            )
            if link is None:
                raise StoreNotFound("Loja não encontrada")
            if link.tipo != TrafficRole.RESPONSIBLE.value:
                raise AccessDenied(
                    "somente Admin Revy ou Gestor Responsável pode "
                    "alterar canais WhatsApp"
                )
