"""Cutucão no silêncio do cliente (spec §5.9). Só Modo 2, só com bot_ativo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import config
from app.models_db import Conversa, Mensagem

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


def classificar_etapa(conversa: Conversa) -> str:
    """Em que ponto o cliente parou.

    Hoje devolve sempre ``so_oi``, que é o fallback que a própria spec manda
    usar quando não há certeza (§5.9) — a classificação rica depende do estado
    do intake, que ainda não existe. Fica isolada aqui para o intake plugar
    depois sem mexer no worker.
    """
    return "so_oi"


class FollowupWorker:
    """Varre conversas caladas e cutuca. Timer é nosso, não Wait do n8n (§5.3)."""

    def run_once(self, db: Session, *, outbound) -> dict[str, int]:
        from app.rodizio import loja_opera_modo2

        agora = datetime.now(timezone.utc)
        contagem = {"toques": 0, "zerados": 0}

        # Última mensagem de cada conversa, para saber quem falou por último
        # e há quanto tempo. Conversa sem mensagem nenhuma não entra.
        ultima = (
            db.query(
                Mensagem.conversa_id.label("conversa_id"),
                func.max(Mensagem.criada_em).label("quando"),
            )
            .group_by(Mensagem.conversa_id)
            .subquery()
        )
        linhas = (
            db.query(Conversa, Mensagem)
            .join(ultima, ultima.c.conversa_id == Conversa.id)
            .join(
                Mensagem,
                (Mensagem.conversa_id == Conversa.id)
                & (Mensagem.criada_em == ultima.c.quando),
            )
            .filter(Conversa.bot_ativo.is_(True))
            .all()
        )

        for conversa, mensagem in linhas:
            # Cliente respondeu: zera o relógio e não cutuca (§5.9 item 3).
            if mensagem.direcao == "entrada":
                if conversa.followup_toques:
                    conversa.followup_toques = 0
                    contagem["zerados"] += 1
                continue

            if not loja_opera_modo2(db, conversa.loja_id):
                continue
            if conversa.followup_toques >= 2:
                continue  # não existe terceiro toque

            silencio = agora - _aware(mensagem.criada_em)
            espera = PRIMEIRO_TOQUE if conversa.followup_toques == 0 else SEGUNDO_TOQUE
            if silencio < espera:
                continue

            toque = conversa.followup_toques + 1
            outbound.send_text(
                instance=config.GRAPH_PHONE_NUMBER_ID,
                number=conversa.telefone,
                text=texto_followup(classificar_etapa(conversa), toque),
            )
            conversa.followup_toques = toque
            contagem["toques"] += 1

        db.commit()
        return contagem


def _aware(momento: datetime) -> datetime:
    """SQLite devolve datetime ingênuo; comparar com aware levanta TypeError."""
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)
