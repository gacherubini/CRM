"""Os três gatilhos de handoff do Modo 2 (spec §5.2 e §5.11)."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.cloud_canal import phone_number_id_da_loja
from app.models_db import OfertaLead
from app.oferta_envio import enviar_oferta
from app.rodizio import abrir_oferta

logger = logging.getLogger("chatbot.handoff_gatilhos")

MOTIVOS = frozenset({"simulacao_pronta", "simulacao_falhou", "pediu_humano"})


def disparar_handoff(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    motivo: str,
    outbound,
    avisar_cliente: bool = True,
) -> str:
    """O que vier primeiro dispara; os seguintes não duplicam a oferta.

    ``simulacao_falhou`` existe para o lead não ficar parado esperando um
    resultado que não vem (spec §5.11): o vendedor simula à mão.

    ``avisar_cliente=False`` cala o texto ao cliente porque quem chamou já vai
    falar por conta própria. É o caso do agente do Modo 2: a tool
    ``solicitar_handoff`` devolve a frase para ELE dizer, então com os dois
    falando o cliente ouve a mesma coisa duas vezes (aconteceu em 24/08, 00:06).
    O lead é ofertado igual — o que muda é só quem fala.
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

    numero_central = phone_number_id_da_loja(db, loja_id)

    oferta = abrir_oferta(db, loja_id, telefone_cliente)
    if oferta is None:
        # Fila vazia ou esgotada: o cliente não pode ficar no vácuo (spec §5.3).
        if avisar_cliente:
            outbound.send_text(
                instance=numero_central,
                number=telefone_cliente,
                text="Já estou passando seu atendimento para um vendedor. Ele te chama em instantes.",
            )
        return "aguardando"

    try:
        enviar_oferta(db, oferta, outbound=outbound)
    except Exception:  # noqa: BLE001
        # A oferta já está aberta (abrir_oferta commita): o vendedor vê no CRM
        # e o job retoma o envio na reoferta. Derrubar aqui virava 500 com a
        # solicitação aceita — o cliente ouvia "não consegui registrar" para
        # uma simulação registrada (smoke e2e de 18/09, template ainda PENDING).
        # Nem telefone nem nome no log: os ids bastam para achar a linha.
        logger.exception(
            "falha ao enviar oferta loja_sufixo=%s oferta=%s",
            loja_id[-8:],
            oferta.id,
        )
    if avisar_cliente:
        outbound.send_text(
            instance=numero_central,
            number=telefone_cliente,
            text="Já estou chamando um vendedor para falar com você.",
        )
    return "ofertado"
