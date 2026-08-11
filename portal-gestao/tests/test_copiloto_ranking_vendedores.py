from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.consultas_vendas import ranking_vendedores
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Venda


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _venda(db, email, preco, dia, mes=8, loja="loja-teste"):
    db.add(
        Venda(
            loja_slug=loja,
            vendedor_email=email,
            descricao="Moto",
            preco_venda=Decimal(str(preco)),
            status="confirmada",
            criada_em=datetime(2026, mes, dia, 15, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()


def test_ordena_por_receita_desc(db):
    _venda(db, "ana@loja.test", 30000, 3)
    _venda(db, "bruno@loja.test", 50000, 4)
    _venda(db, "ana@loja.test", 10000, 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "ok"
    assert [linha.vendedor_email for linha in r.linhas] == [
        "bruno@loja.test",
        "ana@loja.test",
    ]
    assert r.linhas[0].posicao == 1
    assert r.linhas[1].qtd == 2
    assert r.linhas[1].receita == Decimal("40000.00")
    assert r.linhas[1].ticket_medio == Decimal("20000.00")


def test_marca_quem_subiu_e_quem_caiu(db):
    # Julho: ana lidera. Agosto: bruno assume.
    _venda(db, "ana@loja.test", 90000, 10, mes=7)
    _venda(db, "bruno@loja.test", 10000, 12, mes=7)
    _venda(db, "bruno@loja.test", 80000, 4)
    _venda(db, "ana@loja.test", 20000, 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    por_email = {linha.vendedor_email: linha for linha in r.linhas}
    assert por_email["bruno@loja.test"].posicao == 1
    assert por_email["bruno@loja.test"].posicao_anterior == 2
    assert por_email["bruno@loja.test"].variacao == "subiu"
    assert por_email["ana@loja.test"].variacao == "caiu"


def test_vendedor_novo_no_periodo_e_novo_nao_subiu(db):
    _venda(db, "ana@loja.test", 10000, 10, mes=7)
    _venda(db, "ana@loja.test", 10000, 4)
    _venda(db, "caio@loja.test", 50000, 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    por_email = {linha.vendedor_email: linha for linha in r.linhas}
    assert por_email["caio@loja.test"].posicao_anterior is None
    assert por_email["caio@loja.test"].variacao == "novo"


def test_sem_venda_no_periodo_e_vazio(db):
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "vazio"
    assert r.linhas == ()


def test_nao_mistura_outra_loja(db):
    _venda(db, "x@outra.test", 99000, 5, loja="outra-loja")
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "vazio"


def test_respeita_limite(db):
    for i in range(5):
        _venda(db, f"v{i}@loja.test", 1000 * (i + 1), 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31", limite=3)
    assert len(r.linhas) == 3
    assert r.linhas[0].vendedor_email == "v4@loja.test"
