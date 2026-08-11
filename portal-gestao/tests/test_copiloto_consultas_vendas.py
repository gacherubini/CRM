from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.consultas_vendas import vendas_resumo
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Venda


def _ctx(papel="dono"):
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel=papel,
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _venda(db, *, preco, custo=None, dia, mes=8, status="confirmada", email="v1@loja.test"):
    db.add(
        Venda(
            loja_slug="loja-teste",
            vendedor_email=email,
            descricao="Honda CB 500F 2020",
            preco_venda=Decimal(str(preco)),
            custo_veiculo=None if custo is None else Decimal(str(custo)),
            status=status,
            criada_em=datetime(2026, mes, dia, 15, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()


def test_ticket_medio_e_receita_do_periodo(db):
    _venda(db, preco=30000, dia=3)
    _venda(db, preco=20000, dia=7)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "ok"
    assert r.qtd_vendas == 2
    assert r.receita == Decimal("50000.00")
    assert r.ticket_medio == Decimal("25000.00")


def test_periodo_sem_venda_e_vazio_e_nao_inventa_ticket(db):
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "vazio"
    assert r.qtd_vendas == 0
    assert r.receita == Decimal("0.00")
    assert r.ticket_medio is None


def test_margem_parcial_declara_cobertura(db):
    _venda(db, preco=30000, custo=24000, dia=3)
    _venda(db, preco=20000, custo=None, dia=7)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "parcial"
    assert r.cobertura_margem.to_dict() == {"com_dado": 1, "total": 2}
    assert r.cobertura_margem.parcial is True
    assert r.margem == Decimal("6000.00")


def test_vendedor_nao_recebe_margem(db):
    _venda(db, preco=30000, custo=24000, dia=3)
    r = vendas_resumo(db, _ctx(papel="vendedor"), inicio="2026-08-01", fim="2026-08-31")
    assert r.margem is None
    assert r.status == "ok"


def test_compara_com_o_mes_anterior(db):
    _venda(db, preco=30000, dia=3, mes=8)
    _venda(db, preco=20000, dia=10, mes=7)
    _venda(db, preco=20000, dia=20, mes=7)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.janela_comparacao.rotulo == "julho/2026"
    assert r.qtd_vendas_anterior == 2
    assert r.receita_anterior == Decimal("40000.00")
    assert r.ticket_medio_anterior == Decimal("20000.00")
    assert r.delta_qtd == -1
    assert r.delta_receita_pct == Decimal("-25.0")
    assert r.delta_ticket_pct == Decimal("50.0")


def test_sem_periodo_anterior_o_delta_e_none_nao_zero(db):
    """Zero de comparação mentiria: "caiu 100%" quando nunca houve mês anterior."""
    _venda(db, preco=30000, dia=3)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.qtd_vendas_anterior == 0
    assert r.delta_receita_pct is None
    assert r.delta_ticket_pct is None


def test_venda_nao_confirmada_nao_entra(db):
    _venda(db, preco=30000, dia=3, status="registrada")
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.qtd_vendas == 0


def test_venda_de_outra_loja_nao_entra(db):
    db.add(
        Venda(
            loja_slug="outra-loja",
            vendedor_email="x@outra.test",
            descricao="Yamaha MT-03",
            preco_venda=Decimal("31900"),
            status="confirmada",
            criada_em=datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.qtd_vendas == 0
