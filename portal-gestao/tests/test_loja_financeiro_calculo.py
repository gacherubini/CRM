"""Resultado financeiro do mês: DRE + ponto de equilíbrio (2026-08-16).

O que mais importa aqui não é a soma — é a **indisponibilidade honesta**.
Margem parcial não vira estimativa, mês sem venda não vira zero e margem
média negativa não vira ponto de equilíbrio infinito. Mesma regra que o resto
do Revy segue: fonte incompleta → indisponível, nunca zero.
"""
from __future__ import annotations

from decimal import Decimal

from app.db import SessionLocal
from app.loja.financeiro import (
    despesa_fixa_do_mes,
    resultado_financeiro_mes,
)
from app.models import DespesaFixaAjuste, DespesaFixaLoja, Venda, agora


def _venda(preco, custo, *, status="confirmada", loja="loja-teste"):
    db = SessionLocal()
    try:
        v = Venda(
            loja_slug=loja,
            vendedor_email="v@loja.test",
            descricao="Honda CG 160",
            preco_venda=Decimal(preco),
            custo_veiculo=Decimal(custo) if custo is not None else None,
            status=status,
            confirmada_em=agora() if status == "confirmada" else None,
        )
        db.add(v)
        db.commit()
        return v.id
    finally:
        db.close()


def _despesa(valor, *, inicio="2026-01", fim=None, categoria="aluguel", loja="loja-teste"):
    db = SessionLocal()
    try:
        d = DespesaFixaLoja(
            loja_slug=loja,
            categoria=categoria,
            descricao=categoria.capitalize(),
            valor_mensal=Decimal(valor),
            inicio_competencia=inicio,
            fim_competencia=fim,
        )
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


def _competencia_atual():
    from app.financeiro_calc import hoje_portal

    return hoje_portal().strftime("%Y-%m")


# --- Despesa fixa do mês -----------------------------------------------------


def test_soma_despesas_vigentes_no_mes():
    _despesa("6000", inicio="2026-01", categoria="aluguel")
    _despesa("9400", inicio="2026-01", categoria="salarios")
    db = SessionLocal()
    try:
        assert despesa_fixa_do_mes(db, "loja-teste", "2026-08") == Decimal("15400.00")
    finally:
        db.close()


def test_despesa_fora_da_vigencia_nao_conta():
    _despesa("6000", inicio="2026-09")  # começa depois
    _despesa("1000", inicio="2026-01", fim="2026-07")  # terminou antes
    db = SessionLocal()
    try:
        assert despesa_fixa_do_mes(db, "loja-teste", "2026-08") == Decimal("0.00")
    finally:
        db.close()


def test_ajuste_do_mes_substitui_o_valor_recorrente():
    despesa_id = _despesa("1200", inicio="2026-01", categoria="energia")
    db = SessionLocal()
    try:
        db.add(
            DespesaFixaAjuste(
                despesa_id=despesa_id, competencia="2026-08", valor=Decimal("1850")
            )
        )
        db.commit()
        assert despesa_fixa_do_mes(db, "loja-teste", "2026-08") == Decimal("1850.00")
        # O cadastro segue intacto: outro mês usa o valor recorrente.
        assert despesa_fixa_do_mes(db, "loja-teste", "2026-07") == Decimal("1200.00")
    finally:
        db.close()


def test_despesa_de_outra_loja_nao_entra():
    _despesa("5000", loja="outra-loja")
    db = SessionLocal()
    try:
        assert despesa_fixa_do_mes(db, "loja-teste", "2026-08") == Decimal("0.00")
    finally:
        db.close()


# --- Resultado do mês --------------------------------------------------------


def test_resultado_completo_calcula_lucro_operacional_e_ponto_de_equilibrio():
    mes = _competencia_atual()
    for _ in range(4):
        _venda("14900", "11200")
    _despesa("6000", inicio="2020-01")

    db = SessionLocal()
    try:
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.receita == Decimal("59600.00")
    assert r.custo_vendas == Decimal("44800.00")
    assert r.lucro_bruto == Decimal("14800.00")
    assert r.margem_completa is True
    assert r.despesa_fixa == Decimal("6000.00")
    assert r.lucro_operacional == Decimal("8800.00")
    # margem média 3700 → 6000/3700 = 1,62 → 2 motos
    assert r.ponto_equilibrio == 2
    assert r.ponto_equilibrio_disponivel is True


def test_venda_sem_custo_deixa_margem_incompleta_e_suprime_ponto_de_equilibrio():
    """Não se calcula ponto de equilíbrio sobre margem parcial."""
    mes = _competencia_atual()
    _venda("14900", "11200")
    _venda("20000", None)
    _despesa("6000", inicio="2020-01")

    db = SessionLocal()
    try:
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.margem_completa is False
    assert r.vendas_sem_custo == 1
    assert r.lucro_bruto == Decimal("3700.00")  # subtotal conhecido
    assert r.lucro_operacional is None
    assert r.ponto_equilibrio_disponivel is False
    assert r.ponto_equilibrio is None


def test_mes_sem_venda_nao_devolve_zero_no_ponto_de_equilibrio():
    mes = _competencia_atual()
    _despesa("6000", inicio="2020-01")
    db = SessionLocal()
    try:
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.qtd_vendas == 0
    assert r.ponto_equilibrio is None
    assert r.ponto_equilibrio_disponivel is False


def test_sem_despesa_cadastrada_avisa_em_vez_de_fingir_estrutura_zero():
    mes = _competencia_atual()
    _venda("14900", "11200")
    db = SessionLocal()
    try:
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.despesa_fixa == Decimal("0.00")
    assert r.tem_despesa_cadastrada is False
    assert r.lucro_operacional == r.lucro_bruto
    assert r.ponto_equilibrio_disponivel is False


def test_margem_media_negativa_nao_vira_ponto_de_equilibrio():
    """Nenhuma quantidade de motos com margem negativa paga a estrutura."""
    mes = _competencia_atual()
    _venda("10000", "12000")
    _despesa("6000", inicio="2020-01")

    db = SessionLocal()
    try:
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.lucro_bruto == Decimal("-2000.00")
    assert r.ponto_equilibrio is None
    assert r.ponto_equilibrio_disponivel is False


def test_venda_excluida_fica_fora_de_tudo():
    mes = _competencia_atual()
    _venda("14900", "11200")
    _venda("99000", "10000", status="excluida")

    db = SessionLocal()
    try:
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.qtd_vendas == 1
    assert r.receita == Decimal("14900.00")


def test_custos_diretos_saem_da_margem_da_moto():
    from app.models import VendaCustoDireto

    mes = _competencia_atual()
    venda_id = _venda("14900", "11200")
    db = SessionLocal()
    try:
        db.add(
            VendaCustoDireto(venda_id=venda_id, categoria="frete", valor=Decimal("650"))
        )
        db.commit()
        r = resultado_financeiro_mes(db, "loja-teste", mes)
    finally:
        db.close()

    assert r.custos_diretos == Decimal("650.00")
    assert r.lucro_bruto == Decimal("3050.00")
    assert r.linhas[0].lucro == Decimal("3050.00")
