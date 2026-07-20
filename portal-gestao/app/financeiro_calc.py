"""Cálculos financeiros compartilhados entre o dashboard (/app/financeiro) e
os relatórios exportáveis (/app/relatorios). Mantido em módulo próprio, sem
depender de app.main, para que ambos consumidores usem exatamente a mesma
matemática — evitando divergência entre o painel e os CSVs exportados.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AtendimentoAtribuicao, Meta, Venda

CENTAVOS = Decimal("0.01")
FUSO_PORTAL = ZoneInfo(settings.timezone)


def dinheiro(texto) -> Decimal:
    return Decimal(str(texto).replace(",", ".")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _data(momento):
    if not isinstance(momento, datetime):
        return momento
    # SQLite devolve DateTime sem tzinfo mesmo quando a coluna foi declarada com
    # timezone=True. Os timestamps persistidos pelo Portal são UTC.
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_PORTAL).date()


def hoje_portal() -> date:
    return datetime.now(timezone.utc).astimezone(FUSO_PORTAL).date()


def ultimo_dia_mes(dia: date) -> date:
    return date(dia.year, dia.month, calendar.monthrange(dia.year, dia.month)[1])


def periodo_padrao(inicio: str | None, fim: str | None) -> tuple[date, date]:
    hoje = hoje_portal()
    try:
        d_inicio = date.fromisoformat(inicio) if inicio else hoje.replace(day=1)
    except ValueError:
        d_inicio = hoje.replace(day=1)
    try:
        d_fim = date.fromisoformat(fim) if fim else ultimo_dia_mes(hoje)
    except ValueError:
        d_fim = ultimo_dia_mes(hoje)
    return d_inicio, d_fim


def data_api(valor) -> date | None:
    if not valor:
        return None
    try:
        texto = str(valor).replace("Z", "+00:00")
        if len(texto) == 10:
            return date.fromisoformat(texto)
        momento = datetime.fromisoformat(texto)
        return _data(momento) if momento.tzinfo is not None else momento.date()
    except (TypeError, ValueError):
        return None


def origem_lead(lead: dict) -> str | None:
    origem = lead.get("origem")
    return str(origem).strip() if origem and str(origem).strip() else None


def lead_corresponde_origem(lead: dict, origem: str | None) -> bool:
    if not origem:
        return True
    atual = origem_lead(lead)
    if origem == "__sem_origem__":
        return atual is None
    return bool(atual and atual.casefold() == origem.casefold())


def lead_utm_campaign(lead: dict) -> str | None:
    valor = lead.get("utm_campaign_last") or lead.get("utm_campaign")
    return str(valor).strip() if valor and str(valor).strip() else None


def lead_corresponde_utm_campaign(lead: dict, utm_campaign: str | None) -> bool:
    if not utm_campaign:
        return True
    atual = lead_utm_campaign(lead)
    if utm_campaign == "__sem_campanha__":
        return atual is None
    return bool(atual and atual.casefold() == utm_campaign.casefold())


def identidade_telefone(telefone: str | None) -> str | None:
    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    if not digitos:
        return None
    mensagem = f"portal-handoff:v1:{digitos}".encode()
    return hmac.new(settings.identity_hmac_secret.encode(), mensagem, hashlib.sha256).hexdigest()


def atribuicoes_no_periodo(
    db: Session,
    loja_slug: str,
    inicio: date,
    fim: date,
    vendedor_email: str | None = None,
) -> list[AtendimentoAtribuicao]:
    consulta = db.query(AtendimentoAtribuicao).filter(
        AtendimentoAtribuicao.loja_slug == loja_slug
    )
    if vendedor_email:
        consulta = consulta.filter(AtendimentoAtribuicao.vendedor_email == vendedor_email)
    return [
        atribuicao
        for atribuicao in consulta.all()
        if inicio <= _data(atribuicao.iniciada_em) <= fim
    ]


def lucro_bruto_venda(venda: Venda) -> Decimal | None:
    if venda.custo_veiculo is None:
        return None
    custo = venda.custo_veiculo
    diretos = sum((c.valor for c in venda.custos_diretos), Decimal("0"))
    return (venda.preco_venda - custo - diretos).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_metricas_vendas(db: Session, loja_slug: str, d_inicio: date, d_fim: date) -> dict:
    """Vendas confirmadas no período + faturamento/lucro bruto agregados.

    Única fonte da verdade para os totais do dashboard financeiro e dos
    relatórios CSV — qualquer alteração aqui reflete em ambos automaticamente.
    """
    confirmadas = [
        v
        for v in db.query(Venda).filter(Venda.loja_slug == loja_slug, Venda.status == "confirmada").all()
        if d_inicio <= _data(v.criada_em) <= d_fim
    ]
    faturamento = sum((v.preco_venda for v in confirmadas), Decimal("0"))
    lucros_conhecidos = [valor for venda in confirmadas if (valor := lucro_bruto_venda(venda)) is not None]
    lucro = sum(lucros_conhecidos, Decimal("0"))
    vendas_lucro_incompleto = len(confirmadas) - len(lucros_conhecidos)
    lucro_completo = vendas_lucro_incompleto == 0
    return {
        "confirmadas": confirmadas,
        "quantidade": len(confirmadas),
        "faturamento": faturamento,
        "lucro_bruto": lucro,
        "lucro_completo": lucro_completo,
        "vendas_lucro_incompleto": vendas_lucro_incompleto,
    }


def metas_view_periodo(
    db: Session,
    loja_slug: str,
    d_inicio: date,
    d_fim: date,
    realizado_por_tipo: dict,
    lucro_completo: bool,
) -> list[dict]:
    """Metas ativas da loja cujo período cruza [d_inicio, d_fim], com atingimento."""
    metas_view = []
    for meta in db.query(Meta).filter(
        Meta.loja_slug == loja_slug,
        Meta.escopo == "loja",
        Meta.ativa.is_(True),
    ).all():
        if meta.tipo not in realizado_por_tipo or not (meta.periodo_inicio <= d_fim and meta.periodo_fim >= d_inicio):
            continue
        realizado = realizado_por_tipo[meta.tipo]
        indisponivel = meta.tipo == "lucro_bruto" and not lucro_completo
        pct = round(float(realizado / meta.valor_alvo * 100), 1) if meta.valor_alvo and not indisponivel else 0.0
        metas_view.append(
            {
                "tipo": meta.tipo,
                "alvo": meta.valor_alvo,
                "realizado": realizado,
                "pct": pct,
                "pct_barra": min(pct, 100),
                "quantidade": meta.tipo == "quantidade",
                "indisponivel": indisponivel,
            }
        )
    return metas_view


def funil_periodo(
    chatbot,
    db: Session,
    loja_slug: str,
    d_inicio: date,
    d_fim: date,
    vendedor_filtro: str | None,
    origem: str | None,
    confirmadas: list[Venda],
    utm_campaign: str | None = None,
) -> tuple[dict, list[str], list[str]]:
    """Funil auditável (leads elegíveis/atendidos/vendas vinculadas) — mesma
    lógica usada no painel financeiro e no CSV de funil.

    Retorna (funil, origens, utm_campaigns).
    """
    from app.clients.chatbot import ChatbotIndisponivel  # import tardio: evita ciclo com app.clients

    origens: list[str] = []
    campanhas_utm: list[str] = []
    funil = {
        "disponivel": False,
        "elegiveis": None,
        "atendidos": None,
        "vendas_vinculadas": None,
        "erro": None,
    }
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel as exc:
        funil["erro"] = str(exc)
        return funil, origens, campanhas_utm

    origens = sorted({valor for lead in leads if (valor := origem_lead(lead))}, key=str.casefold)
    campanhas_utm = sorted(
        {valor for lead in leads if (valor := lead_utm_campaign(lead))},
        key=str.casefold,
    )
    candidatos = [
        lead
        for lead in leads
        if lead_corresponde_origem(lead, origem)
        and lead_corresponde_utm_campaign(lead, utm_campaign)
    ]
    leads_sem_data = [lead for lead in candidatos if data_api(lead.get("criada_em")) is None]
    if leads_sem_data:
        funil["erro"] = (
            f"{len(leads_sem_data)} lead(s) sem data de criação confiável; "
            "as contagens do período estão indisponíveis."
        )
        return funil, origens, campanhas_utm

    elegiveis = [
        lead
        for lead in candidatos
        if d_inicio <= data_api(lead.get("criada_em")) <= d_fim
    ]
    atribuicoes_periodo = atribuicoes_no_periodo(
        db,
        loja_slug,
        d_inicio,
        d_fim,
        vendedor_email=vendedor_filtro,
    )
    hashes_atendidos = {item.telefone_hmac for item in atribuicoes_periodo}
    if vendedor_filtro:
        elegiveis = [
            lead
            for lead in elegiveis
            if identidade_telefone(lead.get("telefone")) in hashes_atendidos
        ]
    ids_elegiveis = {str(lead.get("id")) for lead in elegiveis if lead.get("id")}
    atendidos = {
        str(lead.get("id"))
        for lead in elegiveis
        if lead.get("id") and identidade_telefone(lead.get("telefone")) in hashes_atendidos
    }
    vendas_vinculadas = [
        venda
        for venda in confirmadas
        if venda.lead_ref and venda.lead_ref in ids_elegiveis
        and (not vendedor_filtro or venda.vendedor_email == vendedor_filtro)
    ]
    funil.update(
        {
            "disponivel": True,
            "elegiveis": len(elegiveis),
            "atendidos": len(atendidos),
            "vendas_vinculadas": len(vendas_vinculadas),
        }
    )
    return funil, origens, campanhas_utm
