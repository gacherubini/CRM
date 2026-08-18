"""Port WhatsAppProvider (Fase 5 multi-WA — lean).

Adapters em memória e stub Evolution. QR/credenciais nunca vão a log.
Sem adapter Cloud API neste plano.
"""
from __future__ import annotations

import base64
import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from app import config
from app.models_db import WhatsAppCanal

logger = logging.getLogger("chatbot.whatsapp_provider")

# Estados canônicos do canal no Modo 1 (Baileys/Evolution). O vocabulário é o do
# ciclo do QR: a sessão cai, reconecta, o lojista some com o celular.
ESTADO_PENDENTE = "pendente"
ESTADO_CONECTADO = "conectado"
ESTADO_DESCONECTADO = "desconectado"
ESTADO_INATIVO = "inativo"

ESTADOS_MODO1 = frozenset(
    {ESTADO_PENDENTE, ESTADO_CONECTADO, ESTADO_DESCONECTADO, ESTADO_INATIVO}
)

# Estados do canal no Modo 2 (Cloud API). Um número Cloud não "desconecta": ele
# está registrado na WABA ou não está, e o que muda é o veredito da Meta sobre
# ele (qualidade, limite, bloqueio). Prefixo ``cloud_`` de propósito — os dois
# vocabulários dividem a mesma coluna e não podem colidir.
#
#   cloud_pendente → cadastrado na WABA, ainda não registrado/verificado.
#   cloud_ativo    → registrado; envia e recebe.
#   cloud_restrito → vivo, mas limitado pela Meta (qualidade baixa / rate limit).
#   cloud_banido   → número ou WABA bloqueado; nada sai.
ESTADO_CLOUD_PENDENTE = "cloud_pendente"
ESTADO_CLOUD_ATIVO = "cloud_ativo"
ESTADO_CLOUD_RESTRITO = "cloud_restrito"
ESTADO_CLOUD_BANIDO = "cloud_banido"

ESTADOS_MODO2 = frozenset(
    {
        ESTADO_CLOUD_PENDENTE,
        ESTADO_CLOUD_ATIVO,
        ESTADO_CLOUD_RESTRITO,
        ESTADO_CLOUD_BANIDO,
    }
)

# Acréscimo, não troca: o Modo 1 depende dos quatro primeiros e nenhum saiu.
ESTADOS_VALIDOS = ESTADOS_MODO1 | ESTADOS_MODO2

# Eventos do webhook gravados em instância nova. Origem: o script que configura
# o webhook da instância legado em operação, `deploy/fly/3vm/set-evolution-webhook.ps1:40`
# (`events = @("MESSAGES_UPSERT")`) — único evento Evolution referenciado no
# repositório. Não editar por palpite: evento faltando faz a instância nova
# receber silêncio, e o sintoma só aparece em operação.
EVOLUTION_WEBHOOK_EVENTS: tuple[str, ...] = (
    "MESSAGES_UPSERT",
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


def _map_evolution_state(dados: object) -> str:
    """Traduz o payload de connectionState para os estados canônicos."""
    bruto = ""
    if isinstance(dados, dict):
        instancia = dados.get("instance")
        if isinstance(instancia, dict):
            bruto = str(instancia.get("state") or "")
        if not bruto:
            bruto = str(dados.get("state") or "")
    if bruto == "open":
        return ESTADO_CONECTADO
    if bruto == "connecting":
        return ESTADO_PENDENTE
    return ESTADO_DESCONECTADO


def _instancia_existe(payload: object, nome: str) -> bool:
    """fetchInstances varia de formato entre versões da Evolution."""
    itens: list = []
    if isinstance(payload, list):
        itens = payload
    elif isinstance(payload, dict):
        bruto = payload.get("instances") or payload.get("data")
        if isinstance(bruto, list):
            itens = bruto
    for item in itens:
        if not isinstance(item, dict):
            continue
        interno = item.get("instance") if isinstance(item.get("instance"), dict) else item
        if nome in {interno.get("name"), interno.get("instanceName")}:
            return True
    return False


class WhatsAppProvisionError(RuntimeError):
    """Falha ao provisionar/parear canal no provedor. Nunca carrega QR nem apikey."""

    def __init__(self, message: str, *, code: str = "evolution_provision_failed"):
        super().__init__(message)
        self.code = code


class EvolutionWhatsAppProvider:
    """Adapter real da Evolution API: ensure_instance, status, connect e disconnect.

    ``connect`` provisiona a instância (com webhook) antes de pedir o QR, então o
    adapter está funcionalmente completo. O que falta antes de ligar
    ``CHATBOT_WHATSAPP_PROVIDER=evolution`` em produção é validação em lab
    (Task 11 do plano): confirmar contra uma Evolution real o formato de
    ``fetchInstances``, o create e o pareamento ponta a ponta.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        webhook_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (
            base_url if base_url is not None else config.EVOLUTION_URL
        ).rstrip("/")
        self.api_key = (
            api_key if api_key is not None else config.EVOLUTION_API_KEY
        ) or ""
        self.webhook_url = (
            webhook_url if webhook_url is not None else config.EVOLUTION_WEBHOOK_URL
        )
        self.timeout = timeout if timeout is not None else config.EVOLUTION_SEND_TIMEOUT
        self.transport = transport

    def ensure_instance(self, canal: WhatsAppCanal) -> None:
        """Garante que a instância existe na Evolution, com webhook configurado.

        Idempotente: instância já existente não é erro e não é reconfigurada.
        """
        if not self.webhook_url:
            raise WhatsAppProvisionError(
                "CHATBOT_EVOLUTION_WEBHOOK_URL não configurado",
                code="evolution_webhook_not_configured",
            )
        nome = canal.evolution_instance
        with self._client() as client:
            existentes = self._request(client, "GET", "/instance/fetchInstances")
            if _instancia_existe(existentes, nome):
                return
            self._request(
                client,
                "POST",
                "/instance/create",
                json={
                    "instanceName": nome,
                    "integration": "WHATSAPP-BAILEYS",
                    "qrcode": False,
                    "webhook": {
                        "url": self.webhook_url,
                        "byEvents": False,
                        "events": list(EVOLUTION_WEBHOOK_EVENTS),
                    },
                },
            )

    def _client(self) -> httpx.Client:
        if not self.base_url or not self.api_key:
            raise WhatsAppProvisionError(
                "Evolution não configurada",
                code="evolution_not_configured",
            )
        return httpx.Client(
            base_url=self.base_url,
            headers={"apikey": self.api_key},
            timeout=self.timeout,
            transport=self.transport,
        )

    def _request(self, client: httpx.Client, method: str, path: str, **kwargs):
        try:
            resposta = client.request(method, path, **kwargs)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("Evolution %s falhou err=%s", path, type(exc).__name__)
            raise WhatsAppProvisionError(
                "não foi possível contatar a Evolution",
                code="evolution_unreachable",
            ) from exc
        if resposta.status_code >= 400:
            logger.warning("Evolution %s status=%s", path, resposta.status_code)
            raise WhatsAppProvisionError(
                f"Evolution recusou a operação (HTTP {resposta.status_code})",
                code="evolution_provision_failed",
            )
        if not resposta.content:
            return {}
        try:
            return resposta.json()
        except ValueError:
            return {}

    def status(self, canal: WhatsAppCanal) -> StatusResult:
        inst = quote(canal.evolution_instance, safe="")
        with self._client() as client:
            dados = self._request(client, "GET", f"/instance/connectionState/{inst}")
        estado = _map_evolution_state(dados)
        return StatusResult(
            estado=estado,
            ativo=bool(canal.ativo),
            evolution_instance=canal.evolution_instance,
        )

    def connect(self, canal: WhatsAppCanal) -> ConnectResult:
        if not canal.ativo or canal.estado == ESTADO_INATIVO:
            return ConnectResult(estado=ESTADO_INATIVO)
        self.ensure_instance(canal)
        inst = quote(canal.evolution_instance, safe="")
        with self._client() as client:
            dados = self._request(client, "GET", f"/instance/connect/{inst}")
        qr = dados.get("base64") or dados.get("code")
        if not qr:
            # Já pareado: a Evolution não devolve QR quando o estado é open.
            canal.estado = ESTADO_CONECTADO
            return ConnectResult(estado=ESTADO_CONECTADO)
        canal.estado = ESTADO_PENDENTE
        return ConnectResult(
            estado=ESTADO_PENDENTE,
            qr_payload=qr,
            expires_in_seconds=60,
            pairing_code=dados.get("pairingCode"),
        )

    def disconnect(self, canal: WhatsAppCanal) -> StatusResult:
        inst = quote(canal.evolution_instance, safe="")
        with self._client() as client:
            self._request(client, "DELETE", f"/instance/logout/{inst}")
        canal.estado = ESTADO_DESCONECTADO
        return StatusResult(
            estado=ESTADO_DESCONECTADO,
            ativo=bool(canal.ativo),
            evolution_instance=canal.evolution_instance,
        )


_provider: WhatsAppProvider | None = None


def get_whatsapp_provider() -> WhatsAppProvider:
    global _provider
    if _provider is None:
        if config.WHATSAPP_PROVIDER == "evolution":
            _provider = EvolutionWhatsAppProvider()
        else:
            _provider = EvolutionStubWhatsAppProvider()
    return _provider


def set_whatsapp_provider(provider: WhatsAppProvider | None) -> None:
    """Sobrescreve o provider (testes). None restaura o stub padrão."""
    global _provider
    _provider = provider
