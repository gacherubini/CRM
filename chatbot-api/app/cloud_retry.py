"""Reprocesso do inbound da Cloud API (spec §6.1).

A §6.1 pede: responder ``200`` **imediatamente** para a Meta não reentregar, e
**processar depois**. Responder rápido já era feito; "depois" não existia — a
exceção virava uma linha de log e o lead morria ali, sem ninguém saber.

Isto é a segunda metade: o corpo cru fica guardado e um worker tenta de novo,
com teto de tentativas para um evento defeituoso não girar para sempre.

Por que reprocessar o corpo cru e não o evento parseado: é dele que o parse sai
de novo (se o bug estava no parse, a correção pega os eventos antigos), e é
sobre esses mesmos bytes que a assinatura da Meta já foi conferida — não há
revalidação a fazer nem segredo a guardar aqui.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.meta_webhook import parse_inbound
from app.models_db import CloudEventoFalho

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 5


def registrar_evento_falho(
    db: Session,
    *,
    wamid: str,
    phone_number_id: str | None,
    corpo_cru: bytes | str,
) -> CloudEventoFalho | None:
    """Guarda o evento que estourou. Idempotente por ``wamid``.

    Sem ``wamid`` não dá para reprocessar só o evento certo (o corpo pode trazer
    vários) nem deduplicar — então não guarda: o log já registrou.
    """
    if not wamid:
        return None

    texto = corpo_cru.decode("utf-8") if isinstance(corpo_cru, bytes) else corpo_cru

    existente = (
        db.query(CloudEventoFalho).filter(CloudEventoFalho.wamid == wamid).first()
    )
    if existente is not None:
        return existente

    linha = CloudEventoFalho(
        id=str(uuid.uuid4()),
        wamid=wamid,
        phone_number_id=phone_number_id or None,
        corpo_cru=texto,
        estado="pendente",
        tentativas=0,
    )
    db.add(linha)
    db.flush()
    return linha


def reprocessar_pendentes(db: Session, *, limite: int = 20) -> int:
    """Tenta de novo os eventos pendentes. Devolve quantos processaram.

    Ignora o dedup por ``wamid`` de propósito: o webhook marca o wamid como
    visto **antes** de processar (protege contra a rajada de reentrega da Meta),
    então um reprocesso passaria batido pelo dedup e nunca rodaria. Aqui o
    reprocesso é explícito, de um evento que sabidamente não completou.
    """
    from app.main import processar_evento_cloud

    linhas = (
        db.query(CloudEventoFalho)
        .filter(
            CloudEventoFalho.estado == "pendente",
            CloudEventoFalho.tentativas < MAX_TENTATIVAS,
        )
        .order_by(CloudEventoFalho.criado_em.asc())
        .limit(limite)
        .all()
    )

    processados = 0
    for linha in linhas:
        linha.tentativas += 1
        try:
            payload = json.loads(linha.corpo_cru)
        except ValueError as exc:
            # Corpo ilegível não melhora com nova tentativa.
            linha.estado = "desistiu"
            linha.ultimo_erro = f"corpo inválido: {exc}"
            continue

        alvo = [e for e in parse_inbound(payload) if e.wamid == linha.wamid]
        if not alvo:
            linha.estado = "desistiu"
            linha.ultimo_erro = "wamid não encontrado no corpo guardado"
            continue

        # A contagem é gravada ANTES da tentativa: se o processamento estourar,
        # o rollback que limpa a transação suja não pode zerar o contador — era
        # assim que um evento defeituoso giraria para sempre.
        tentativa_atual = linha.tentativas
        db.commit()

        try:
            for evento in alvo:
                processar_evento_cloud(db, evento)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            erro = f"{type(exc).__name__}: {exc}"[:2000]
            linha = db.get(CloudEventoFalho, linha.id)
            if linha is None:
                continue
            linha.ultimo_erro = erro
            if tentativa_atual >= MAX_TENTATIVAS:
                linha.estado = "desistiu"
                logger.error(
                    "evento cloud desistiu apos %s tentativas wamid=%s",
                    tentativa_atual,
                    linha.wamid,
                )
            db.commit()
            continue

        linha.estado = "processado"
        linha.ultimo_erro = None
        db.commit()
        processados += 1

    return processados


class CloudRetryWorker:
    """Adaptador para o ``_Periodico`` do ``modo2_workers``."""

    def run_once(self, db: Session) -> int:
        return reprocessar_pendentes(db)
