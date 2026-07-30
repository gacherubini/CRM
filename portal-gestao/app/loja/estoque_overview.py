"""Read model determinístico da visão geral de Estoque (Revy Loja Fase 2).

Regras:
- Contagens vêm do campo ``status`` do veículo (disponivel / reservado / vendido).
- Faixas de idade usam ``criado_em`` (ou ``entrada``); se nenhum veículo tiver
  data, ``idade`` fica ``None`` — não se inventam zeros.
- Lacunas listam ids/placas limitados (sem preço, sem foto, campos obrigatórios).
- Reservas/vendas recentes usam ``atualizado_em`` quando existir; lista vazia
  se a API não expuser timestamps (nunca métricas falsas).
- Status ``erro``: contagens e idade são ``None`` (API falhou).
- Status ``vazio``: API ok, zero veículos.
- Status ``ok``: há veículos e agregados confiáveis.
- Status ``parcial``: há veículos, mas alguma fatia opcional não pôde ser montada
  (ex.: nenhuma data de entrada para idade, sem inventar faixas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.loja.types import StatusReadModel

# Campos mínimos que o cadastro operacional espera preenchidos.
CAMPOS_OBRIGATORIOS = ("tipo", "marca", "modelo", "ano_modelo")

# Limites de UI — evita tabelas enormes na visão geral.
LIMITE_LACUNAS_PADRAO = 20
LIMITE_RECENTES_PADRAO = 10

# Faixas de idade em dias (estoque parado: disponível + reservado).
FAIXA_ATE_30 = 30
FAIXA_ATE_60 = 60
FAIXA_ATE_90 = 90


@dataclass(frozen=True)
class ContagensEstoque:
    """Totais por status — fórmulas explícitas e testáveis."""

    disponivel: int
    reservado: int
    vendido: int
    indisponivel: int
    publicados: int
    total: int


@dataclass(frozen=True)
class FaixasIdade:
    """Distribuição de idade do estoque ativo (disponível + reservado)."""

    ate_30: int
    de_31_a_60: int
    de_61_a_90: int
    acima_90: int
    com_data: int
    sem_data: int


@dataclass(frozen=True)
class LacunaCadastro:
    id: str
    placa: str | None
    marca: str
    modelo: str
    status: str
    faltas: tuple[str, ...]


@dataclass(frozen=True)
class EventoRecente:
    """Reserva ou venda recente derivada do veículo (sem inventar histórico)."""

    id: str
    tipo: str  # "reserva" | "venda"
    placa: str | None
    marca: str
    modelo: str
    status: str
    atualizado_em: str | None


@dataclass(frozen=True)
class EstoqueOverview:
    status: StatusReadModel
    contagens: ContagensEstoque | None
    idade: FaixasIdade | None
    lacunas: tuple[LacunaCadastro, ...] = field(default_factory=tuple)
    recentes: tuple[EventoRecente, ...] = field(default_factory=tuple)
    erro: str | None = None
    total_lacunas: int = 0
    # Flag de apresentação (RBAC); o read model em si não esconde números de
    # custo — a UI omite campos de custo/margem quando False.
    pode_ver_custo: bool = False


def _parse_dt(valor: Any) -> datetime | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str):
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _data_entrada(veiculo: dict) -> datetime | None:
    """Preferência: criado_em → entrada → None."""
    return _parse_dt(veiculo.get("criado_em")) or _parse_dt(veiculo.get("entrada"))


def _preco_ausente(veiculo: dict) -> bool:
    preco = veiculo.get("preco")
    if preco is None or preco == "":
        return True
    try:
        return float(preco) <= 0
    except (TypeError, ValueError):
        return True


def _foto_ausente(veiculo: dict) -> bool:
    if veiculo.get("tem_foto") is True:
        return False
    if veiculo.get("foto_url"):
        return False
    fotos = veiculo.get("fotos") or veiculo.get("midias") or []
    return not bool(fotos)


def _faltas_obrigatorias(veiculo: dict) -> list[str]:
    faltas: list[str] = []
    for campo in CAMPOS_OBRIGATORIOS:
        valor = veiculo.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            faltas.append(campo)
    if _preco_ausente(veiculo):
        faltas.append("preco")
    if _foto_ausente(veiculo):
        faltas.append("foto")
    return faltas


def _rotulo(veiculo: dict, chave: str, padrao: str = "—") -> str:
    valor = veiculo.get(chave)
    if valor is None or valor == "":
        return padrao
    return str(valor)


def _contar(veiculos: list[dict]) -> ContagensEstoque:
    disponivel = sum(1 for v in veiculos if v.get("status") == "disponivel")
    reservado = sum(1 for v in veiculos if v.get("status") == "reservado")
    vendido = sum(1 for v in veiculos if v.get("status") == "vendido")
    indisponivel = sum(1 for v in veiculos if v.get("status") == "indisponivel")
    publicados = sum(1 for v in veiculos if bool(v.get("publicado")))
    return ContagensEstoque(
        disponivel=disponivel,
        reservado=reservado,
        vendido=vendido,
        indisponivel=indisponivel,
        publicados=publicados,
        total=len(veiculos),
    )


def _faixas_idade(
    veiculos: list[dict],
    agora: datetime,
) -> FaixasIdade | None:
    """Idade do estoque ativo. Retorna None se nenhum veículo tiver data."""
    ativos = [
        v
        for v in veiculos
        if v.get("status") in {"disponivel", "reservado"}
    ]
    if not ativos:
        # Sem estoque ativo: faixas zeradas só fazem sentido se há datas em
        # algum ativo — sem ativos, omitimos o bloco de idade.
        return None

    ate_30 = de_31_a_60 = de_61_a_90 = acima_90 = 0
    com_data = sem_data = 0
    ref = agora if agora.tzinfo else agora.replace(tzinfo=timezone.utc)

    for v in ativos:
        entrada = _data_entrada(v)
        if entrada is None:
            sem_data += 1
            continue
        com_data += 1
        dias = max(0, (ref - entrada).days)
        if dias <= FAIXA_ATE_30:
            ate_30 += 1
        elif dias <= FAIXA_ATE_60:
            de_31_a_60 += 1
        elif dias <= FAIXA_ATE_90:
            de_61_a_90 += 1
        else:
            acima_90 += 1

    if com_data == 0:
        # Dados existem mas sem timestamps — não inventar distribuição.
        return None

    return FaixasIdade(
        ate_30=ate_30,
        de_31_a_60=de_31_a_60,
        de_61_a_90=de_61_a_90,
        acima_90=acima_90,
        com_data=com_data,
        sem_data=sem_data,
    )


def _lacunas(
    veiculos: list[dict],
    limite: int,
) -> tuple[tuple[LacunaCadastro, ...], int]:
    itens: list[LacunaCadastro] = []
    total = 0
    for v in veiculos:
        # Lacunas importam no estoque vivo; vendidos não entram na pendência.
        if v.get("status") == "vendido":
            continue
        faltas = _faltas_obrigatorias(v)
        if not faltas:
            continue
        total += 1
        if len(itens) >= limite:
            continue
        itens.append(
            LacunaCadastro(
                id=str(v.get("id") or ""),
                placa=(str(v["placa"]) if v.get("placa") else None),
                marca=_rotulo(v, "marca"),
                modelo=_rotulo(v, "modelo"),
                status=str(v.get("status") or ""),
                faltas=tuple(faltas),
            )
        )
    return tuple(itens), total


def _recentes(
    veiculos: list[dict],
    limite: int,
) -> tuple[EventoRecente, ...]:
    candidatos: list[tuple[datetime | None, EventoRecente]] = []
    for v in veiculos:
        status = v.get("status")
        if status == "reservado":
            tipo = "reserva"
        elif status == "vendido":
            tipo = "venda"
        else:
            continue
        atualizado = _parse_dt(v.get("atualizado_em")) or _data_entrada(v)
        candidatos.append(
            (
                atualizado,
                EventoRecente(
                    id=str(v.get("id") or ""),
                    tipo=tipo,
                    placa=(str(v["placa"]) if v.get("placa") else None),
                    marca=_rotulo(v, "marca"),
                    modelo=_rotulo(v, "modelo"),
                    status=str(status),
                    atualizado_em=(
                        atualizado.isoformat() if atualizado is not None else None
                    ),
                ),
            )
        )

    # Ordena por data desc; sem data vai para o fim (ainda listamos o que a
    # API devolveu — não inventamos timestamps).
    def _chave(item: tuple[datetime | None, EventoRecente]):
        dt, _ = item
        if dt is None:
            return (1, datetime.min.replace(tzinfo=timezone.utc))
        return (0, -dt.timestamp())

    candidatos.sort(key=_chave)
    return tuple(ev for _, ev in candidatos[:limite])


def montar_estoque_overview(
    veiculos: list[dict] | None,
    *,
    erro: str | None = None,
    agora: datetime | None = None,
    limite_lacunas: int = LIMITE_LACUNAS_PADRAO,
    limite_recentes: int = LIMITE_RECENTES_PADRAO,
    pode_ver_custo: bool = False,
) -> EstoqueOverview:
    """Agrega veículos da Estoque API em um overview determinístico.

    ``veiculos=None`` com ``erro`` → status erro (sem contagens).
    Lista vazia → status vazio (contagens zeradas reais da lista).
    """
    if erro and veiculos is None:
        return EstoqueOverview(
            status="erro",
            contagens=None,
            idade=None,
            lacunas=(),
            recentes=(),
            erro=erro,
            total_lacunas=0,
            pode_ver_custo=pode_ver_custo,
        )

    lista = list(veiculos or [])
    if not lista:
        return EstoqueOverview(
            status="vazio",
            contagens=_contar([]),
            idade=None,
            lacunas=(),
            recentes=(),
            erro=None,
            total_lacunas=0,
            pode_ver_custo=pode_ver_custo,
        )

    ref = agora or datetime.now(timezone.utc)
    contagens = _contar(lista)
    idade = _faixas_idade(lista, ref)
    lacunas, total_lacunas = _lacunas(lista, limite_lacunas)
    recentes = _recentes(lista, limite_recentes)

    # Parcial: há dados, mas idade omitida por falta de timestamps (bloco
    # opcional). Contagens e lacunas continuam confiáveis.
    ativos = [v for v in lista if v.get("status") in {"disponivel", "reservado"}]
    parcial = idade is None and bool(ativos)

    return EstoqueOverview(
        status="parcial" if parcial else "ok",
        contagens=contagens,
        idade=idade,
        lacunas=lacunas,
        recentes=recentes,
        erro=None,
        total_lacunas=total_lacunas,
        pode_ver_custo=pode_ver_custo,
    )
