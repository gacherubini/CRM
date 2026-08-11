from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.consultas_origem import (
    venda_origem_periodo,
    venda_origem_ultima,
)
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Campanha, Venda


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _campanha(db, id_, nome, utm="agosto-motos"):
    db.add(
        Campanha(
            id=id_,
            loja_slug="loja-teste",
            nome=nome,
            canal="meta",
            utm_campaign=utm,
            utm_campaign_norm=utm,
            criada_por_email="dono@loja.test",
        )
    )
    db.commit()


def _venda(db, *, dia, first=None, last=None, utm_last=None, preco=30000):
    venda = Venda(
        loja_slug="loja-teste",
        vendedor_email="ana@loja.test",
        descricao=f"Honda CB 500F dia {dia}",
        preco_venda=Decimal(str(preco)),
        status="confirmada",
        criada_em=datetime(2026, 8, dia, 15, 0, tzinfo=timezone.utc),
        confirmada_em=datetime(2026, 8, dia, 16, 0, tzinfo=timezone.utc),
        campanha_id_first=first,
        campanha_id_last=last,
        utm_campaign_last=utm_last,
    )
    db.add(venda)
    db.commit()
    return venda


def test_ultima_venda_com_campanha_devolve_nome_e_utm(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=5, first="camp-1", last="camp-1", utm_last="agosto-motos")
    r = venda_origem_ultima(db, _ctx())
    assert r.status == "ok"
    assert r.origem.identificada is True
    assert r.origem.campanha_nome == "Motos Agosto — Meta"
    assert r.origem.campanha_canal == "meta"
    assert r.origem.utm_campaign == "agosto-motos"


def test_ultima_venda_sem_campanha_nao_deduz(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=4, first="camp-1", last="camp-1")
    _venda(db, dia=6)  # mais recente, sem origem
    r = venda_origem_ultima(db, _ctx())
    assert r.status == "ok"
    assert r.origem.identificada is False
    assert r.origem.campanha_nome is None
    assert r.origem.descricao == "Honda CB 500F dia 6"


def test_sem_venda_nenhuma_e_vazio(db):
    r = venda_origem_ultima(db, _ctx())
    assert r.status == "vazio"
    assert r.origem is None


def test_periodo_declara_cobertura_parcial(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=3, first="camp-1", last="camp-1")
    _venda(db, dia=4, first="camp-1", last="camp-1")
    _venda(db, dia=5)
    r = venda_origem_periodo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "parcial"
    assert r.cobertura.to_dict() == {"com_dado": 2, "total": 3}
    assert len(r.itens) == 3


def test_periodo_com_tudo_identificado_e_ok(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=3, first="camp-1", last="camp-1")
    r = venda_origem_periodo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "ok"
    assert r.cobertura.completa is True


def test_primeiro_clique_diferente_do_ultimo_aparece(db):
    _campanha(db, "camp-1", "Prospecção — Meta", utm="prospec")
    _campanha(db, "camp-2", "Remarketing — Meta", utm="remkt")
    _venda(db, dia=5, first="camp-1", last="camp-2", utm_last="remkt")
    r = venda_origem_ultima(db, _ctx())
    assert r.origem.campanha_nome == "Remarketing — Meta"
    assert r.origem.primeiro_clique_nome == "Prospecção — Meta"


def test_campanha_apagada_nao_derruba_a_consulta(db):
    """Snapshot aponta para campanha que não existe mais: conta como origem
    conhecida (o id está lá), mas sem nome inventado."""
    _venda(db, dia=5, first="camp-sumiu", last="camp-sumiu", utm_last="agosto")
    r = venda_origem_ultima(db, _ctx())
    assert r.origem.identificada is True
    assert r.origem.campanha_nome is None
    assert r.origem.utm_campaign == "agosto"
