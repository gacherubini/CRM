"""Envio da oferta ao vendedor (spec §5.7): dois envelopes, um significado."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import config
from app.models_db import Conversa, FilaVendedor, Mensagem, OfertaLead
from app.operacao import variantes_telefone

JANELA_HORAS = 24


def janela_aberta(
    db: Session, loja_id: str, telefone_vendedor: str, *, agora: datetime | None = None
) -> bool:
    """Houve inbound daquele vendedor nas últimas 24 h?

    É o que decide template pago × interativa grátis. A cobrança é por
    **vendedor com janela fechada**, não por lead: o primeiro "peguei" do dia
    abre a janela e os leads seguintes daquele vendedor saem de graça.
    """
    limite = (agora or datetime.now(timezone.utc)) - timedelta(hours=JANELA_HORAS)
    # Match por variantes, não por igualdade de string: o `wa_id` da Meta vem
    # do aparelho do vendedor e no Brasil costuma chegar SEM o 9º dígito, ou
    # sem o DDI, enquanto `fila_vendedor.telefone` guarda o que o lojista
    # digitou. Comparando cru, a janela parece sempre fechada e o Revy paga
    # template em TODA oferta em vez de um por vendedor por dia (§5.7, §9).
    variantes = variantes_telefone(telefone_vendedor)
    if not variantes:
        return False
    # Mensagem não guarda telefone: ele mora em Conversa (`models_db.py:91`).
    # O join é obrigatório — não existe `Mensagem.telefone`.
    return (
        db.query(Mensagem)
        .join(Conversa, Mensagem.conversa_id == Conversa.id)
        .filter(
            Conversa.loja_id == loja_id,
            Conversa.telefone.in_(variantes),
            Mensagem.direcao == "entrada",
            Mensagem.criada_em >= limite,
        )
        .first()
        is not None
    )


def enviar_oferta(db: Session, oferta: OfertaLead, *, outbound) -> str:
    """Manda a oferta e devolve o envelope usado: ``template`` ou ``interativa``.

    Nada de ``wa.me`` nem telefone do cliente aqui: o contato só vai depois do
    clique (spec §5.7), senão o vendedor chama sem o backend saber.
    """
    vendedor = db.get(FilaVendedor, oferta.vendedor_id)
    resumo = f"Lead novo na loja. Toque em Peguei para assumir."

    if janela_aberta(db, oferta.loja_id, vendedor.telefone):
        outbound.send_interactive_button(
            instance=config.GRAPH_PHONE_NUMBER_ID,
            number=vendedor.telefone,
            texto=resumo,
            oferta_id=oferta.id,
        )
        return "interativa"

    outbound.send_template_button(
        instance=config.GRAPH_PHONE_NUMBER_ID,
        number=vendedor.telefone,
        template=config.GRAPH_TEMPLATE_OFERTA,
        variaveis=[vendedor.nome],
        oferta_id=oferta.id,
    )
    return "template"
