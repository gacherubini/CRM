from datetime import date, datetime, timezone
from decimal import Decimal

from app.models import Campanha, CampanhaGasto, Venda, novo_id
from app.roi_calc import calcular_roi_loja, totais_roi


def _campanha(**kwargs):
    base = dict(
        id=novo_id(),
        loja_slug="loja-teste",
        nome="Seminovos",
        canal="meta",
        status="ativa",
        utm_campaign="seminovos-julho",
        utm_campaign_norm="seminovos-julho",
        criada_por_email="dono@loja.test",
    )
    base.update(kwargs)
    return Campanha(**base)


def test_cpl_cpa_roas_basico():
    c = _campanha()
    gastos = [
        CampanhaGasto(
            id=novo_id(),
            campanha_id=c.id,
            loja_slug="loja-teste",
            valor=Decimal("1000.00"),
            referencia=date(2026, 7, 10),
            criada_por="dono@loja.test",
        )
    ]
    leads = [
        {
            "id": f"l{i}",
            "utm_campaign": "seminovos-julho",
            "utm_campaign_last": "seminovos-julho",
            "criada_em": "2026-07-15T12:00:00+00:00",
        }
        for i in range(10)
    ]
    vendas = [
        Venda(
            id=novo_id(),
            loja_slug="loja-teste",
            vendedor_email="v@t.com",
            descricao="moto",
            preco_venda=Decimal("5000.00"),
            status="confirmada",
            campanha_id_last=c.id,
            utm_campaign_last="seminovos-julho",
            criada_em=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confirmada_em=datetime(2026, 7, 16, tzinfo=timezone.utc),
        )
        for _ in range(2)
    ]
    linhas = calcular_roi_loja(
        campanhas=[c],
        gastos=gastos,
        leads=leads,
        vendas_confirmadas=vendas,
        d_inicio=date(2026, 7, 1),
        d_fim=date(2026, 7, 31),
        modo_atribuicao="last",
    )
    linha = next(l for l in linhas if l.campanha_id == c.id)
    assert linha.cpl == Decimal("100.00")
    assert linha.cpa == Decimal("500.00")
    assert linha.roas == Decimal("10.00")
    assert linha.roas_barra_pct == 100.0
    totais = totais_roi(linhas)
    assert totais["gasto"] == Decimal("1000.00")
    assert totais["leads"] == 10


def test_gasto_zero_metricas_none():
    c = _campanha()
    leads = [
        {
            "id": "l1",
            "utm_campaign": "seminovos-julho",
            "criada_em": "2026-07-15T12:00:00+00:00",
        }
    ]
    linhas = calcular_roi_loja(
        campanhas=[c],
        gastos=[],
        leads=leads,
        vendas_confirmadas=[],
        d_inicio=date(2026, 7, 1),
        d_fim=date(2026, 7, 31),
    )
    linha = next(l for l in linhas if l.campanha_id == c.id)
    assert linha.cpl is None
    assert linha.roas is None
    assert linha.leads == 1


def test_first_vs_last_separa_leads():
    ca = _campanha(nome="A", utm_campaign="camp-a", utm_campaign_norm="camp-a")
    cb = _campanha(nome="B", utm_campaign="camp-b", utm_campaign_norm="camp-b")
    lead = {
        "id": "l1",
        "utm_campaign_first": "camp-a",
        "utm_campaign_last": "camp-b",
        "utm_campaign": "camp-b",
        "criada_em": "2026-07-15T12:00:00+00:00",
    }
    first = calcular_roi_loja(
        campanhas=[ca, cb],
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[],
        d_inicio=date(2026, 7, 1),
        d_fim=date(2026, 7, 31),
        modo_atribuicao="first",
    )
    last = calcular_roi_loja(
        campanhas=[ca, cb],
        gastos=[],
        leads=[lead],
        vendas_confirmadas=[],
        d_inicio=date(2026, 7, 1),
        d_fim=date(2026, 7, 31),
        modo_atribuicao="last",
    )
    assert next(l for l in first if l.campanha_id == ca.id).leads == 1
    assert next(l for l in first if l.campanha_id == cb.id).leads == 0
    assert next(l for l in last if l.campanha_id == ca.id).leads == 0
    assert next(l for l in last if l.campanha_id == cb.id).leads == 1
