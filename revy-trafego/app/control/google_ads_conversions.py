"""Google Ads — bindings e outbox de conversões (Fase 4D lean).

Nunca cria conversion actions. Envio via GoogleDataManagerPort (fakes em testes).
Falha de upload não propaga para o chamador de enqueue (fire-and-forget).
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.control.audit import _append_event
from app.control.google_ads import (
    CONNECTION_STATUS_CONNECTED,
    FakeGoogleDataManagerPort,
    GoogleAdsConnectionNotFound,
    GoogleDataManagerPort,
    _assert_can_manage_connection,
    _assert_can_view_connection,
    _normalize_customer_id,
)
from app.control.stores import _find_store
from app.control.types import (
    Actor,
    ControlError,
    StoreNotFound,
    StoreRef,
)
from app.cripto import decifrar
from app.models import (
    GoogleAdsConnection,
    GoogleAdsConversionBinding,
    GoogleAdsConversionOutbox,
    GoogleAdsUploadAttempt,
    agora,
    novo_id,
)

logger = logging.getLogger(__name__)

OUTBOX_PENDING = "pending"
OUTBOX_SENT = "sent"
OUTBOX_FAILED = "failed"
OUTBOX_DEAD = "dead"

ATTEMPT_ACCEPTED = "accepted"
ATTEMPT_REJECTED = "rejected"
ATTEMPT_ERROR = "error"

DEFAULT_MAX_ATTEMPTS = 8
RETRY_BASE = timedelta(minutes=5)

EVENT_VENDA_CONFIRMADA = "venda_confirmada"


class GoogleAdsConversionBindingNotFound(ControlError):
    pass


class GoogleAdsInvalidConversionBinding(ControlError):
    pass


@dataclass(frozen=True)
class ConversionBindingView:
    id: str
    loja_id: str
    revy_event_type: str
    conversion_action_resource_name: str
    customer_id: str
    active: bool


@dataclass(frozen=True)
class ConversionOutboxView:
    id: str
    loja_id: str
    domain_event_id: str
    event_type: str
    transaction_id: str
    status: str
    request_id: str | None
    attempts: int


@dataclass(frozen=True)
class EnqueueConversion:
    loja_id: str
    event_type: str
    domain_event_id: str
    gclid: str | None = None
    gbraid: str | None = None
    wbraid: str | None = None
    value: Decimal | float | str | None = None
    currency: str = "BRL"
    consent: bool = False
    email: str | None = None
    phone: str | None = None
    conversion_time: datetime | None = None


def build_transaction_id(
    loja_id: str,
    event_type: str,
    domain_event_id: str,
) -> str:
    """transaction_id determinístico: revy:{loja_id}:{tipo}:{id_dominio}."""
    return f"revy:{loja_id}:{event_type}:{domain_event_id}"


def hash_user_value(value: str) -> str:
    """SHA-256 hex do valor normalizado (trim + lower)."""
    normalized = (value or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class GoogleAdsConversionsControl:
    """Bind de ações existentes + outbox idempotente de conversões."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        data_manager_port: GoogleDataManagerPort | None = None,
        now: Callable[[], datetime] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._session_factory = session_factory
        self._data_manager_port = data_manager_port or FakeGoogleDataManagerPort()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._max_attempts = max_attempts

    @property
    def data_manager_port(self) -> GoogleDataManagerPort:
        return self._data_manager_port

    def bind_conversion_action(
        self,
        actor: Actor,
        store: StoreRef,
        *,
        revy_event_type: str,
        conversion_action_resource_name: str,
        customer_id: str,
        active: bool = True,
    ) -> ConversionBindingView:
        """Mapeia evento Revy → conversion action existente (nunca cria no Google)."""
        event_type = (revy_event_type or "").strip()
        resource = (conversion_action_resource_name or "").strip()
        cid = _normalize_customer_id(customer_id)
        if not event_type:
            raise GoogleAdsInvalidConversionBinding("revy_event_type obrigatório")
        if not resource:
            raise GoogleAdsInvalidConversionBinding(
                "conversion_action_resource_name obrigatório"
            )
        if not cid:
            raise GoogleAdsInvalidConversionBinding("customer_id inválido")

        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_manage_connection(db, actor, loja.id)

            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)

            binding = (
                db.query(GoogleAdsConversionBinding)
                .filter(
                    GoogleAdsConversionBinding.loja_id == loja.id,
                    GoogleAdsConversionBinding.revy_event_type == event_type,
                )
                .first()
            )
            before: dict[str, object] | None = None
            if binding is None:
                binding = GoogleAdsConversionBinding(
                    id=novo_id(),
                    loja_id=loja.id,
                    revy_event_type=event_type,
                    conversion_action_resource_name=resource,
                    customer_id=cid,
                    active=bool(active),
                    created_at=now,
                    updated_at=now,
                )
                db.add(binding)
            else:
                before = {
                    "conversion_action_resource_name": (
                        binding.conversion_action_resource_name
                    ),
                    "customer_id": binding.customer_id,
                    "active": binding.active,
                }
                binding.conversion_action_resource_name = resource
                binding.customer_id = cid
                binding.active = bool(active)
                binding.updated_at = now

            _append_event(
                db,
                actor=actor,
                store_id=loja.id,
                action="google_ads.conversion_bound",
                resource_type="google_ads_conversion_binding",
                resource_id=binding.id,
                before=before,
                after={
                    "revy_event_type": event_type,
                    "conversion_action_resource_name": resource,
                    "customer_id": cid,
                    "active": bool(active),
                },
            )
            db.commit()
            db.refresh(binding)
            return _binding_view(binding)

    def list_bindings(
        self,
        actor: Actor,
        store: StoreRef,
    ) -> tuple[ConversionBindingView, ...]:
        with self._session_factory() as db:
            loja = _find_store(db, store)
            if loja is None:
                raise StoreNotFound("Loja não encontrada")
            _assert_can_view_connection(db, actor, loja.id)
            rows = (
                db.query(GoogleAdsConversionBinding)
                .filter(GoogleAdsConversionBinding.loja_id == loja.id)
                .order_by(GoogleAdsConversionBinding.revy_event_type.asc())
                .all()
            )
            return tuple(_binding_view(r) for r in rows)

    def enqueue_conversion(
        self,
        command: EnqueueConversion,
    ) -> ConversionOutboxView | None:
        """Enfileira conversão. Idempotente por transaction_id.

        Não levanta exceção de falha Google — erros de domínio leves
        (sem binding, sem click id) retornam None. Nunca bloqueia o caller.
        """
        try:
            return self._enqueue_conversion_inner(command)
        except Exception:  # pragma: no cover - defensive fire-and-forget
            logger.exception(
                "google_ads enqueue_conversion falhou (não propaga)",
                extra={
                    "loja_id": command.loja_id,
                    "event_type": command.event_type,
                    "domain_event_id": command.domain_event_id,
                },
            )
            return None

    def _enqueue_conversion_inner(
        self,
        command: EnqueueConversion,
    ) -> ConversionOutboxView | None:
        loja_id = (command.loja_id or "").strip()
        event_type = (command.event_type or "").strip()
        domain_event_id = (command.domain_event_id or "").strip()
        if not loja_id or not event_type or not domain_event_id:
            return None

        gclid = (command.gclid or "").strip() or None
        gbraid = (command.gbraid or "").strip() or None
        wbraid = (command.wbraid or "").strip() or None
        if not gclid and not gbraid and not wbraid:
            # Sem click ID e sem binding de user-data-only nesta fatia lean.
            return None

        transaction_id = build_transaction_id(loja_id, event_type, domain_event_id)

        with self._session_factory() as db:
            existing = (
                db.query(GoogleAdsConversionOutbox)
                .filter(
                    GoogleAdsConversionOutbox.transaction_id == transaction_id
                )
                .first()
            )
            if existing is not None:
                return _outbox_view(existing)

            binding = (
                db.query(GoogleAdsConversionBinding)
                .filter(
                    GoogleAdsConversionBinding.loja_id == loja_id,
                    GoogleAdsConversionBinding.revy_event_type == event_type,
                    GoogleAdsConversionBinding.active.is_(True),
                )
                .first()
            )
            if binding is None:
                return None

            now = self._now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)

            conversion_time = command.conversion_time or now
            if conversion_time.tzinfo is None:
                conversion_time = conversion_time.replace(tzinfo=timezone.utc)

            payload = _build_event_payload(
                transaction_id=transaction_id,
                conversion_action=binding.conversion_action_resource_name,
                conversion_time=conversion_time,
                gclid=gclid,
                gbraid=gbraid,
                wbraid=wbraid,
                value=command.value,
                currency=command.currency or "BRL",
                consent=bool(command.consent),
                email=command.email,
                phone=command.phone,
                customer_id=binding.customer_id,
                event_type=event_type,
            )
            row = GoogleAdsConversionOutbox(
                id=novo_id(),
                loja_id=loja_id,
                domain_event_id=domain_event_id,
                event_type=event_type,
                transaction_id=transaction_id,
                payload_json=json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":")
                ),
                status=OUTBOX_PENDING,
                next_attempt_at=now,
                request_id=None,
                attempts=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _outbox_view(row)

    def process_outbox_once(
        self,
        *,
        loja_id: str | None = None,
        limit: int = 20,
    ) -> int:
        """Processa itens pending/failed elegíveis. Retorna quantos foram sent."""
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        with self._session_factory() as db:
            q = db.query(GoogleAdsConversionOutbox).filter(
                GoogleAdsConversionOutbox.status.in_(
                    (OUTBOX_PENDING, OUTBOX_FAILED)
                ),
                GoogleAdsConversionOutbox.next_attempt_at <= now,
                GoogleAdsConversionOutbox.attempts < self._max_attempts,
            )
            if loja_id:
                q = q.filter(GoogleAdsConversionOutbox.loja_id == loja_id)
            rows = (
                q.order_by(GoogleAdsConversionOutbox.next_attempt_at.asc())
                .limit(limit)
                .all()
            )
            # snapshot ids + payload para processar fora do lock longo
            work = [
                {
                    "id": r.id,
                    "loja_id": r.loja_id,
                    "transaction_id": r.transaction_id,
                    "payload_json": r.payload_json,
                    "attempts": r.attempts,
                }
                for r in rows
            ]

        sent = 0
        for item in work:
            if self._process_one(item, now=now):
                sent += 1
        return sent

    def _process_one(self, item: dict[str, Any], *, now: datetime) -> bool:
        loja_id = item["loja_id"]
        payload = json.loads(item["payload_json"])
        try:
            with self._session_factory() as db:
                from app.control.stores import store_blocks_traffic_jobs

                # Loja suspensa/encerrada: não envia e não apaga a fila.
                if store_blocks_traffic_jobs(db, loja_id=loja_id):
                    return False
                connection = (
                    db.query(GoogleAdsConnection)
                    .filter(GoogleAdsConnection.loja_id == loja_id)
                    .first()
                )
                if (
                    connection is None
                    or connection.status != CONNECTION_STATUS_CONNECTED
                    or not connection.refresh_token_ciphertext
                ):
                    raise RuntimeError("conexão Google Ads indisponível")
                refresh_token = decifrar(connection.refresh_token_ciphertext)
                customer_id = (
                    payload.get("customer_id")
                    or connection.customer_id
                    or ""
                )
                if not customer_id:
                    raise RuntimeError("customer_id ausente no payload/conexão")

            event = payload.get("event") or payload
            clean_event = {
                k: v
                for k, v in event.items()
                if k
                not in {
                    "customer_id",
                    "event_type",
                    "conversion_action_resource_name",
                }
            }
            if "transaction_id" not in clean_event:
                clean_event["transaction_id"] = item["transaction_id"]

            result = self._data_manager_port.ingest(
                refresh_token=refresh_token,
                customer_id=customer_id,
                events=[clean_event],
            )

            with self._session_factory() as db:
                row = (
                    db.query(GoogleAdsConversionOutbox)
                    .filter(GoogleAdsConversionOutbox.id == item["id"])
                    .one()
                )
                attempt_n = int(row.attempts) + 1
                row.attempts = attempt_n
                row.request_id = result.request_id
                row.updated_at = now
                if result.rejected and not result.accepted:
                    row.status = OUTBOX_FAILED
                    row.last_error = "ingest rejected"
                    row.next_attempt_at = now + _retry_delay(attempt_n)
                    attempt_status = ATTEMPT_REJECTED
                    error_code = "rejected"
                else:
                    row.status = OUTBOX_SENT
                    row.last_error = None
                    attempt_status = ATTEMPT_ACCEPTED
                    error_code = None
                db.add(
                    GoogleAdsUploadAttempt(
                        id=novo_id(),
                        outbox_id=row.id,
                        request_id=result.request_id,
                        attempt=attempt_n,
                        status=attempt_status,
                        error_code=error_code,
                        created_at=now,
                    )
                )
                db.commit()
                return row.status == OUTBOX_SENT

        except Exception as exc:
            logger.warning(
                "google_ads process_outbox falhou id=%s: %s",
                item["id"],
                exc,
            )
            with self._session_factory() as db:
                row = (
                    db.query(GoogleAdsConversionOutbox)
                    .filter(GoogleAdsConversionOutbox.id == item["id"])
                    .first()
                )
                if row is None:
                    return False
                attempt_n = int(row.attempts) + 1
                row.attempts = attempt_n
                row.updated_at = now
                row.last_error = str(exc)[:500]
                if attempt_n >= self._max_attempts:
                    row.status = OUTBOX_DEAD
                else:
                    row.status = OUTBOX_FAILED
                    row.next_attempt_at = now + _retry_delay(attempt_n)
                db.add(
                    GoogleAdsUploadAttempt(
                        id=novo_id(),
                        outbox_id=row.id,
                        request_id=None,
                        attempt=attempt_n,
                        status=ATTEMPT_ERROR,
                        error_code="exception",
                        created_at=now,
                    )
                )
                db.commit()
            return False


def _build_event_payload(
    *,
    transaction_id: str,
    conversion_action: str,
    conversion_time: datetime,
    gclid: str | None,
    gbraid: str | None,
    wbraid: str | None,
    value: Decimal | float | str | None,
    currency: str,
    consent: bool,
    email: str | None,
    phone: str | None,
    customer_id: str,
    event_type: str,
) -> dict[str, Any]:
    ad_identifiers: dict[str, str] = {}
    if gclid:
        ad_identifiers["gclid"] = gclid
    if gbraid:
        ad_identifiers["gbraid"] = gbraid
    if wbraid:
        ad_identifiers["wbraid"] = wbraid

    event: dict[str, Any] = {
        "transaction_id": transaction_id,
        "event_source": "OTHER",
        "event_timestamp": conversion_time.isoformat(),
        "conversion_action": conversion_action,
        "ad_identifiers": ad_identifiers,
        "currency": (currency or "BRL").upper(),
    }
    if value is not None:
        event["conversion_value"] = str(Decimal(str(value)))

    # Sem consentimento: não envia user data enhanced (email/phone hashes).
    if consent:
        user_data: dict[str, str] = {}
        if email and email.strip():
            user_data["email_hash"] = hash_user_value(email)
        if phone and phone.strip():
            user_data["phone_hash"] = hash_user_value(phone)
        if user_data:
            event["user_data"] = user_data
        event["consent"] = {"ad_user_data": "GRANTED"}
    else:
        event["consent"] = {"ad_user_data": "DENIED"}

    return {
        "customer_id": customer_id,
        "event_type": event_type,
        "conversion_action_resource_name": conversion_action,
        "event": event,
    }



def _binding_view(row: GoogleAdsConversionBinding) -> ConversionBindingView:
    return ConversionBindingView(
        id=row.id,
        loja_id=row.loja_id,
        revy_event_type=row.revy_event_type,
        conversion_action_resource_name=row.conversion_action_resource_name,
        customer_id=row.customer_id,
        active=bool(row.active),
    )


def _outbox_view(row: GoogleAdsConversionOutbox) -> ConversionOutboxView:
    return ConversionOutboxView(
        id=row.id,
        loja_id=row.loja_id,
        domain_event_id=row.domain_event_id,
        event_type=row.event_type,
        transaction_id=row.transaction_id,
        status=row.status,
        request_id=row.request_id,
        attempts=int(row.attempts or 0),
    )


def _retry_delay(attempt: int) -> timedelta:
    # backoff linear simples (lean): 5m * attempt
    n = max(1, int(attempt))
    return RETRY_BASE * n
