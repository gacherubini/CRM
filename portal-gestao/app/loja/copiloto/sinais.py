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


def regra_preco_fora_da_faixa(
    veiculos_com_fipe: Any,
    *,
    folga_alta: float,
    folga_base: float,
    dias_parado_min: int,
) -> list[SinalCandidato]:
    """Preço muito acima da FIPE, ou acima e encalhado — capital preso.

    Recebe pares ``(veiculo, valor_fipe)`` JÁ RESOLVIDOS — esta regra não
    consulta a FIPE. Quem busca, aplica o teto por ciclo e decide quais
    veículos entram na lista é o worker (``app/copiloto_sinais_job.py``); ele
    só inclui aqui veículos com match exato e confirmado (status ``ok``).
    Ambíguo, não encontrado ou indisponível nunca chegam com ``valor_fipe``
    preenchido — e sem valor, esta função não tem o que decidir e pula o
    veículo (defesa também útil para o caso raro de o chamador passar
    ``None`` por engano).

    Estar acima da FIPE, sozinho, é normal — decisão do dono (2026-08-12:
    "na FIPE é normal estar acima"). Alertar em qualquer centavo acima seria
    ruído em cima do estoque inteiro. Por isso dois gatilhos, nunca "qualquer
    centavo acima":

    1. **Muito acima, sozinho**: preço >= FIPE * (1 + ``folga_alta``). Destoa
       o bastante para valer aviso mesmo em veículo recém-cadastrado.
    2. **Acima + encalhado**: preço >= FIPE * (1 + ``folga_base``) E parado
       há >= ``dias_parado_min`` dias. Nenhuma das duas condições sozinha
       merece alerta; juntas são a definição de capital preso.

    Preço abaixo da FIPE nunca dispara nesta fase — pode ser giro deliberado
    do dono, e opinar sobre isso é opinar sobre a operação dele.

    Severidade: "critico" no caso 2 (preço alto em veículo parado há meses é
    dinheiro dormindo), "atencao" no caso 1 (preço alto sozinho é decisão
    comercial recente, ainda não é capital preso).
    """
    saida: list[SinalCandidato] = []
    for par in veiculos_com_fipe or ():
        veiculo, valor_fipe = par
        if valor_fipe is None:
            continue
        preco = getattr(veiculo, "preco", None)
        if preco is None:
            continue
        valor_fipe = Decimal(str(valor_fipe))
        preco = Decimal(str(preco))
        if valor_fipe <= 0 or preco < valor_fipe:
            continue

        dias_parado = int(getattr(veiculo, "dias_parado", 0) or 0)
        limite_alto = valor_fipe * (Decimal("1") + Decimal(str(folga_alta)))
        limite_base = valor_fipe * (Decimal("1") + Decimal(str(folga_base)))
        muito_acima = preco >= limite_alto
        acima_e_encalhado = preco >= limite_base and dias_parado >= dias_parado_min
        if not muito_acima and not acima_e_encalhado:
            continue

        severidade = "critico" if acima_e_encalhado else "atencao"
        veiculo_id = getattr(veiculo, "id", None)
        descricao = getattr(veiculo, "descricao", None) or "Veículo"
        pct_acima = (preco / valor_fipe - 1) * 100
        pct_txt = f"{pct_acima:.0f}%"

        if acima_e_encalhado:
            titulo = (
                f"{descricao} está {pct_txt} acima da FIPE e parado há "
                f"{dias_parado} dias"
            )
            detalhe = (
                f"{_brl(preco)} contra {_brl(valor_fipe)} da FIPE, e o veículo "
                "já está parado tempo suficiente para isso pesar. Vale revisar "
                "o preço."
            )
        else:
            titulo = f"{descricao} está {pct_txt} acima da FIPE"
            detalhe = (
                f"{_brl(preco)} contra {_brl(valor_fipe)} da FIPE. Acima da "
                "FIPE pode ser decisão comercial — vale só confirmar que é "
                "intencional."
            )

        saida.append(
            SinalCandidato(
                regra="preco_fora_da_faixa",
                severidade=severidade,
                entidade_ref=veiculo_id,
                titulo=titulo,
                detalhe=detalhe,
                dados={
                    "veiculo_id": veiculo_id,
                    "preco": str(preco),
                    "valor_fipe": str(valor_fipe),
                    "pct_acima": float(pct_acima.quantize(Decimal("0.1"))),
                    "dias_parado": dias_parado,
                    "encalhado": acima_e_encalhado,
                },
                acao_sugerida={"acao": "ajustar_preco", "veiculo_id": veiculo_id},
            )
        )
    return saida


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
