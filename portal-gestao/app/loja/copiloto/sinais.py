"""Regras determinísticas de alerta. O LLM não participa.

Cada regra é uma função PURA: recebe um read model já montado e devolve
candidatos a sinal. Quem busca dado é o worker (``app/copiloto_sinais_job.py``);
quem persiste e aplica cooldown é ``sinais_store.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CENTAVOS = Decimal("0.01")

DIAS_CRITICO_ESTOQUE = 120
LIMITE_PCT_META_RISCO = 0.85  # ritmo projetado abaixo de 85% do alvo


def _brl(valor: Decimal | None) -> str:
    if valor is None:
        return "R$ 0,00"
    texto = f"{valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP):,.2f}"
    return "R$ " + texto.replace(",", "@").replace(".", ",").replace("@", ".")


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


@dataclass(frozen=True)
class SinalCandidato:
    regra: str
    severidade: str  # info | atencao | critico
    titulo: str
    detalhe: str
    entidade_ref: str | None = None
    dados: dict[str, Any] = field(default_factory=dict)
    acao_sugerida: dict[str, Any] | None = None


def regra_estoque_parado(parado: Any) -> list[SinalCandidato]:
    """Um sinal por veículo — o dono age veículo a veículo, não em lote."""
    if getattr(parado, "status", "") in {"erro", "indisponivel"}:
        return []
    saida: list[SinalCandidato] = []
    for item in getattr(parado, "itens", ()) or ():
        severidade = "critico" if item.dias_parado >= DIAS_CRITICO_ESTOQUE else "atencao"
        saida.append(
            SinalCandidato(
                regra="estoque_parado",
                severidade=severidade,
                entidade_ref=item.id,
                titulo=f"{item.descricao} parada há {item.dias_parado} dias",
                detalhe=(
                    f"{_brl(item.preco)} de capital preso neste veículo. "
                    "Vale revisar o preço."
                ),
                dados={
                    "veiculo_id": item.id,
                    "dias_parado": item.dias_parado,
                    "preco": None if item.preco is None else str(item.preco),
                    "ressalva": getattr(parado, "ressalva", ""),
                },
                acao_sugerida={"acao": "ajustar_preco", "veiculo_id": item.id},
            )
        )
    return saida


def regra_lead_sem_resposta(leads: Any) -> list[SinalCandidato]:
    """Agregado: nunca guarda telefone, nem em hash — o link leva à fila."""
    total = getattr(leads, "sem_resposta", None)
    if not total:
        return []
    horas = getattr(leads, "horas_sem_resposta", 4)
    return [
        SinalCandidato(
            regra="lead_sem_resposta",
            severidade="critico",
            titulo=(
                f"{total} {_plural(total, 'lead', 'leads')} "
                f"há mais de {horas}h sem resposta"
            ),
            detalhe=(
                "Estão em atendimento humano e a última mensagem é do cliente."
            ),
            dados={"sem_resposta": total, "horas": horas},
            acao_sugerida={"acao": "abrir", "href": "/app/loja/atendimento"},
        )
    ]


def regra_meta_em_risco(
    metas: list[dict],
    janela: Any,
    *,
    hoje: date,
) -> list[SinalCandidato]:
    """Dispara quando o ritmo do período projeta abaixo do alvo."""
    dias_restantes = max(0, (janela.fim - hoje).days + 1)
    decorridos = max(1, (hoje - janela.inicio).days + 1)
    saida: list[SinalCandidato] = []
    for meta in metas or []:
        if meta.get("indisponivel"):
            continue
        alvo = meta.get("alvo")
        realizado = meta.get("realizado")
        if alvo in (None, 0) or realizado is None:
            continue
        alvo = Decimal(str(alvo))
        realizado = Decimal(str(realizado))
        if realizado >= alvo:
            continue
        projetado = realizado / Decimal(decorridos) * Decimal(janela.dias)
        if projetado >= alvo * Decimal(str(LIMITE_PCT_META_RISCO)):
            continue
        falta = (alvo - realizado).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        saida.append(
            SinalCandidato(
                regra="meta_em_risco",
                severidade="atencao",
                entidade_ref=str(meta.get("tipo") or ""),
                titulo=(
                    f"Faltam {dias_restantes} "
                    f"{_plural(dias_restantes, 'dia', 'dias')} e {_brl(falta)} "
                    "para bater a meta"
                ),
                detalhe=(
                    f"No ritmo atual o período fecha em {_brl(projetado)} "
                    f"de {_brl(alvo)}."
                ),
                dados={
                    "tipo": meta.get("tipo"),
                    "alvo": str(alvo.quantize(CENTAVOS)),
                    "realizado": str(realizado.quantize(CENTAVOS)),
                    "falta": str(falta),
                    "projetado": str(projetado.quantize(CENTAVOS)),
                    "dias_restantes": dias_restantes,
                },
            )
        )
    return saida


def regra_margem_incompleta(vendas: Any) -> list[SinalCandidato]:
    cobertura = getattr(vendas, "cobertura_margem", None)
    if cobertura is None or not cobertura.parcial:
        return []
    sem_custo = cobertura.total - cobertura.com_dado
    return [
        SinalCandidato(
            regra="margem_incompleta",
            severidade="atencao",
            titulo=(
                f"{sem_custo} de {cobertura.total} "
                f"{_plural(cobertura.total, 'venda', 'vendas')} sem custo informado"
            ),
            detalhe="Sua margem está subestimada enquanto o custo não entrar.",
            dados={
                "sem_custo": sem_custo,
                "com_custo": cobertura.com_dado,
                "total": cobertura.total,
            },
            acao_sugerida={"acao": "abrir", "href": "/app/loja/vendas/lista"},
        )
    ]


def regra_cadastro_incompleto(overview_estoque: Any) -> list[SinalCandidato]:
    total = int(getattr(overview_estoque, "total_lacunas", 0) or 0)
    if total <= 0:
        return []
    return [
        SinalCandidato(
            regra="cadastro_incompleto",
            severidade="info",
            titulo=(
                f"{total} {_plural(total, 'veículo', 'veículos')} "
                "com cadastro incompleto"
            ),
            detalhe="Falta foto ou dado obrigatório — some da vitrine e do bot.",
            dados={"total": total},
            acao_sugerida={"acao": "abrir", "href": "/app/loja/estoque"},
        )
    ]


def regra_atribuicao_baixa(
    origem: Any,
    *,
    minimo_vendas: int = 3,
    limite_pct: float = 30.0,
) -> list[SinalCandidato]:
    """Transforma a fraqueza da atribuição em produto (§4.2).

    Em vez de o buraco ficar invisível, o dono é avisado — e fechar a cadeia
    melhora o dado que sustenta o fosso do Revy.
    """
    cobertura = getattr(origem, "cobertura", None)
    if cobertura is None or cobertura.total < minimo_vendas:
        return []
    sem_origem = cobertura.total - cobertura.com_dado
    if sem_origem <= 0:
        return []
    pct = sem_origem / cobertura.total * 100
    if pct < limite_pct:
        return []
    return [
        SinalCandidato(
            regra="atribuicao_baixa",
            severidade="atencao",
            titulo=(
                f"{sem_origem} de {cobertura.total} vendas sem campanha de origem"
            ),
            detalhe="Seu ROI está incompleto: essas vendas não voltam para nenhum anúncio.",
            dados={
                "sem_origem": sem_origem,
                "com_origem": cobertura.com_dado,
                "total": cobertura.total,
                "pct_sem_origem": round(pct, 1),
            },
        )
    ]
