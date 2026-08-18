"""Cliente que volta a escrever depois da trava (spec §5.4).

Não é exceção: a central é o número do anúncio, e o cliente não sabe que o
atendimento mudou de número — ainda mais enquanto o vendedor não ligou.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.cloud_canal import phone_number_id_da_loja
from app.models_db import FilaVendedor, OfertaLead
from app.oferta_envio import janela_aberta

INTERVALO_AVISO_CLIENTE = timedelta(hours=6)

# A spec (§5.4) permite cutucar o vendedor 1x/hora. Na prática o cutucão sai
# junto do aviso ao cliente, então já é no máximo 1x/6h — dentro do teto e
# mais conservador. Não existe constante de 1 h porque não existe throttle
# separado: se um dia o aviso ao cliente e o cutucão se descolarem, aí sim.

# Último aviso por lead, em memória do processo: perder isso num restart
# custa um aviso repetido, não um erro. Persistir exigiria tabela nova para
# uma janela de 6 h.
_ultimo_aviso: dict[tuple[str, str], datetime] = {}


def cliente_voltou_a_escrever(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    outbound,
    agora: datetime | None = None,
) -> str:
    agora = agora or datetime.now(timezone.utc)
    travada = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_id,
            OfertaLead.telefone_cliente == telefone_cliente,
            OfertaLead.estado == "travada",
        )
        .first()
    )
    if travada is None:
        return "silencio"

    chave = (loja_id, telefone_cliente)
    anterior = _ultimo_aviso.get(chave)
    if anterior is not None and agora - anterior < INTERVALO_AVISO_CLIENTE:
        return "silencio"

    vendedor = db.get(FilaVendedor, travada.vendedor_id)
    numero_central = phone_number_id_da_loja(db, loja_id)
    outbound.send_text(
        instance=numero_central,
        number=telefone_cliente,
        text=(
            f"O {vendedor.nome} já está com seu atendimento e vai te chamar "
            f"do número {vendedor.telefone}."
        ),
    )
    _ultimo_aviso[chave] = agora

    # Cutucão ao vendedor SÓ se a janela dele estiver aberta: re-notificação
    # nunca gasta template pago (spec §5.4).
    if janela_aberta(db, loja_id, vendedor.telefone, agora=agora):
        outbound.send_text(
            instance=numero_central,
            number=vendedor.telefone,
            text="O cliente voltou a escrever na central. Ele está esperando seu contato.",
        )
    return "avisou_cliente"
