"""Leitura executiva dos resultados de tráfego no dashboard do dono."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.models import Campanha, CampanhaGasto, MetaCapiOutbox, MetaPixelConfig, Venda
from app.meta_pixel import normalizar_pixel_id
from app.roi_calc import LinhaRoiCampanha, totais_roi


@dataclass(frozen=True)
class AlertaTrafego:
    codigo: str
    texto: str
    href: str
    acao: str


def resumo_from_api(payload: dict) -> dict:
    """Adapta JSON da API Revy Tráfego ao shape usado pelo partial de resultados."""
    from types import SimpleNamespace

    totais_raw = payload.get("totais") or {}

    def _d(v):
        if v is None or v == "":
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    totais = {
        "gasto": _d(totais_raw.get("gasto")) or Decimal("0.00"),
        "leads": int(totais_raw.get("leads") or 0),
        "vendas": int(totais_raw.get("vendas") or 0),
        "faturamento": _d(totais_raw.get("faturamento")) or Decimal("0.00"),
        "cpl": _d(totais_raw.get("cpl")),
        "cpa": _d(totais_raw.get("cpa")),
        "roas": _d(totais_raw.get("roas")),
    }
    canais = []
    for item in payload.get("canais") or []:
        roas = _d(item.get("roas"))
        canais.append(
            {
                "canal": item.get("canal") or "outro",
                "gasto": _d(item.get("gasto")) or Decimal("0.00"),
                "vendas": int(item.get("vendas") or 0),
                "faturamento": _d(item.get("faturamento")) or Decimal("0.00"),
                "roas": roas,
                "roas_barra_pct": item.get("roas_barra_pct")
                or (
                    min(100.0, float(roas) / 5.0 * 100.0) if roas is not None else 0.0
                ),
            }
        )
    melhor_raw = payload.get("melhor_campanha")
    melhor = None
    if melhor_raw:
        melhor = SimpleNamespace(
            campanha_id=melhor_raw.get("id"),
            nome=melhor_raw.get("nome") or "—",
            canal=melhor_raw.get("canal") or "—",
            roas=_d(melhor_raw.get("roas")),
            vendas=int(melhor_raw.get("vendas") or 0),
            leads=int(melhor_raw.get("leads") or 0),
            gasto=_d(melhor_raw.get("gasto")) or Decimal("0.00"),
        )
    return {
        "totais": totais,
        "canais": canais,
        "melhor_campanha": melhor,
        "tem_campanhas": bool(payload.get("tem_campanhas")),
        "vendas_sem_campanha": int(payload.get("vendas_sem_campanha") or 0),
        "leads_sem_campanha": int(payload.get("leads_sem_campanha") or 0),
        "fonte": "api",
    }


def resumo_periodo(linhas: Iterable[LinhaRoiCampanha]) -> dict:
    itens = list(linhas)
    campanhas = [linha for linha in itens if linha.campanha_id is not None]
    totais = totais_roi(itens)
    por_canal: dict[str, dict] = {}
    for linha in campanhas:
        chave_canal = linha.canal if linha.canal in {"meta", "google"} else "outro"
        canal = por_canal.setdefault(
            chave_canal,
            {
                "canal": chave_canal,
                "gasto": Decimal("0.00"),
                "vendas": 0,
                "faturamento": Decimal("0.00"),
            },
        )
        canal["gasto"] += linha.gasto
        canal["vendas"] += linha.vendas
        canal["faturamento"] += linha.faturamento
    canais = []
    for canal in por_canal.values():
        if canal["gasto"] <= 0 and canal["vendas"] <= 0 and canal["faturamento"] <= 0:
            continue
        canal["roas"] = (
            (canal["faturamento"] / canal["gasto"]).quantize(Decimal("0.01"))
            if canal["gasto"] > 0
            else None
        )
        canal["roas_barra_pct"] = (
            min(100.0, float(canal["roas"]) / 5.0 * 100.0)
            if canal["roas"] is not None
            else 0.0
        )
        canais.append(canal)
    canais.sort(key=lambda item: (item["gasto"], item["vendas"]), reverse=True)

    com_resultado = [
        linha
        for linha in campanhas
        if linha.gasto > 0 and linha.vendas > 0 and linha.roas is not None
    ]
    if com_resultado:
        melhor = max(com_resultado, key=lambda linha: (linha.roas or Decimal("0"), linha.vendas))
    else:
        candidatas = [linha for linha in campanhas if linha.vendas > 0]
        melhor = max(candidatas, key=lambda linha: linha.vendas) if candidatas else None
    sem_campanha = next((linha for linha in itens if linha.campanha_id is None), None)
    return {
        "totais": totais,
        "canais": canais,
        "melhor_campanha": melhor,
        "tem_campanhas": bool(campanhas),
        "vendas_sem_campanha": sem_campanha.vendas if sem_campanha else 0,
        "leads_sem_campanha": sem_campanha.leads if sem_campanha else 0,
    }


def alertas_trafego(
    *,
    linhas: Iterable[LinhaRoiCampanha],
    config: MetaPixelConfig | None,
    ultimo_outbox: MetaCapiOutbox | None,
    chatbot_offline: bool = False,
    modo_cliente: bool = False,
) -> list[AlertaTrafego]:
    """Alertas de mídia.

    ``modo_cliente=True``: só linguagem de negócio, sem links de config técnica
    (equipe Revy opera no app Revy Tráfego).
    """
    itens = list(linhas)
    campanhas = [linha for linha in itens if linha.campanha_id is not None]
    sem_campanha = next((linha for linha in itens if linha.campanha_id is None), None)
    alertas: list[AlertaTrafego] = []
    if modo_cliente:
        if sem_campanha and sem_campanha.vendas:
            n = sem_campanha.vendas
            alertas.append(
                AlertaTrafego(
                    "vendas_sem_utm",
                    f"{n} {'venda está' if n == 1 else 'vendas estão'} sem campanha atribuída.",
                    "/app/vendas",
                    "Ver vendas",
                )
            )
        if chatbot_offline:
            alertas.append(
                AlertaTrafego(
                    "chatbot_offline",
                    "Contagem de leads pode estar incompleta no momento.",
                    "/app/leads",
                    "Ver leads",
                )
            )
        return alertas[:4]

    if ultimo_outbox is not None and ultimo_outbox.status == "failed":
        alertas.append(
            AlertaTrafego(
                "capi_falhou",
                "Purchase Meta falhou — retente o envio na aba Tráfego.",
                "/app/trafego",
                "Retentar",
            )
        )
    if (
        config is None
        or not normalizar_pixel_id(config.pixel_id)
        or not config.token_ciphertext
    ):
        alertas.append(
            AlertaTrafego(
                "pixel_nao_config",
                "Configure o Pixel e a CAPI para fechar o ciclo de medição.",
                "/app/trafego",
                "Configurar",
            )
        )
    if sem_campanha and sem_campanha.vendas:
        n = sem_campanha.vendas
        alertas.append(
            AlertaTrafego(
                "vendas_sem_utm",
                f"{n} {'venda está' if n == 1 else 'vendas estão'} sem campanha no ROI.",
                "/app/trafego/roi",
                "Ver ROI",
            )
        )
    sem_gasto = sum(1 for linha in campanhas if linha.status == "ativa" and linha.gasto <= 0)
    if sem_gasto:
        alertas.append(
            AlertaTrafego(
                "campanhas_sem_gasto",
                f"{sem_gasto} {'campanha ativa está' if sem_gasto == 1 else 'campanhas ativas estão'} "
                "sem gasto no período.",
                "/app/campanhas/gastos/lote",
                "Lançar gastos",
            )
        )
    total_leads = sum(linha.leads for linha in itens)
    if sem_campanha and sem_campanha.leads and total_leads:
        percentual = round(sem_campanha.leads / total_leads * 100)
        alertas.append(
            AlertaTrafego(
                "leads_sem_utm",
                f"{percentual}% dos leads estão sem UTM de campanha.",
                "/app/campanhas",
                "Revisar UTMs",
            )
        )
    if chatbot_offline:
        alertas.append(
            AlertaTrafego(
                "chatbot_offline",
                "Chatbot offline: a contagem de leads pode estar incompleta.",
                "/app/trafego/roi",
                "Ver dados locais",
            )
        )
    return alertas[:4]


def checklist_medicao(
    *,
    config: MetaPixelConfig | None,
    campanhas: Iterable[Campanha],
    gastos: Iterable[CampanhaGasto],
    vendas: Iterable[Venda],
    outboxes: Iterable[MetaCapiOutbox],
) -> dict:
    campanhas_lista = list(campanhas)
    gastos_lista = list(gastos)
    vendas_lista = list(vendas)
    outboxes_lista = list(outboxes)
    purchase_desligado = bool(config is not None and not config.enviar_purchase)
    passos = [
        {
            "rotulo": "Pixel / CAPI configurado",
            "feito": bool(
                config
                and normalizar_pixel_id(config.pixel_id)
                and config.token_ciphertext
            ),
            "href": "/app/trafego",
        },
        {
            "rotulo": "Campanha com UTM",
            "feito": any(c.status == "ativa" and bool(c.utm_campaign) for c in campanhas_lista),
            "href": "/app/campanhas/nova",
        },
        {
            "rotulo": "Gasto lançado",
            "feito": bool(gastos_lista),
            "href": "/app/campanhas/gastos/lote",
        },
        {
            "rotulo": "Venda com lead",
            "feito": any(v.status == "confirmada" and bool(v.lead_ref) for v in vendas_lista),
            "href": "/app/vendas",
        },
        {
            "rotulo": "Purchase desligado" if purchase_desligado else "Purchase enviado",
            "feito": purchase_desligado or any(o.status == "delivered" for o in outboxes_lista),
            "href": "/app/trafego",
        },
    ]
    concluidos = sum(1 for passo in passos if passo["feito"])
    proximo = next((passo["href"] for passo in passos if not passo["feito"]), "/app/trafego/roi")
    return {
        "passos": passos,
        "concluidos": concluidos,
        "total": len(passos),
        "completo": concluidos == len(passos),
        "proximo_href": proximo,
        "dispensado": bool(config and config.medicao_onboarding_dismiss_em),
    }
