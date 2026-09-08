"""Modo de WhatsApp da loja: 1 XOR 2, escolhido no Control (spec §5.8).

A Loja **não** oferece o toggle — ela opera o modo que o Control gravou e que
chega aqui pela projeção operacional (`aggregate="whatsapp_modo"`, `state` "1"
ou "2"), a mesma tabela dos entitlements.

Fonte única: quem precisa saber o modo pergunta aqui. Ler a projeção na mão em
cada tela é como o menu e a rota passam a discordar.
"""
from __future__ import annotations

from typing import Any

# Baileys + grupo do estoque (legado). É o default: loja que o Control ainda não
# projetou continua no que sempre funcionou.
MODO_BAILEYS = 1
# Central Cloud API só-bot, com fila de vendedores. Sem QR, sem grupo.
MODO_CLOUD = 2

AGGREGATE = "whatsapp_modo"


def modo_da_loja(db: Any, loja_slug: str) -> int:
    """Modo projetado para a loja; ``MODO_BAILEYS`` quando não se sabe.

    Falta de projeção é ausência de informação, não Modo 2: cair no legado
    mantém a loja atendendo, e é o que o Control envia no próximo snapshot.
    """
    if db is None or not loja_slug:
        return MODO_BAILEYS
    from app.models import LojaOperacionalProjecao

    linha = db.get(LojaOperacionalProjecao, (loja_slug, AGGREGATE))
    if linha is None:
        return MODO_BAILEYS
    return MODO_CLOUD if str(linha.state).strip() == str(MODO_CLOUD) else MODO_BAILEYS
