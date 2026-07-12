"""Dispatcher da outbox: entrega os ``EventoSaida`` pendentes ao webhook de cada loja.

Cada entrega leva assinatura HMAC-SHA256 do corpo, um ``X-Entrega-Id`` (delivery/idempotency id)
e é registrada em ``EntregaEvento``. Falhas reagendam com backoff exponencial até ``MAX_TENTATIVAS``,
quando o evento é descartado. O transporte HTTP é injetado (``poster``) para permitir testes.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.cripto import decifrar
from app.models_db import EntregaEvento, EventoSaida, WebhookDestino

MAX_TENTATIVAS = 5
BACKOFF_BASE_SEG = 30
BACKOFF_MAX_SEG = 3600

# poster(url, corpo_bytes, headers) -> (status_http | None, erro | None)
Poster = Callable[[str, bytes, dict], tuple[Optional[int], Optional[str]]]


def assinar(segredo: str, corpo: bytes) -> str:
    """Assinatura ``sha256=<hexdigest>`` do corpo, no estilo webhook do GitHub."""
    digest = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def assinatura_valida(segredo: str, corpo: bytes, assinatura: str) -> bool:
    return hmac.compare_digest(assinar(segredo, corpo), assinatura or "")


def _backoff(tentativas: int) -> timedelta:
    """Backoff exponencial a partir do número de falhas acumuladas (1, 2, 3...)."""
    segundos = BACKOFF_BASE_SEG * (2 ** max(tentativas - 1, 0))
    return timedelta(seconds=min(segundos, BACKOFF_MAX_SEG))


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _corpo(evento: EventoSaida) -> bytes:
    return json.dumps(
        evento.payload, sort_keys=True, ensure_ascii=False, default=str
    ).encode("utf-8")


def _pendentes_prontos(db: Session, agora: datetime, limite: int) -> list[EventoSaida]:
    candidatos = (
        db.query(EventoSaida)
        .filter(EventoSaida.status == "pendente")
        .order_by(EventoSaida.criada_em.asc())
        .limit(limite * 4)
        .all()
    )
    prontos = [
        e for e in candidatos
        if e.proxima_tentativa_em is None or _aware(e.proxima_tentativa_em) <= agora
    ]
    return prontos[:limite]


def _destino(db: Session, loja_id: str) -> Optional[WebhookDestino]:
    destino = db.get(WebhookDestino, loja_id)
    return destino if destino and destino.ativo else None


def processar_pendentes(
    db: Session,
    poster: Poster,
    *,
    agora: Optional[datetime] = None,
    max_tentativas: int = MAX_TENTATIVAS,
    limite: int = 100,
) -> dict:
    """Processa um lote de eventos pendentes. Retorna um resumo por resultado."""
    agora = agora or datetime.now(timezone.utc)
    resumo = {"entregues": 0, "reagendados": 0, "descartados": 0, "sem_destino": 0}

    for evento in _pendentes_prontos(db, agora, limite):
        destino = _destino(db, evento.loja_id)
        if destino is None:
            # Sem destino configurado: não conta como falha; espera configuração.
            resumo["sem_destino"] += 1
            continue

        segredo = decifrar(destino.segredo_cifrado)
        corpo = _corpo(evento)
        entrega_id = str(uuid.uuid4())
        headers = {
            "Content-Type": "application/json",
            "X-Evento-Id": evento.id,
            "X-Evento-Tipo": evento.tipo,
            "X-Entrega-Id": entrega_id,
            "X-Assinatura": assinar(segredo, corpo),
        }

        try:
            status_http, erro = poster(destino.url, corpo, headers)
        except Exception as exc:  # transporte pode levantar (timeout, conexão)
            status_http, erro = None, f"{type(exc).__name__}: {exc}"

        sucesso = status_http is not None and 200 <= status_http < 300
        db.add(
            EntregaEvento(
                id=entrega_id,
                evento_id=evento.id,
                loja_id=evento.loja_id,
                destino_url=destino.url,
                tentativa=evento.tentativas + 1,
                status_http=status_http,
                sucesso=sucesso,
                erro=None if sucesso else (erro or f"HTTP {status_http}"),
            )
        )

        if sucesso:
            evento.status = "entregue"
            evento.processada_em = agora
            evento.proxima_tentativa_em = None
            resumo["entregues"] += 1
        else:
            evento.tentativas += 1
            if evento.tentativas >= max_tentativas:
                evento.status = "descartado"
                evento.proxima_tentativa_em = None
                resumo["descartados"] += 1
            else:
                evento.proxima_tentativa_em = agora + _backoff(evento.tentativas)
                resumo["reagendados"] += 1

    db.commit()
    return resumo


def poster_httpx(timeout: float = 10.0) -> Poster:
    """Poster real baseado em httpx, usado pelo worker."""
    import httpx

    def _poster(url: str, corpo: bytes, headers: dict) -> tuple[Optional[int], Optional[str]]:
        try:
            resposta = httpx.post(url, content=corpo, headers=headers, timeout=timeout)
            return resposta.status_code, None
        except httpx.HTTPError as exc:
            return None, f"{type(exc).__name__}: {exc}"

    return _poster
