"""Clique do vendedor volta como inbound e é comando de controle (spec §5.5, §5.7)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.cloud_canal import phone_number_id_da_loja
from app.models_db import FilaVendedor, OfertaLead
from app.rodizio import assumir_oferta

_PREFIXO = "pego:"


def extrair_oferta_id(payload: dict) -> str | None:
    """Lê o id da oferta do clique, template ou interativa.

    Payload ausente ou fora do formato devolve ``None`` — e o chamador trata
    como "já foi pego" em vez de adivinhar qual lead era (spec §5.7).
    """
    bruto = (
        (payload.get("button") or {}).get("payload")
        or ((payload.get("interactive") or {}).get("button_reply") or {}).get("id")
        or ""
    )
    bruto = str(bruto)
    if not bruto.startswith(_PREFIXO):
        return None
    return bruto[len(_PREFIXO):] or None


def processar_clique(
    db: Session,
    loja_id: str,
    telefone_remetente: str,
    oferta_id: str | None,
    *,
    outbound,
) -> str:
    """Trava o lead e entrega o pacote ao vencedor; avisa o perdedor."""
    if not oferta_id:
        return "desconhecida"

    ganhou, oferta = assumir_oferta(db, oferta_id)
    if oferta is None:
        return "desconhecida"

    numero_central = phone_number_id_da_loja(db, loja_id)

    if not ganhou:
        # Nada de contato aqui: quem perdeu não fala com o cliente.
        outbound.send_text(
            instance=numero_central,
            number=telefone_remetente,
            text="Esse lead já foi pego por outro vendedor.",
        )
        return "ja_foi_pego"

    vencedor = db.get(FilaVendedor, oferta.vendedor_id)
    outbound.send_text(
        instance=numero_central,
        number=vencedor.telefone,
        text=(
            f"Lead é seu. Chame o cliente: https://wa.me/{oferta.telefone_cliente}\n"
            f"Ficha completa no Portal."
        ),
    )
    return "travou"
