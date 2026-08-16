"""Os três gatilhos de handoff do Modo 2 (spec §5.2 e §5.11)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import config
from app.models_db import OfertaLead
from app.oferta_envio import enviar_oferta
from app.rodizio import abrir_oferta

MOTIVOS = frozenset({"simulacao_pronta", "simulacao_falhou", "pediu_humano"})


def disparar_handoff(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    motivo: str,
    outbound,
) -> str:
    """O que vier primeiro dispara; os seguintes não duplicam a oferta.

    ``simulacao_falhou`` existe para o lead não ficar parado esperando um
    resultado que não vem (spec §5.11): o vendedor simula à mão.
    """
    if motivo not in MOTIVOS:
        raise ValueError(f"motivo desconhecido: {motivo}")

    em_andamento = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_id,
            OfertaLead.telefone_cliente == telefone_cliente,
            OfertaLead.estado.in_(("aberta", "travada")),
        )
        .first()
    )
    if em_andamento is not None:
        return "ja_em_andamento"

    oferta = abrir_oferta(db, loja_id, telefone_cliente)
    if oferta is None:
        # Fila vazia ou esgotada: o cliente não pode ficar no vácuo (spec §5.3).
        outbound.send_text(
            instance=config.GRAPH_PHONE_NUMBER_ID,
            number=telefone_cliente,
            text="Já estou passando seu atendimento para um vendedor. Ele te chama em instantes.",
        )
        return "aguardando"

    enviar_oferta(db, oferta, outbound=outbound)
    outbound.send_text(
        instance=config.GRAPH_PHONE_NUMBER_ID,
        number=telefone_cliente,
        text="Já estou chamando um vendedor para falar com você.",
    )
    return "ofertado"
