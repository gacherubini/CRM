"""Bus síncrono e best-effort para conversões outbound.

A venda já deve estar commitada antes da publicação. Cada adapter é uma fronteira
de falha: uma integração indisponível não impede que as demais recebam o evento e
nunca propaga erro para o fluxo que confirmou a venda.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, Sequence

from sqlalchemy.orm import Session

from app.conversions.types import ConversionKind, PurchaseConversion

logger = logging.getLogger(__name__)


class ConversionAdapter(Protocol):
    """Contrato mínimo de um destino de conversões."""

    name: str

    def handle(
        self,
        kind: ConversionKind,
        payload: PurchaseConversion,
        db: Session,
    ) -> object:
        """Aceita um evento; persistência/retry pertencem ao adapter."""


@dataclass(frozen=True)
class AdapterPublishResult:
    adapter: str
    accepted: bool


@dataclass(frozen=True)
class PublishResult:
    """Resumo operacional sem expor exceções ou dados pessoais."""

    event_id: str
    adapters: tuple[AdapterPublishResult, ...]

    @property
    def attempted(self) -> int:
        return len(self.adapters)

    @property
    def accepted(self) -> int:
        return sum(item.accepted for item in self.adapters)

    @property
    def failed(self) -> int:
        return self.attempted - self.accepted


def default_adapters() -> tuple[ConversionAdapter, ...]:
    """Constrói os adapters padrão sem manter estado global mutável."""

    # Import tardio evita ciclos e permite acrescentar adapters sem acoplar types.
    from app.conversions.meta import MetaAdapter
    from app.conversions.meta_messaging import MetaMessagingAdapter

    return (MetaAdapter(), MetaMessagingAdapter())


def publish_conversion(
    kind: ConversionKind | str,
    payload: PurchaseConversion,
    db: Session,
    *,
    adapters: Sequence[ConversionAdapter] | None = None,
) -> PublishResult:
    """Publica em todos os adapters, isolando integralmente suas falhas."""

    try:
        normalized_kind = ConversionKind(kind)
    except ValueError:
        logger.warning(
            "conversion_bus: tipo de conversão desconhecido event_id=%s",
            payload.event_id,
        )
        return PublishResult(event_id=payload.event_id, adapters=())

    destinos = tuple(adapters) if adapters is not None else default_adapters()
    resultados: list[AdapterPublishResult] = []
    for adapter in destinos:
        nome = str(getattr(adapter, "name", adapter.__class__.__name__))
        try:
            adapter.handle(normalized_kind, payload, db)
        except Exception as exc:
            rollback = getattr(db, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception:
                    pass
            # Não logar mensagem/representação da exceção: SDKs podem incluir token/PII.
            logger.warning(
                "conversion_bus: adapter falhou adapter=%s kind=%s event_id=%s tipo=%s",
                nome,
                normalized_kind.value,
                payload.event_id,
                type(exc).__name__,
            )
            resultados.append(AdapterPublishResult(adapter=nome, accepted=False))
            continue
        resultados.append(AdapterPublishResult(adapter=nome, accepted=True))
    return PublishResult(event_id=payload.event_id, adapters=tuple(resultados))
