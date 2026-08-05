"""ROI de campanhas: CPL, CPA, ROAS (puro e testável)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from app.campanhas import gasto_no_periodo, lead_casa_campanha, normalizar_utm
from app.financeiro_calc import VendaRoi, _data, lucro_bruto_venda
from app.models import Campanha, CampanhaGasto

CENTAVOS = Decimal("0.01")
QUATRO = Decimal("0.0001")


@dataclass
class LinhaRoiCampanha:
    campanha_id: str | None
    nome: str
    canal: str
    utm_campaign: str
    status: str
    gasto: Decimal
    leads: int
    vendas: int
    faturamento: Decimal
    lucro_bruto: Decimal | None
    cpl: Decimal | None
    cpa: Decimal | None
    roas: Decimal | None

    @property
    def roas_barra_pct(self) -> float:
        """Barra visual: 0–100, ROAS 1x = 20%, ROAS 5x+ = 100%."""
        if self.roas is None:
            return 0.0
        try:
            r = float(self.roas)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, (r / 5.0) * 100.0))


def _lead_no_periodo(lead: dict, d_inicio: date, d_fim: date) -> bool:
    raw = lead.get("atribuida_em") or lead.get("criada_em")
    if not raw:
        return False
    try:
        from datetime import datetime

        if isinstance(raw, str):
            momento = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            momento = raw
    except (TypeError, ValueError):
        return False
    dia = _data(momento)
    return d_inicio <= dia <= d_fim


def _div(num: Decimal, den: int | Decimal) -> Decimal | None:
    if not den:
        return None
    if num <= 0:
        return None
    return (num / Decimal(den)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _roas(faturamento: Decimal, gasto: Decimal) -> Decimal | None:
    if gasto <= 0:
        return None
    return (faturamento / gasto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def venda_casa_campanha(
    venda: VendaRoi, campanha: Campanha, *, modo: str = "last"
) -> bool:
    if modo == "first":
        return venda.campanha_id_first == campanha.id or (
            not venda.campanha_id_first
            and normalizar_utm(venda.utm_campaign_first) == normalizar_utm(campanha.utm_campaign)
        )
    return venda.campanha_id_last == campanha.id or (
        not venda.campanha_id_last
        and normalizar_utm(venda.utm_campaign_last) == normalizar_utm(campanha.utm_campaign)
    )


def calcular_roi_loja(
    *,
    campanhas: list[Campanha],
    gastos: list[CampanhaGasto],
    leads: list[dict],
    vendas_confirmadas: list[VendaRoi],
    d_inicio: date,
    d_fim: date,
    modo_atribuicao: str = "last",
    mapa_ad_campaign: dict[str, str] | None = None,
) -> list[LinhaRoiCampanha]:
    modo = modo_atribuicao if modo_atribuicao in ("first", "last") else "last"
    leads_periodo = [l for l in leads if _lead_no_periodo(l, d_inicio, d_fim)]
    mapa = mapa_ad_campaign or None

    linhas: list[LinhaRoiCampanha] = []
    leads_matched_ids: set[str] = set()
    vendas_matched_ids: set[str] = set()

    for campanha in sorted(campanhas, key=lambda c: c.nome.casefold()):
        gasto = gasto_no_periodo(gastos, campanha.id, d_inicio, d_fim)
        leads_c = [
            l
            for l in leads_periodo
            if lead_casa_campanha(l, campanha, modo=modo, mapa_ad_campaign=mapa)
        ]
        for l in leads_c:
            if l.get("id"):
                leads_matched_ids.add(str(l["id"]))

        vendas_c: list[VendaRoi] = []
        for v in vendas_confirmadas:
            if venda_casa_campanha(v, campanha, modo=modo):
                vendas_c.append(v)
        for v in vendas_c:
            vendas_matched_ids.add(v.id)

        faturamento = sum((v.preco_venda for v in vendas_c), Decimal("0"))
        lucros = [x for v in vendas_c if (x := lucro_bruto_venda(v)) is not None]
        lucro = sum(lucros, Decimal("0")) if lucros and len(lucros) == len(vendas_c) else (
            sum(lucros, Decimal("0")) if lucros else None
        )
        if vendas_c and len(lucros) != len(vendas_c):
            lucro_final: Decimal | None = None
        else:
            lucro_final = lucro.quantize(CENTAVOS, rounding=ROUND_HALF_UP) if lucro is not None else (
                Decimal("0.00") if not vendas_c else None
            )

        n_leads = len(leads_c)
        n_vendas = len(vendas_c)
        linhas.append(
            LinhaRoiCampanha(
                campanha_id=campanha.id,
                nome=campanha.nome,
                canal=campanha.canal,
                utm_campaign=campanha.utm_campaign,
                status=campanha.status,
                gasto=gasto,
                leads=n_leads,
                vendas=n_vendas,
                faturamento=faturamento.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
                lucro_bruto=lucro_final,
                cpl=_div(gasto, n_leads),
                cpa=_div(gasto, n_vendas),
                roas=_roas(faturamento, gasto),
            )
        )

    # Sem campanha
    leads_sem = [l for l in leads_periodo if str(l.get("id") or "") not in leads_matched_ids]
    # leads without id
    leads_sem += [
        l
        for l in leads_periodo
        if not l.get("id")
        and all(
            not lead_casa_campanha(l, c, modo=modo, mapa_ad_campaign=mapa)
            for c in campanhas
        )
    ]
    # dedupe by id/object
    seen = set()
    leads_sem_u = []
    for l in leads_sem:
        key = str(l.get("id") or id(l))
        if key in seen:
            continue
        seen.add(key)
        leads_sem_u.append(l)

    vendas_sem = [v for v in vendas_confirmadas if v.id not in vendas_matched_ids]
    fat_sem = sum((v.preco_venda for v in vendas_sem), Decimal("0"))
    linhas.append(
        LinhaRoiCampanha(
            campanha_id=None,
            nome="Sem campanha",
            canal="—",
            utm_campaign="—",
            status="—",
            gasto=Decimal("0.00"),
            leads=len(leads_sem_u),
            vendas=len(vendas_sem),
            faturamento=fat_sem.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
            lucro_bruto=None,
            cpl=None,
            cpa=None,
            roas=None,
        )
    )
    return linhas


def totais_roi(linhas: Iterable[LinhaRoiCampanha]) -> dict:
    itens = [l for l in linhas if l.campanha_id is not None]
    gasto = sum((l.gasto for l in itens), Decimal("0"))
    leads = sum(l.leads for l in itens)
    vendas = sum(l.vendas for l in itens)
    faturamento = sum((l.faturamento for l in itens), Decimal("0"))
    return {
        "gasto": gasto.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "leads": leads,
        "vendas": vendas,
        "faturamento": faturamento.quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        "cpl": _div(gasto, leads),
        "cpa": _div(gasto, vendas),
        "roas": _roas(faturamento, gasto),
    }


def gerar_insights_roi(
    linhas: Iterable[LinhaRoiCampanha],
    totais: dict,
) -> list[str]:
    """Gera leitura executiva determinística do ROI, sem atribuição causal."""
    itens = list(linhas)
    campanhas = [linha for linha in itens if linha.campanha_id is not None]
    insights: list[str] = []

    candidatas = [linha for linha in campanhas if linha.gasto > 0 and linha.vendas > 0]
    com_roas = [linha for linha in candidatas if linha.roas is not None]
    if com_roas:
        melhor = max(com_roas, key=lambda linha: (linha.roas or Decimal("0"), linha.vendas))
        insights.append(
            f"{melhor.nome} teve o melhor ROAS: {melhor.roas}x com {melhor.vendas} "
            f"{'venda' if melhor.vendas == 1 else 'vendas'}."
        )

    canais: dict[str, dict[str, int]] = {}
    for linha in campanhas:
        agregado = canais.setdefault(linha.canal, {"leads": 0, "vendas": 0})
        agregado["leads"] += linha.leads
        agregado["vendas"] += linha.vendas
    conversoes = [
        (canal, Decimal(dados["vendas"]) / Decimal(dados["leads"]))
        for canal, dados in canais.items()
        if dados["leads"] > 0
    ]
    if len(conversoes) >= 2:
        melhor_canal, melhor_taxa = max(conversoes, key=lambda item: item[1])
        pior_canal, pior_taxa = min(conversoes, key=lambda item: item[1])
        if melhor_canal != pior_canal:
            insights.append(
                f"Conversão de leads: {melhor_canal} {melhor_taxa * 100:.1f}% × "
                f"{pior_canal} {pior_taxa * 100:.1f}%."
            )

    sem_gasto = sum(1 for linha in campanhas if linha.status == "ativa" and linha.gasto <= 0)
    if sem_gasto:
        insights.append(
            f"{sem_gasto} {'campanha ativa está' if sem_gasto == 1 else 'campanhas ativas estão'} "
            "sem gasto lançado no período."
        )

    sem_campanha = next((linha for linha in itens if linha.campanha_id is None), None)
    if sem_campanha and (sem_campanha.leads or sem_campanha.vendas):
        insights.append(
            f"Sem campanha: {sem_campanha.leads} leads e {sem_campanha.vendas} vendas "
            "não entraram no ROI atribuído."
        )

    if totais.get("gasto", Decimal("0")) <= 0 and campanhas:
        insights.append("Lance os gastos do período para calcular CPL, CPA e ROAS.")
    elif totais.get("roas") is not None:
        insights.append(f"No total, cada R$ 1 investido virou R$ {totais['roas']} em vendas.")
    if campanhas:
        insights.append(
            f"O período acompanha {len(campanhas)} "
            f"{'campanha cadastrada' if len(campanhas) == 1 else 'campanhas cadastradas'} no Revy."
        )
    return insights[:8]
