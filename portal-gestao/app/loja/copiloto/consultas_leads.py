"""Leads e atendimento, do ponto de vista do dono.

As métricas de funil vêm de ``SalesOverview.funil`` (``sales_overview.py:929-945``)
— NÃO de ``ChatbotClient.resumo_atendimento()``, que devolve outra coisa
(``chatbot-api/app/servico.py:1512-1518``).

"Sem resposta" tem uma definição só, e ela é honesta: conversa em handoff
(bot desligado, humano é o responsável) cuja última mensagem é do cliente e
passou do limiar de horas. Bot ligado = bot respondendo, não é abandono.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.clients.chatbot import ChatbotIndisponivel
from app.loja.copiloto.tipos import (
    STATUS_ERRO,
    STATUS_INDISPONIVEL,
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    CopilotoContexto,
)

logger = logging.getLogger(__name__)

LIMITE_CONVERSAS = 200


def _dt(valor: Any) -> datetime | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class LeadsStatus:
    status: str
    total_leads: int | None
    taxa_resposta_pct: str | None
    tempo_mediano_primeira_resposta_segundos: int | None
    sem_resposta: int | None
    sem_resposta_status: str
    horas_sem_resposta: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_leads": self.total_leads,
            "taxa_resposta_pct": self.taxa_resposta_pct,
            "tempo_mediano_primeira_resposta_segundos": (
                self.tempo_mediano_primeira_resposta_segundos
            ),
            "sem_resposta": self.sem_resposta,
            "sem_resposta_status": self.sem_resposta_status,
            "horas_sem_resposta": self.horas_sem_resposta,
        }


def contar_sem_resposta(
    conversas: list[dict],
    *,
    agora: datetime,
    horas: int,
) -> int:
    limite_segundos = horas * 3600
    total = 0
    for conversa in conversas or []:
        if conversa.get("bot_ativo") is not False:
            continue
        ultima = conversa.get("ultima_mensagem") or None
        if not isinstance(ultima, dict):
            continue
        if (ultima.get("direcao") or "").strip().casefold() != "entrada":
            continue
        criada = _dt(ultima.get("criada_em"))
        if criada is None:
            continue
        if (agora - criada).total_seconds() >= limite_segundos:
            total += 1
    return total


def leads_status(
    overview: Any,
    chatbot: Any,
    *,
    ctx: CopilotoContexto,
    agora: datetime | None = None,
    horas_sem_resposta: int = 4,
) -> LeadsStatus:
    """Leads do período + quantos estão esperando gente há horas."""
    ref = agora or datetime.now(timezone.utc)
    funil = getattr(overview, "funil", None) or {}
    funil_status = getattr(overview, "funil_status", STATUS_INDISPONIVEL)

    total_leads = funil.get("total_leads")
    taxa = funil.get("taxa_resposta_pct")
    tempo = funil.get("tempo_mediano_primeira_resposta_segundos")

    sem_resposta: int | None = None
    sem_resposta_status = STATUS_INDISPONIVEL
    try:
        conversas = chatbot.listar_conversas(limit=LIMITE_CONVERSAS)
        sem_resposta = contar_sem_resposta(
            conversas, agora=ref, horas=horas_sem_resposta
        )
        sem_resposta_status = STATUS_OK
    except ChatbotIndisponivel:
        pass
    except Exception:
        # Degrada igual ao caso esperado (nunca zero inventado), mas isto NÃO
        # é o sinal conhecido de "chatbot fora do ar": é bug real (payload
        # malformado, client sem o método) e precisa aparecer no log.
        logger.warning(
            "copiloto leads_status: falha inesperada em chatbot.listar_conversas "
            "loja=%s",
            ctx.loja_slug,
            exc_info=True,
        )

    if funil_status == STATUS_INDISPONIVEL and sem_resposta_status == STATUS_INDISPONIVEL:
        # As duas fontes fora do ar ao mesmo tempo: não há nada parcialmente
        # confiável para mostrar.
        status = STATUS_INDISPONIVEL
    elif funil_status == STATUS_ERRO and sem_resposta_status != STATUS_OK:
        status = STATUS_ERRO
    elif funil_status == STATUS_VAZIO and sem_resposta_status == STATUS_OK:
        # Funil genuinamente vazio (zero leads) com as duas fontes ok: vazio
        # não é degradação, é o mesmo vocabulário de estoque_parado/vendas_resumo.
        status = STATUS_VAZIO
    elif (
        funil_status in {STATUS_ERRO, STATUS_INDISPONIVEL, STATUS_PARCIAL}
        or sem_resposta is None
    ):
        # funil_status == "parcial" cai aqui: o período coberto pelo funil não
        # é o todo, e REGRAS[7] do system prompt instrui o modelo a avisar
        # quando um dado vier parcial — entregar STATUS_OK aqui faria um
        # modelo bem-comportado NÃO qualificar um número que devia vir com
        # ressalva.
        status = STATUS_PARCIAL
    else:
        status = STATUS_OK

    return LeadsStatus(
        status=status,
        total_leads=total_leads,
        taxa_resposta_pct=taxa,
        tempo_mediano_primeira_resposta_segundos=tempo,
        sem_resposta=sem_resposta,
        sem_resposta_status=sem_resposta_status,
        horas_sem_resposta=horas_sem_resposta,
    )
