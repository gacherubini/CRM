"""Consultas de estoque do Copiloto.

§3.7 do design: o ``EstoqueClient`` é instanciado com um token GLOBAL do
processo (``app/main.py:389``) e a ``estoque-api`` deriva o ``loja_id`` da
credencial (``estoque-api/app/auth.py:32-35``), não do pedido. Enquanto o
Portal for uma loja por deploy isso funciona; no dia do multi-loja, agiria na
loja errada em silêncio. Por isso toda consulta aqui passa por
``garantir_escopo_loja`` e FALHA FECHADO.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.clients.estoque import EstoqueIndisponivel
from app.loja.copiloto.prompt import rotular_conteudo_externo
from app.loja.copiloto.texto_externo import (
    sanitizar_texto_externo,
    truncar_com_reticencias,
)
from app.loja.copiloto.tipos import (
    STATUS_ERRO,
    STATUS_INDISPONIVEL,
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)
from app.loja.estoque_overview import _data_entrada

CENTAVOS = Decimal("0.01")

# Status que ainda prendem capital. Vendido/indisponível não são "parados".
STATUS_ATIVOS = frozenset({"disponivel", "reservado"})

# Descrição vai para o CONTEXTO DO MODELO (via to_dict() -> tool result),
# não direto para tela — por isso o limite é mais generoso que o rótulo do
# cartão (LIMITE_ROTULO=40 em cartao.py, que É tela). 200 ainda corta
# qualquer payload de injeção bem antes de caber uma frase de instrução.
LIMITE_DESCRICAO = 200

RESSALVA_IDADE = (
    "Dias contados a partir da data de cadastro no sistema, não da entrada "
    "física do veículo. Em estoque migrado a idade real pode ser maior."
)


class EscopoLojaDivergente(RuntimeError):
    """O estoque respondeu com dados de outra loja. Nunca seguir adiante."""


def garantir_escopo_loja(estoque: Any, loja_slug: str) -> None:
    """Confere que a credencial do estoque aponta para a loja da sessão."""
    dados = estoque.obter_loja() or {}
    slug = str(dados.get("slug") or "").strip().casefold()
    esperado = (loja_slug or "").strip().casefold()
    if not slug or slug != esperado:
        raise EscopoLojaDivergente(
            f"estoque respondeu pela loja {slug or '(vazio)'}, sessão é {esperado}"
        )


def _preco(veiculo: dict) -> Decimal | None:
    bruto = veiculo.get("preco")
    if bruto in (None, ""):
        return None
    try:
        valor = Decimal(str(bruto))
    except (ArithmeticError, ValueError):
        return None
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP) if valor > 0 else None


def _descricao(veiculo: dict) -> str:
    """Descrição de marca/modelo/versão/ano — texto de terceiro.

    Sanitizada (controle/bidi fora, espaço colapsado) e cortada em
    ``LIMITE_DESCRICAO`` como QUALQUER texto de terceiro nesta base. O
    rótulo "conteúdo não confiável" (``rotular_conteudo_externo``) é
    aplicado só na fronteira de serialização para o modelo
    (``VeiculoParado.to_dict``), não aqui: este valor também alimenta
    ``sinais.py`` (título mostrado direto ao dono), que não pode carregar
    tags `<CONTEUDO_NAO_CONFIAVEL>` literais na tela.
    """
    partes = [
        sanitizar_texto_externo(str(veiculo.get(campo)))
        for campo in ("marca", "modelo", "versao", "ano_modelo")
        if veiculo.get(campo) not in (None, "")
    ]
    partes = [p for p in partes if p]
    texto = " ".join(partes) or str(veiculo.get("id") or "veículo")
    return truncar_com_reticencias(texto, LIMITE_DESCRICAO)


@dataclass(frozen=True)
class VeiculoParado:
    id: str
    descricao: str
    placa: str | None
    preco: Decimal | None
    dias_parado: int
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            # Aqui, e só aqui, o texto de terceiro entra no contexto do
            # modelo (§6.3, defesa 1): rotulado e delimitado como conteúdo
            # não confiável antes de virar JSON de retorno de ferramenta.
            "descricao": rotular_conteudo_externo(self.descricao),
            "placa": self.placa,
            "preco": None if self.preco is None else str(self.preco),
            "dias_parado": self.dias_parado,
            "status": self.status,
        }


@dataclass(frozen=True)
class EstoqueParado:
    status: str
    dias_min: int
    itens: tuple[VeiculoParado, ...]
    total: int | None
    capital_preso: Decimal | None
    cobertura_data: Cobertura
    ressalva: str
    erro: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dias_min": self.dias_min,
            "itens": [i.to_dict() for i in self.itens],
            "total": self.total,
            "capital_preso": (
                None if self.capital_preso is None else str(self.capital_preso)
            ),
            "cobertura_data": self.cobertura_data.to_dict(),
            "ressalva": self.ressalva,
            "erro": self.erro,
        }


def _vazio(status: str, dias_min: int, erro: str | None = None) -> EstoqueParado:
    return EstoqueParado(
        status=status,
        dias_min=dias_min,
        itens=(),
        total=None,
        capital_preso=None,
        cobertura_data=Cobertura(com_dado=0, total=0),
        ressalva=RESSALVA_IDADE,
        erro=erro,
    )


def estoque_parado(
    estoque: Any,
    ctx: CopilotoContexto,
    *,
    dias_min: int = 30,
    limite: int = 20,
    agora: datetime | None = None,
) -> EstoqueParado:
    """Veículos parados além do limiar, com dias e capital preso."""
    try:
        garantir_escopo_loja(estoque, ctx.loja_slug)
    except EscopoLojaDivergente as exc:
        return _vazio(STATUS_ERRO, dias_min, erro=str(exc))
    except EstoqueIndisponivel:
        return _vazio(STATUS_INDISPONIVEL, dias_min)

    try:
        veiculos = estoque.listar()
    except EstoqueIndisponivel:
        return _vazio(STATUS_INDISPONIVEL, dias_min)

    ref = agora or datetime.now(timezone.utc)
    ativos = [v for v in (veiculos or []) if v.get("status") in STATUS_ATIVOS]

    com_data = 0
    parados: list[VeiculoParado] = []
    for v in ativos:
        entrada = _data_entrada(v)
        if entrada is None:
            # Sem data não vira "0 dias parado": vira buraco de cobertura.
            continue
        com_data += 1
        dias = max(0, (ref - entrada).days)
        if dias < dias_min:
            continue
        parados.append(
            VeiculoParado(
                id=str(v.get("id") or ""),
                descricao=_descricao(v),
                placa=(str(v["placa"]) if v.get("placa") else None),
                preco=_preco(v),
                dias_parado=dias,
                status=str(v.get("status") or ""),
            )
        )

    parados.sort(key=lambda i: (-i.dias_parado, i.id))
    cobertura = Cobertura(com_dado=com_data, total=len(ativos))
    capital = sum(
        (i.preco for i in parados if i.preco is not None), Decimal("0")
    ).quantize(CENTAVOS, rounding=ROUND_HALF_UP)

    if not parados:
        status = STATUS_PARCIAL if cobertura.parcial else STATUS_VAZIO
    else:
        status = STATUS_PARCIAL if cobertura.parcial else STATUS_OK

    return EstoqueParado(
        status=status,
        dias_min=dias_min,
        itens=tuple(parados[: max(1, limite)]),
        total=len(parados),
        capital_preso=capital,
        cobertura_data=cobertura,
        ressalva=RESSALVA_IDADE,
    )
