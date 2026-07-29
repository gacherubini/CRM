"""Outbox transacional de snapshots de venda para o Revy Trafego."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.clients.revy_trafego import RevyTrafegoClient
from app.cripto import cifrar, decifrar
from app.models import RevyTrafegoEventOutbox, agora, novo_id

logger = logging.getLogger(__name__)
OUTBOX_LEASE_SECONDS = 300


def _iso(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat()


def _snapshot_base(venda) -> dict:
    return {
        "venda_id": str(venda.id),
        "lead_ref": venda.lead_ref,
        "valor": str(venda.preco_venda),
        "moeda": "BRL",
        "status": venda.status,
        "criada_em": _iso(venda.criada_em),
        "confirmada_em": _iso(venda.confirmada_em),
        "atualizada_em": _iso(venda.atualizada_em),
        "custo_veiculo": (
            str(venda.custo_veiculo) if venda.custo_veiculo is not None else None
        ),
        "custos_diretos_total": str(
            sum((c.valor for c in venda.custos_diretos), Decimal("0"))
        ),
        "campanha_id_first": venda.campanha_id_first,
        "campanha_id_last": venda.campanha_id_last,
        "utm_campaign_first": venda.utm_campaign_first,
        "utm_campaign_last": venda.utm_campaign_last,
    }


def _enfileirar(
    db: Session,
    *,
    venda,
    event_id: str,
    event_type: str,
    payload: dict,
) -> RevyTrafegoEventOutbox:
    existente = (
        db.query(RevyTrafegoEventOutbox)
        .filter(RevyTrafegoEventOutbox.event_id == event_id)
        .first()
    )
    if existente is not None:
        return existente
    item = RevyTrafegoEventOutbox(
        id=novo_id(),
        loja_slug=venda.loja_slug,
        venda_id=venda.id,
        event_id=event_id,
        event_type=event_type,
        payload_ciphertext=cifrar(
            json.dumps(payload, ensure_ascii=False, sort_keys=True)
        ),
        status="pending",
        attempts=0,
        criada_em=agora(),
        atualizada_em=agora(),
    )
    db.add(item)
    db.flush()
    return item


def enfileirar_venda_confirmada(
    db: Session,
    venda,
    purchase,
) -> RevyTrafegoEventOutbox:
    payload = _snapshot_base(venda)
    payload.update(
        {
            "event_id": purchase.event_id,
            "cliente_telefone": purchase.phone,
            "cliente_email": purchase.email,
            "fbclid": purchase.fbclid,
            "fbc": purchase.fbc,
            # Click IDs Google: opacos; payload já vai cifrado no outbox.
            "gclid": purchase.gclid,
            "gbraid": purchase.gbraid,
            "wbraid": purchase.wbraid,
            "ctwa_clid": purchase.ctwa_clid,
        }
    )
    return _enfileirar(
        db,
        venda=venda,
        event_id=f"revy:{venda.loja_slug}:venda:{venda.id}:confirmada",
        event_type="venda_confirmada",
        payload=payload,
    )


def enfileirar_venda_atualizada(db: Session, venda) -> RevyTrafegoEventOutbox:
    versao = _iso(venda.atualizada_em) or "sem-versao"
    return _enfileirar(
        db,
        venda=venda,
        event_id=(
            f"revy:{venda.loja_slug}:venda:{venda.id}:{venda.status}:{versao}"
        ),
        event_type="venda_atualizada",
        payload=_snapshot_base(venda),
    )


def tentar_entregar(
    db: Session,
    item: RevyTrafegoEventOutbox,
    *,
    client: RevyTrafegoClient | None = None,
) -> bool:
    """Tenta uma entrega e persiste o resultado; nunca propaga falha externa."""
    destino = client or RevyTrafegoClient()
    try:
        payload = json.loads(decifrar(item.payload_ciphertext))
        if item.event_type == "venda_confirmada":
            resposta = destino.notificar_venda_confirmada(
                loja_slug=item.loja_slug,
                payload=payload,
            )
        else:
            resposta = destino.notificar_venda_atualizada(
                loja_slug=item.loja_slug,
                payload=payload,
            )
        item.attempts = int(item.attempts or 0) + 1
        item.atualizada_em = agora()
        if resposta is None:
            item.status = "failed"
            item.last_error = "Revy Trafego indisponivel"
            db.commit()
            return False
        item.status = "delivered"
        item.last_error = None
        item.delivered_at = agora()
        db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "revy_trafego_outbox: entrega falhou event_id=%s tipo=%s",
            item.event_id,
            type(exc).__name__,
        )
        try:
            item.attempts = int(item.attempts or 0) + 1
            item.status = "failed"
            item.last_error = "Falha interna ao entregar evento"
            item.atualizada_em = agora()
            db.commit()
        except Exception:
            db.rollback()
        return False


def _em_utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def _reivindicar(
    db: Session,
    item: RevyTrafegoEventOutbox,
    *,
    instante: datetime,
) -> RevyTrafegoEventOutbox | None:
    """CAS portátil: somente um worker transforma o item em processing."""
    status_anterior = item.status
    query = db.query(RevyTrafegoEventOutbox).filter(
        RevyTrafegoEventOutbox.id == item.id,
        RevyTrafegoEventOutbox.status == status_anterior,
    )
    if item.atualizada_em is not None:
        query = query.filter(
            RevyTrafegoEventOutbox.atualizada_em == item.atualizada_em
        )
    alteradas = query.update(
        {"status": "processing", "atualizada_em": instante},
        synchronize_session=False,
    )
    db.commit()
    if alteradas != 1:
        db.expire_all()
        return None
    return db.get(RevyTrafegoEventOutbox, item.id)


def processar_pendentes(
    db_factory: Callable[[], Session],
    *,
    limite: int = 100,
    backoff_base_seconds: float = 60,
    retencao_dias: int = 30,
    lease_seconds: int = OUTBOX_LEASE_SECONDS,
) -> dict[str, int]:
    db = db_factory()
    try:
        instante = datetime.now(timezone.utc)
        corte = instante - timedelta(days=max(1, retencao_dias))
        expurgados = (
            db.query(RevyTrafegoEventOutbox)
            .filter(
                RevyTrafegoEventOutbox.status == "delivered",
                RevyTrafegoEventOutbox.delivered_at < corte,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        candidatos = (
            db.query(RevyTrafegoEventOutbox)
            .filter(
                RevyTrafegoEventOutbox.status.in_(
                    ("pending", "failed", "processing")
                ),
            )
            .order_by(RevyTrafegoEventOutbox.criada_em.asc())
            .limit(500)
            .all()
        )
        processados = 0
        entregues = 0
        falharam = 0
        aguardando = 0
        aguardando_lease = 0
        concorrentes = 0
        for item in candidatos:
            if processados >= max(1, min(limite, 500)):
                break
            if item.status == "processing" and item.atualizada_em is not None:
                expira_em = _em_utc(item.atualizada_em) + timedelta(
                    seconds=max(1, lease_seconds)
                )
                if expira_em > instante:
                    aguardando_lease += 1
                    continue
            if item.status == "failed" and item.atualizada_em is not None:
                atualizado = _em_utc(item.atualizada_em)
                atraso = min(
                    max(1.0, backoff_base_seconds)
                    * (2 ** max(int(item.attempts or 0) - 1, 0)),
                    3600.0,
                )
                if atualizado + timedelta(seconds=atraso) > instante:
                    aguardando += 1
                    continue
            reivindicado = _reivindicar(db, item, instante=instante)
            if reivindicado is None:
                concorrentes += 1
                continue
            processados += 1
            if tentar_entregar(db, reivindicado):
                entregues += 1
            else:
                falharam += 1
        return {
            "encontrados": len(candidatos),
            "processados": processados,
            "entregues": entregues,
            "falharam": falharam,
            "aguardando_backoff": aguardando,
            "aguardando_lease": aguardando_lease,
            "concorrentes": concorrentes,
            "expurgados": expurgados,
        }
    finally:
        db.close()
