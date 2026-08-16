"""Resultado financeiro da loja: lucro por moto e lucro operacional do mês.

Dois níveis que **não se misturam** (decisão do dono, 2026-08-16):

1. **Por moto — lucro bruto.** ``preço − custo do veículo − custos diretos``.
   Número real, rastreável até um lançamento.
2. **Pelo mês — lucro operacional.** ``lucro bruto do mês − despesa fixa``.
   Sem vínculo com venda nenhuma.

A despesa fixa **não é rateada** por moto. Jogar estrutura em cima da unidade
(custeio por absorção) faria o lucro de uma moto depender de quantas outras
foram vendidas no mês e mudar retroativamente a cada venda nova — e faria o
lojista recusar negócio bom. O que responde a intuição por trás do rateio é o
**ponto de equilíbrio**: quantas motos pagam a casa.

Regra de indisponibilidade, igual ao resto do Revy: fonte incompleta →
indisponível, nunca zero e nunca estimativa. Ver ``_ponto_equilibrio``.

A cifra deste módulo é de dono/gerente. Quem chama aplica o gate
(``Module.FINANCEIRO`` + papel); aqui não há checagem de permissão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.financeiro_calc import CENTAVOS, _data, hoje_portal, lucro_bruto_venda
from app.models import DespesaFixaAjuste, DespesaFixaLoja, Venda

CATEGORIAS_DESPESA = (
    "aluguel",
    "salarios",
    "contador",
    "energia",
    "marketing",
    "outros",
)

ZERO = Decimal("0.00")


def _q(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def competencia_atual() -> str:
    return hoje_portal().strftime("%Y-%m")


def competencia_valida(texto: str | None) -> str:
    """Normaliza 'YYYY-MM'; entrada inválida cai no mês corrente."""
    bruto = (texto or "").strip()
    if len(bruto) == 7 and bruto[4] == "-":
        try:
            ano, mes = int(bruto[:4]), int(bruto[5:])
        except ValueError:
            return competencia_atual()
        if 1900 <= ano <= 2999 and 1 <= mes <= 12:
            return f"{ano:04d}-{mes:02d}"
    return competencia_atual()


def intervalo_da_competencia(competencia: str) -> tuple[date, date]:
    ano, mes = int(competencia[:4]), int(competencia[5:])
    inicio = date(ano, mes, 1)
    fim = date(ano + (mes == 12), (mes % 12) + 1, 1)
    return inicio, fim


def _vigente(despesa: DespesaFixaLoja, competencia: str) -> bool:
    if despesa.inicio_competencia > competencia:
        return False
    return despesa.fim_competencia is None or despesa.fim_competencia >= competencia


def despesas_vigentes(
    db: Session, loja_slug: str, competencia: str
) -> list[tuple[DespesaFixaLoja, Decimal]]:
    """Despesas que valem no mês, com o valor efetivo (ajuste vence cadastro)."""
    cadastradas = (
        db.query(DespesaFixaLoja)
        .filter(DespesaFixaLoja.loja_slug == loja_slug)
        .order_by(DespesaFixaLoja.categoria, DespesaFixaLoja.descricao)
        .all()
    )
    vigentes = [d for d in cadastradas if _vigente(d, competencia)]
    if not vigentes:
        return []

    ajustes = {
        a.despesa_id: a.valor
        for a in db.query(DespesaFixaAjuste).filter(
            DespesaFixaAjuste.despesa_id.in_([d.id for d in vigentes]),
            DespesaFixaAjuste.competencia == competencia,
        )
    }
    return [(d, _q(ajustes.get(d.id, d.valor_mensal))) for d in vigentes]


def despesa_fixa_do_mes(db: Session, loja_slug: str, competencia: str) -> Decimal:
    itens = despesas_vigentes(db, loja_slug, competencia)
    return _q(sum((valor for _d, valor in itens), ZERO))


@dataclass(frozen=True)
class LinhaVenda:
    """Uma moto vendida no mês, com a margem dela."""

    venda_id: str
    descricao: str
    data: date
    preco: Decimal
    custo: Decimal | None
    custos_diretos: Decimal
    lucro: Decimal | None  # None quando o custo do veículo é desconhecido

    @property
    def custo_conhecido(self) -> bool:
        return self.custo is not None


@dataclass(frozen=True)
class ResultadoFinanceiro:
    competencia: str
    qtd_vendas: int
    receita: Decimal
    custo_vendas: Decimal
    custos_diretos: Decimal
    lucro_bruto: Decimal
    margem_completa: bool
    vendas_sem_custo: int
    despesa_fixa: Decimal
    tem_despesa_cadastrada: bool
    # None quando a margem está parcial: não se soma o que não se conhece.
    lucro_operacional: Decimal | None
    ponto_equilibrio: int | None
    ponto_equilibrio_disponivel: bool
    ponto_equilibrio_motivo: str | None
    margem_media: Decimal | None
    vendas_ate_equilibrio: int | None
    dia_do_equilibrio: date | None
    linhas: list[LinhaVenda] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "competencia": self.competencia,
            "qtd_vendas": self.qtd_vendas,
            "receita": str(self.receita),
            "lucro_bruto": str(self.lucro_bruto),
            "margem_completa": self.margem_completa,
            "despesa_fixa": str(self.despesa_fixa),
            "lucro_operacional": (
                str(self.lucro_operacional)
                if self.lucro_operacional is not None
                else None
            ),
            "ponto_equilibrio": self.ponto_equilibrio,
            "ponto_equilibrio_disponivel": self.ponto_equilibrio_disponivel,
        }


def _vendas_do_mes(db: Session, loja_slug: str, competencia: str) -> list[Venda]:
    """Confirmadas do mês, recortadas por ``criada_em``.

    ``criada_em`` e não ``confirmada_em`` de propósito: é o recorte que
    ``financeiro_calc.calcular_metricas_vendas`` já usa na tela Resultado. Duas
    telas da mesma Loja discordando sobre o mesmo mês é pior do que a Loja e o
    Control recortarem diferente (o Control usa ``confirmada_em``) — o lojista
    compara Resultado com Financeiro toda hora, e Control com Loja quase nunca.
    """
    inicio, fim = intervalo_da_competencia(competencia)
    return [
        v
        for v in db.query(Venda)
        .filter(Venda.loja_slug == loja_slug, Venda.status == "confirmada")
        .all()
        if inicio <= _data(v.criada_em) < fim
    ]


def _ponto_equilibrio(
    *,
    lucro_bruto: Decimal,
    qtd_vendas: int,
    despesa_fixa: Decimal,
    margem_completa: bool,
    tem_despesa_cadastrada: bool,
) -> tuple[int | None, bool, str | None, Decimal | None]:
    """Quantas motos pagam a estrutura do mês.

    Devolve ``(ponto, disponivel, motivo, margem_media)``. Cada indisponibilidade
    tem motivo próprio para a tela dizer o que falta em vez de mostrar traço.
    """
    if not margem_completa:
        return None, False, "margem_parcial", None
    if not tem_despesa_cadastrada:
        return None, False, "sem_despesa", None
    if qtd_vendas == 0:
        return None, False, "sem_venda", None

    margem_media = _q(lucro_bruto / qtd_vendas)
    if margem_media <= 0:
        # Nenhuma quantidade de motos com margem negativa paga a estrutura.
        return None, False, "margem_negativa", margem_media

    # Teto explícito: `//` de Decimal trunca em direção a zero (não é floor
    # como em int), então o truque `-(-a // b)` devolveria 1 onde o certo é 2.
    ponto = int(
        (despesa_fixa / margem_media).to_integral_value(rounding=ROUND_CEILING)
    )
    return ponto, True, None, margem_media


def resultado_financeiro_mes(
    db: Session, loja_slug: str, competencia: str | None = None
) -> ResultadoFinanceiro:
    competencia = competencia_valida(competencia)
    vendas = _vendas_do_mes(db, loja_slug, competencia)

    linhas: list[LinhaVenda] = []
    receita = custo_vendas = custos_diretos = ZERO
    lucro_bruto = ZERO
    sem_custo = 0

    for venda in sorted(vendas, key=lambda v: _data(v.criada_em)):
        diretos = _q(sum((c.valor for c in venda.custos_diretos), ZERO))
        lucro = lucro_bruto_venda(venda)
        receita += venda.preco_venda
        custos_diretos += diretos
        if venda.custo_veiculo is None:
            sem_custo += 1
        else:
            custo_vendas += venda.custo_veiculo
            lucro_bruto += lucro
        linhas.append(
            LinhaVenda(
                venda_id=venda.id,
                descricao=venda.descricao,
                data=_data(venda.criada_em),
                preco=_q(venda.preco_venda),
                custo=_q(venda.custo_veiculo) if venda.custo_veiculo is not None else None,
                custos_diretos=diretos,
                lucro=_q(lucro) if lucro is not None else None,
            )
        )

    margem_completa = sem_custo == 0
    itens_despesa = despesas_vigentes(db, loja_slug, competencia)
    despesa_fixa = _q(sum((valor for _d, valor in itens_despesa), ZERO))
    tem_despesa = bool(itens_despesa)

    ponto, disponivel, motivo, margem_media = _ponto_equilibrio(
        lucro_bruto=_q(lucro_bruto),
        qtd_vendas=len(vendas),
        despesa_fixa=despesa_fixa,
        margem_completa=margem_completa,
        tem_despesa_cadastrada=tem_despesa,
    )

    # Lucro operacional só existe se a margem estiver completa: subtrair
    # despesa de um lucro bruto que já é subtotal produziria um número que
    # parece resultado e não é.
    lucro_operacional = _q(lucro_bruto - despesa_fixa) if margem_completa else None

    vendas_ate, dia = _cruzamento_do_equilibrio(linhas, despesa_fixa, disponivel)

    return ResultadoFinanceiro(
        competencia=competencia,
        qtd_vendas=len(vendas),
        receita=_q(receita),
        custo_vendas=_q(custo_vendas),
        custos_diretos=_q(custos_diretos),
        lucro_bruto=_q(lucro_bruto),
        margem_completa=margem_completa,
        vendas_sem_custo=sem_custo,
        despesa_fixa=despesa_fixa,
        tem_despesa_cadastrada=tem_despesa,
        lucro_operacional=lucro_operacional,
        ponto_equilibrio=ponto,
        ponto_equilibrio_disponivel=disponivel,
        ponto_equilibrio_motivo=motivo,
        margem_media=margem_media,
        vendas_ate_equilibrio=vendas_ate,
        dia_do_equilibrio=dia,
        linhas=linhas,
    )


def _cruzamento_do_equilibrio(
    linhas: list[LinhaVenda], despesa_fixa: Decimal, disponivel: bool
) -> tuple[int | None, date | None]:
    """Em que venda (e em que dia) o mês passou a pagar a estrutura.

    Só faz sentido quando o ponto de equilíbrio existe — com margem parcial o
    acumulado é subtotal e cruzaria cedo demais.
    """
    if not disponivel:
        return None, None
    acumulado = ZERO
    for i, linha in enumerate(linhas, start=1):
        if linha.lucro is None:
            continue
        acumulado += linha.lucro
        if acumulado >= despesa_fixa:
            return i, linha.data
    return None, None
