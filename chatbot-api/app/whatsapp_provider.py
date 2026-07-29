"""Port WhatsAppProvider (Fase 5 multi-WA — lean).

Adapters em memória e stub Evolution. QR/credenciais nunca vão a log.
Sem adapter Cloud API neste plano.
"""
from __future__ import annotations

import base64
import secrets
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.models_db import WhatsAppCanal

# Estados canônicos do canal.
ESTADO_PENDENTE = "pendente"
ESTADO_CONECTADO = "conectado"
ESTADO_DESCONECTADO = "desconectado"
ESTADO_INATIVO = "inativo"

ESTADOS_VALIDOS = frozenset(
    {ESTADO_PENDENTE, ESTADO_CONECTADO, ESTADO_DESCONECTADO, ESTADO_INATIVO}
)


@dataclass(frozen=True)
class ConnectResult:
    estado: str
    qr_payload: str | None = None
    expires_in_seconds: int | None = None
    pairing_code: str | None = None


@dataclass(frozen=True)
class StatusResult:
    estado: str
    ativo: bool
    evolution_instance: str


class WhatsAppProvider(Protocol):
    """Provedor de conexão do canal (sem log de QR/credenciais)."""

    def connect(self, canal: WhatsAppCanal) -> ConnectResult:
        """Inicia pareamento; pode devolver QR efêmero."""

    def status(self, canal: WhatsAppCanal) -> StatusResult:
        """Consulta estado atual do canal."""

    def disconnect(self, canal: WhatsAppCanal) -> StatusResult:
        """Desconecta mantendo o canal na loja (permite reconectar)."""


def _fake_qr_payload(instance: str) -> str:
    """Payload base64 opaco para testes/UI — não é QR real Evolution."""
    raw = f"revy-qr:{instance}:{uuid.uuid4().hex}:{secrets.token_hex(16)}"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


class MemoryWhatsAppProvider:
    """Adapter de teste: pareamento instantâneo com QR fake."""

    def connect(self, canal: WhatsAppCanal) -> ConnectResult:
        if not canal.ativo or canal.estado == ESTADO_INATIVO:
            return ConnectResult(estado=ESTADO_INATIVO)
        if canal.estado == ESTADO_CONECTADO:
            return ConnectResult(estado=ESTADO_CONECTADO)
        # Simula pareamento OK sem provedor externo.
        canal.estado = ESTADO_CONECTADO
        return ConnectResult(
            estado=ESTADO_CONECTADO,
            qr_payload=_fake_qr_payload(canal.evolution_instance),
            expires_in_seconds=60,
        )

    def status(self, canal: WhatsAppCanal) -> StatusResult:
        return StatusResult(
            estado=canal.estado,
            ativo=bool(canal.ativo),
            evolution_instance=canal.evolution_instance,
        )

    def disconnect(self, canal: WhatsAppCanal) -> StatusResult:
        if canal.estado != ESTADO_INATIVO:
            canal.estado = ESTADO_DESCONECTADO
        return self.status(canal)


class EvolutionStubWhatsAppProvider:
    """Stub Evolution: mesmo comportamento do Memory, sem rede.

    Ponto de extensão para EvolutionAdapter real (fora do lean).
    """

    def __init__(self) -> None:
        self._inner = MemoryWhatsAppProvider()

    def connect(self, canal: WhatsAppCanal) -> ConnectResult:
        # Nunca loga QR; apenas devolve no payload HTTP com Cache-Control: no-store.
        return self._inner.connect(canal)

    def status(self, canal: WhatsAppCanal) -> StatusResult:
        return self._inner.status(canal)

    def disconnect(self, canal: WhatsAppCanal) -> StatusResult:
        return self._inner.disconnect(canal)


_provider: WhatsAppProvider | None = None


def get_whatsapp_provider() -> WhatsAppProvider:
    global _provider
    if _provider is None:
        _provider = EvolutionStubWhatsAppProvider()
    return _provider


def set_whatsapp_provider(provider: WhatsAppProvider | None) -> None:
    """Sobrescreve o provider (testes). None restaura o stub padrão."""
    global _provider
    _provider = provider
