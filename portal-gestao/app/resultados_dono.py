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
) -> list[AlertaTrafego]:
    itens = list(linhas)
    campanhas = [linha for linha in itens if linha.campanha_id is not None]
    sem_campanha = next((linha for linha in itens if linha.campanha_id is None), None)
    alertas: list[AlertaTrafego] = []
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
