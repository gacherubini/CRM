"""A venda sem atribuicao propria herda a campanha do lead que a originou.

Contexto de producao (08/08): 212 de 220 leads de anuncio tem `meta_ad_id`, mas
`venda_casa_campanha` so olha o que esta gravado na propria venda. A linha da
campanha mostrava leads e nao mostrava vendas.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from app.models import Campanha, CampanhaGasto, novo_id
from app.roi_calc import calcular_roi_loja, herdar_campanhas_de_leads


class Venda:
    """Fake estrutural: o calculo nao depende do ORM do Portal."""

    def __init__(self, **campos):
        campos.setdefault("loja_slug", "loja-teste")
        campos.setdefault("status", "confirmada")
        campos.setdefault("custo_veiculo", None)
        campos.setdefault("lead_ref", None)
        campos.setdefault("campanha_id_first", None)
        campos.setdefault("campanha_id_last", None)
        campos.setdefault("utm_campaign_first", None)
        campos.setdefault("utm_campaign_last", None)
        campos.setdefault("criada_em", datetime(2026, 8, 6, 12, tzinfo=timezone.utc))
        for nome, valor in campos.items():
            setattr(self, nome, valor)
        self.custos_diretos = campos.get("custos_diretos", [])


def _campanha(**kwargs):
    base = dict(
        id=novo_id(),
        loja_slug="loja-teste",
        nome="Seminovos",
        canal="meta",
        status="ativa",
        utm_campaign="seminovos-agosto",
        utm_campaign_norm="seminovos-agosto",
        criada_por_email="dono@loja.test",
    )
    base.update(kwargs)
    return Campanha(**base)


def _venda(**kwargs):
    base = dict(id=novo_id(), preco_venda=Decimal("32000.00"))
    base.update(kwargs)
    return Venda(**base)


def _gasto(campanha_id: str, valor: str):
    return CampanhaGasto(
        id=novo_id(),
        campanha_id=campanha_id,
        loja_slug="loja-teste",
        valor=Decimal(valor),
        referencia=date(2026, 8, 3),
        criada_por="dono@loja.test",
    )


AGOSTO = dict(d_inicio=date(2026, 8, 1), d_fim=date(2026, 8, 31))


def test_venda_sem_campanha_herda_do_lead_por_ad_id():
    """O caso dos 212 leads: lead com meta_ad_id, cache Graph ad->campanha, venda crua."""
    campanha = _campanha(
        id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224"
    )
    lead = {
        "id": "lead-1",
        "meta_ad_id": "120249613359810224",
        "criada_em": "2026-08-05T10:00:00+00:00",
    }
    venda = _venda(
        id="v-1",
        lead_ref="lead-1",
        preco_venda=Decimal("32000.00"),
        campanha_id_last=None,
        utm_campaign_last=None,
    )

    linhas = calcular_roi_loja(
        campanhas=[campanha],
        gastos=[_gasto("c-caua", "500.00")],
        leads=[lead],
        vendas_confirmadas=[venda],
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
        **AGOSTO,
    )
    linha = next(l for l in linhas if l.campanha_id == "c-caua")
    assert linha.leads == 1
    assert linha.vendas == 1
    assert linha.faturamento == Decimal("32000.00")
    assert linha.roas == Decimal("64.00")

    sem = next(l for l in linhas if l.campanha_id is None)
    assert sem.vendas == 0
    assert sem.faturamento == Decimal("0.00")


def test_lead_fora_do_periodo_ainda_atribui_a_venda():
    """Lead de julho, venda de agosto: o indice nao pode ser filtrado por periodo."""
    campanha = _campanha(id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224")
    lead = {
        "id": "lead-1",
        "meta_ad_id": "120249613359810224",
        "criada_em": "2026-07-30T10:00:00+00:00",
    }
    venda = _venda(id="v-1", lead_ref="lead-1", preco_venda=Decimal("32000.00"))

    linhas = calcular_roi_loja(
        campanhas=[campanha],
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[venda],
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
        **AGOSTO,
    )
    linha = next(l for l in linhas if l.campanha_id == "c-caua")
    assert linha.leads == 0, "o lead e de julho, nao conta no periodo"
    assert linha.vendas == 1, "mas a venda de agosto herda a campanha dele"


def test_atribuicao_explicita_vence_heranca():
    """UTM ja gravado no snapshot manda, mesmo que o lead case outra campanha."""
    explicita = _campanha(
        id="c-utm",
        nome="MT03 AGOSTO",
        utm_campaign="MT03AGOSTO",
        utm_campaign_norm="mt03agosto",
    )
    do_lead = _campanha(
        id="c-caua",
        nome="CAUA",
        utm_campaign="caua-agosto",
        utm_campaign_norm="caua-agosto",
        meta_campaign_id="120249613359800224",
    )
    lead = {
        "id": "lead-1",
        "meta_ad_id": "120249613359810224",
        "criada_em": "2026-08-05T10:00:00+00:00",
    }
    venda = _venda(id="v-1", lead_ref="lead-1", utm_campaign_last="MT03AGOSTO")

    linhas = calcular_roi_loja(
        campanhas=[explicita, do_lead],
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[venda],
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
        **AGOSTO,
    )
    assert next(l for l in linhas if l.campanha_id == "c-utm").vendas == 1
    assert next(l for l in linhas if l.campanha_id == "c-caua").vendas == 0


def test_venda_nao_conta_em_duas_campanhas():
    """Duas campanhas casam o mesmo lead -> faturamento nao dobra."""
    a = _campanha(
        id="c-a",
        nome="A Primeira",
        utm_campaign="camp-a",
        utm_campaign_norm="camp-a",
        meta_campaign_id="120249613359800224",
    )
    b = _campanha(
        id="c-b",
        nome="B Segunda",
        utm_campaign="camp-b",
        utm_campaign_norm="camp-b",
        meta_campaign_id="120249613359800224",
    )
    lead = {
        "id": "lead-1",
        "meta_campaign_id": "120249613359800224",
        "criada_em": "2026-08-05T10:00:00+00:00",
    }
    venda = _venda(id="v-1", lead_ref="lead-1", preco_venda=Decimal("32000.00"))

    linhas = calcular_roi_loja(
        campanhas=[b, a],  # ordem de entrada trocada de proposito
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[venda],
        **AGOSTO,
    )
    com_campanha = [l for l in linhas if l.campanha_id is not None]
    assert sum(l.vendas for l in com_campanha) == 1
    assert sum(l.faturamento for l in com_campanha) == Decimal("32000.00")
    assert next(l for l in linhas if l.campanha_id == "c-a").vendas == 1, (
        "determinismo: a primeira campanha da ordem do laco (nome casefold) leva"
    )


def test_lead_sem_ad_id_cai_em_sem_campanha():
    """Os 8 leads de anuncio sem identificador: nao inventar campanha."""
    campanha = _campanha(id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224")
    lead = {
        "id": "lead-2",
        "ctwa_source_type": "ctwa_ad",
        "meta_ad_id": None,
        "criada_em": "2026-08-05T10:00:00+00:00",
    }
    venda = _venda(id="v-1", lead_ref="lead-2", preco_venda=Decimal("32000.00"))

    linhas = calcular_roi_loja(
        campanhas=[campanha],
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[venda],
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
        **AGOSTO,
    )
    assert next(l for l in linhas if l.campanha_id == "c-caua").vendas == 0
    sem = next(l for l in linhas if l.campanha_id is None)
    assert sem.vendas == 1
    assert sem.faturamento == Decimal("32000.00")


def test_sem_lead_ref_cai_em_sem_campanha():
    campanha = _campanha(id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224")
    lead = {
        "id": "lead-1",
        "meta_ad_id": "120249613359810224",
        "criada_em": "2026-08-05T10:00:00+00:00",
    }
    venda = _venda(id="v-1", lead_ref=None, preco_venda=Decimal("32000.00"))

    linhas = calcular_roi_loja(
        campanhas=[campanha],
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[venda],
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
        **AGOSTO,
    )
    assert next(l for l in linhas if l.campanha_id == "c-caua").vendas == 0
    assert next(l for l in linhas if l.campanha_id is None).vendas == 1


def test_chatbot_offline_nao_quebra():
    """leads=[] (ChatbotIndisponivel) -> nenhuma heranca, nenhuma excecao."""
    campanha = _campanha(id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224")
    venda = _venda(id="v-1", lead_ref="lead-1", preco_venda=Decimal("32000.00"))

    linhas = calcular_roi_loja(
        campanhas=[campanha],
        gastos=[],
        leads=[],
        vendas_confirmadas=[venda],
        **AGOSTO,
    )
    assert next(l for l in linhas if l.campanha_id == "c-caua").vendas == 0
    assert next(l for l in linhas if l.campanha_id is None).vendas == 1


def test_heranca_devolve_mapa_venda_para_campanha():
    """A funcao pura, usada tambem pelo detalhe da campanha (main.py)."""
    campanha = _campanha(id="c-caua", nome="CAUA", meta_campaign_id="120249613359800224")
    lead = {"id": "lead-1", "meta_ad_id": "120249613359810224"}
    herdada = _venda(id="v-1", lead_ref="lead-1")
    propria = _venda(id="v-2", lead_ref="lead-1", campanha_id_last="c-outra")

    heranca = herdar_campanhas_de_leads(
        campanhas=[campanha],
        vendas=[herdada, propria],
        leads=[lead],
        modo="last",
        mapa_ad_campaign={"120249613359810224": "120249613359800224"},
    )
    assert heranca == {"v-1": "c-caua"}


def test_heranca_respeita_modo_first():
    """No modo first, a guarda de precedencia olha os campos _first."""
    campanha = _campanha(
        id="c-a", nome="A", utm_campaign="camp-a", utm_campaign_norm="camp-a"
    )
    lead = {"id": "lead-1", "utm_campaign_first": "camp-a", "utm_campaign_last": "camp-b"}
    venda = _venda(id="v-1", lead_ref="lead-1", utm_campaign_last="ja-tem-last")

    assert herdar_campanhas_de_leads(
        campanhas=[campanha], vendas=[venda], leads=[lead], modo="first"
    ) == {"v-1": "c-a"}
    assert (
        herdar_campanhas_de_leads(
            campanhas=[campanha], vendas=[venda], leads=[lead], modo="last"
        )
        == {}
    )
