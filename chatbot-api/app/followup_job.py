"""Cutucão no silêncio do cliente (spec §5.9). Só Modo 2, só com bot_ativo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

PRIMEIRO_TOQUE = timedelta(minutes=30)
SEGUNDO_TOQUE = timedelta(hours=1)

# Texto por etapa, exatamente como fechado na spec §5.9. O bot NÃO inventa
# frase: classifica a etapa e escolhe o par. Sem certeza, cai em "so_oi".
_TEXTOS: dict[str, tuple[str, str]] = {
    "so_oi": (
        "e aí amigo, ainda tá aí? te ajudo a achar uma moto",
        "amigo, se ainda quiser dar uma olhada nas motos é só responder. fico por aqui",
    ),
    "anuncio": (
        "amigo, você queria essa moto à vista ou financiada? me fala que eu sigo",
        "ainda consigo te ajudar nessa moto do anúncio. me diz se é à vista ou financiamento",
    ),
    "vendo_opcoes": (
        "amigo, viu alguma que te interessou? me fala qual que eu te mostro melhor",
        "se alguma moto te pegou, me manda o modelo que eu continuo. senão a gente deixa quieto",
    ),
    "faltou_dado": (
        "amigo, pra eu simular falta só [o que falta]. me manda que eu já encaminho",
        "sem esses dados eu não consigo simular. se ainda quiser, me passa que eu resolvo agora",
    ),
    "catalogo": (
        "amigo, deu uma olhada no catálogo? me fala qual moto que eu te atendo nela",
        "se viu alguma, me manda o modelo. se não for a hora, tudo bem",
    ),
    "a_vista": (
        "amigo, ficou alguma dúvida no valor? te explico direto",
        "se ainda quiser fechar à vista me chama que eu sigo com você",
    ),
}


def texto_followup(etapa: str, toque: int) -> str:
    """Texto do toque 1 ou 2. Terceiro toque não existe — a spec para em dois."""
    if toque not in (1, 2):
        raise ValueError("só existem os toques 1 e 2 (spec §5.9)")
    par = _TEXTOS.get(etapa, _TEXTOS["so_oi"])
    return par[toque - 1]
