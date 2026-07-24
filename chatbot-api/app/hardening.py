"""Proteções de borda do webhook sem reter ou registrar dados pessoais."""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import config


logger = logging.getLogger("chatbot.webhook")

_TELEFONE_FORMATADO_RE = re.compile(r"^[+\d\s().-]+$")
_SUFIXOS_WHATSAPP = ("@s.whatsapp.net", "@c.us")
_PARTICIPANTE_LID_RE = re.compile(r"^\d{8,32}@lid$", re.IGNORECASE)


def normalizar_telefone_webhook(valor: str) -> str:
    """Retorna telefone só com dígitos ou rejeita identificadores ambíguos."""
    if not isinstance(valor, str):
        raise ValueError("telefone deve ser texto")
    telefone = valor.strip()
    for sufixo in _SUFIXOS_WHATSAPP:
        if telefone.lower().endswith(sufixo):
            telefone = telefone[: -len(sufixo)]
            break
    if not telefone or not _TELEFONE_FORMATADO_RE.fullmatch(telefone):
        raise ValueError("telefone inválido")
    digitos = "".join(c for c in telefone if c.isdigit())
    if not 8 <= len(digitos) <= 15:
        raise ValueError("telefone deve conter entre 8 e 15 dígitos")
    return digitos


def normalizar_participante_whatsapp(valor: str) -> str:
    """Aceita telefone comum ou o identificador LID de um participante de grupo."""
    if isinstance(valor, str) and _PARTICIPANTE_LID_RE.fullmatch(valor.strip()):
        return valor.strip().lower()
    return normalizar_telefone_webhook(valor)


def validar_identificador(valor: str, *, nome: str, limite: int) -> str:
    """Normaliza identificadores curtos e recusa controles/valores vazios."""
    if not isinstance(valor, str):
        raise ValueError(f"{nome} deve ser texto")
    normalizado = valor.strip()
    if not normalizado:
        raise ValueError(f"{nome} é obrigatório")
    if len(normalizado) > max(1, limite):
        raise ValueError(f"{nome} excede o limite permitido")
    if any(ord(c) < 32 or ord(c) == 127 for c in normalizado):
        raise ValueError(f"{nome} contém caracteres inválidos")
    return normalizado


class WebhookPayloadLimitMiddleware:
    """Limita o corpo antes de FastAPI/Pydantic alocarem e parsearem o JSON."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._deve_limitar(scope):
            await self.app(scope, receive, send)
            return

        limite = max(1, int(config.WEBHOOK_MAX_PAYLOAD_BYTES))
        tamanho_declarado = self._content_length(scope)
        if tamanho_declarado is not None and tamanho_declarado > limite:
            await self._rejeitar(scope, receive, send)
            return

        partes: list[bytes] = []
        total = 0
        while True:
            mensagem = await receive()
            if mensagem["type"] == "http.disconnect":
                return
            parte = mensagem.get("body", b"")
            total += len(parte)
            if total > limite:
                await self._rejeitar(scope, receive, send)
                return
            partes.append(parte)
            if not mensagem.get("more_body", False):
                break

        corpo = b"".join(partes)
        entregue = False

        async def receive_limitado() -> Message:
            nonlocal entregue
            if entregue:
                return {"type": "http.disconnect"}
            entregue = True
            return {"type": "http.request", "body": corpo, "more_body": False}

        await self.app(scope, receive_limitado, send)

    @staticmethod
    def _deve_limitar(scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path")
            in {
                "/webhook/mensagem",
                "/webhook/audio/transcrever",
                "/webhook/operacao/veiculos/foto",
            }
        )

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for nome, valor in scope.get("headers", []):
            if nome.lower() != b"content-length":
                continue
            try:
                return max(0, int(valor))
            except ValueError:
                return None
        return None

    @staticmethod
    async def _rejeitar(scope: Scope, receive: Receive, send: Send) -> None:
        logger.warning("webhook rejeitado: payload acima do limite")
        resposta = JSONResponse(
            status_code=413,
            content={"detail": "payload do webhook excede o limite permitido"},
        )
        await resposta(scope, receive, send)


class WebhookRateLimiter:
    """Janela deslizante local, limitada em memória e sem chaves em logs."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: OrderedDict[str, deque[float]] = OrderedDict()

    def verificar(self, origem: str, escopo: str) -> int | None:
        limite = int(config.WEBHOOK_RATE_LIMIT_REQUESTS)
        janela = float(config.WEBHOOK_RATE_LIMIT_WINDOW_SECONDS)
        if limite <= 0 or janela <= 0:
            return None

        chave = self._chave(origem, escopo)
        agora = self._clock()
        inicio = agora - janela
        with self._lock:
            acessos = self._buckets.setdefault(chave, deque())
            while acessos and acessos[0] <= inicio:
                acessos.popleft()
            self._buckets.move_to_end(chave)
            if len(acessos) >= limite:
                return max(1, math.ceil(acessos[0] + janela - agora))
            acessos.append(agora)
            self._limitar_buckets()
        return None

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _limitar_buckets(self) -> None:
        maximo = max(1, int(config.WEBHOOK_RATE_LIMIT_MAX_BUCKETS))
        while len(self._buckets) > maximo:
            self._buckets.popitem(last=False)

    @staticmethod
    def _chave(origem: str, escopo: str) -> str:
        material = f"{origem}\0{escopo}".encode("utf-8", errors="replace")
        return hashlib.blake2b(material, digest_size=16).hexdigest()


webhook_rate_limiter = WebhookRateLimiter()


def aplicar_rate_limit(request: Request, escopo: str = "webhook") -> None:
    origem = request.client.host if request.client else "desconhecida"
    retry_after = webhook_rate_limiter.verificar(origem, escopo)
    if retry_after is None:
        return
    logger.warning("webhook rejeitado: limite de requisições excedido")
    raise HTTPException(
        status_code=429,
        detail="limite de requisições do webhook excedido",
        headers={"Retry-After": str(retry_after)},
    )
