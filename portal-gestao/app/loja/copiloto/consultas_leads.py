"""Leads e atendimento, do ponto de vista do dono.

As métricas de funil vêm de ``SalesOverview.funil`` (``sales_overview.py:929-945``)
— NÃO de ``ChatbotClient.resumo_atendimento()``, que devolve outra coisa
(``chatbot-api/app/servico.py:1512-1518``).

"Sem resposta" tem uma definição só, e ela é honesta: conversa em handoff
(bot desligado, humano é o responsável) cuja última mensagem é do cliente e
passou do limiar de horas. Bot ligado = bot respondendo, não é abandono.

§I5 — escopo de loja do ``sem_resposta``: ``ChatbotClient.listar_conversas``
(``app/clients/chatbot.py``) não tem NENHUM parâmetro de loja — só
``busca``/``limit``/``offset``/``canal_id``. ``canal_id`` escopa por canal de
WhatsApp, não por loja (e o Portal não guarda localmente quais canais são de
qual loja para montar essa lista). O chatbot-api também não expõe um
endpoint de identidade equivalente a ``EstoqueClient.obter_loja()`` — ver
``consultas_estoque.garantir_escopo_loja``, o padrão da casa para este
problema. A loja que ``/v1/conversas`` devolve é 100% implícita na credencial
(``settings.chatbot_token``), que é global ao processo Portal
(``app/main.py``), exatamente como o ``EstoqueClient``.

Sem hook de escopo nem endpoint de identidade, não há como CONFIRMAR a loja
por chamada. O guard aqui é o equivalente possível: ``settings.chatbot_loja_slug``
é uma declaração manual e opt-in de qual loja aquela credencial atende. Vazio
(hoje, deploy de uma loja só) preserva o comportamento atual — nada muda.
Quando declarado e divergente da sessão, degrada em vez de arriscar devolver
a contagem de outra loja.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.clients.chatbot import ChatbotIndisponivel
from app.config import settings
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


def escopo_chatbot_confiavel(ctx: CopilotoContexto, *, loja_declarada: str | None = None) -> bool:
    """``True`` se é seguro tratar o que ``ChatbotClient`` devolve como desta loja.

    Não existe verificação ao vivo possível (ver docstring do módulo), então
    isto compara a sessão contra uma declaração de config
    (``settings.chatbot_loja_slug``/``CHATBOT_API_LOJA_SLUG``). Sem
    declaração, confia — é o comportamento de hoje, deploy de uma loja só.
    Com declaração, só confia se bater com ``ctx.loja_slug``.
    """
    declarada = loja_declarada if loja_declarada is not None else settings.chatbot_loja_slug
    declarada = (declarada or "").strip().casefold()
    if not declarada:
        return True
    return declarada == (ctx.loja_slug or "").strip().casefold()


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
    chatbot_loja_slug: str | None = None,
) -> LeadsStatus:
    """Leads do período + quantos estão esperando gente há horas.

    ``chatbot_loja_slug``: injeta a declaração de escopo (I5) para teste sem
    mexer em ``settings`` (frozen). ``None`` (default de produção) lê de
    ``settings.chatbot_loja_slug`` — ver ``escopo_chatbot_confiavel``.
    """
    ref = agora or datetime.now(timezone.utc)
    funil = getattr(overview, "funil", None) or {}
    funil_status = getattr(overview, "funil_status", STATUS_INDISPONIVEL)

    total_leads = funil.get("total_leads")
    taxa = funil.get("taxa_resposta_pct")
    tempo = funil.get("tempo_mediano_primeira_resposta_segundos")

    declarado = (
        settings.chatbot_loja_slug if chatbot_loja_slug is None else chatbot_loja_slug
    )

    sem_resposta: int | None = None
    sem_resposta_status = STATUS_INDISPONIVEL
    if not escopo_chatbot_confiavel(ctx, loja_declarada=declarado):
        # I5: CHATBOT_API_LOJA_SLUG está declarado e diverge da sessão — a
        # credencial global aponta para outra loja. Nunca repassar a
        # contagem: degrada como qualquer outra fonte indisponível.
        logger.warning(
            "copiloto leads_status: CHATBOT_API_LOJA_SLUG=%s não bate com a "
            "loja da sessão (%s); degradando sem_resposta em vez de arriscar "
            "a contagem de outra loja",
            declarado,
            ctx.loja_slug,
        )
    else:
        try:
            conversas = chatbot.listar_conversas(limit=LIMITE_CONVERSAS)
            sem_resposta = contar_sem_resposta(
                conversas, agora=ref, horas=horas_sem_resposta
            )
            sem_resposta_status = STATUS_OK
        except ChatbotIndisponivel:
            pass
        except Exception:
            # Degrada igual ao caso esperado (nunca zero inventado), mas isto
            # NÃO é o sinal conhecido de "chatbot fora do ar": é bug real
            # (payload malformado, client sem o método) e precisa aparecer no
            # log.
            logger.warning(
                "copiloto leads_status: falha inesperada em "
                "chatbot.listar_conversas loja=%s",
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
