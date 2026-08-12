"""Execução das ações propostas pelo Copiloto.

A ação NUNCA é executada pelo turno do LLM. O modelo propõe; isto aqui roda
depois do clique humano, com sete guardas server-side.

A guarda 5 (releitura antes do PATCH) existe porque o PATCH da estoque-api
não tem idempotência nem If-Match/ETag (Idempotency-Key só existe no POST de
criação, ``estoque-api/app/main.py:204``). Sem ela, o Copiloto sobrescreve em
silêncio a alteração que outra pessoa fez dois segundos antes.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.clients.estoque import (
    ConflitoEstoque,
    EstoqueIndisponivel,
    VeiculoNaoEncontrado,
)
from app.config import settings
from app.loja.copiloto.consultas_estoque import (
    EscopoLojaDivergente,
    garantir_escopo_loja,
)
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja_operacao_auditoria import registrar_auditoria_copiloto
from app.models import CopilotoAcao

logger = logging.getLogger("portal.copiloto.acoes")

CENTAVOS = Decimal("0.01")
ACOES_PERMITIDAS = frozenset({"ajustar_preco", "repostar_veiculo", "publicar_veiculo", "despublicar_veiculo"})

# Cada ação diz ao Estoque EXATAMENTE o verbo dela. Um "else" que assume
# "publicar" faz despublicar_veiculo publicar o veículo — o oposto do que o
# dono confirmou no cartão.
VERBO_ESTOQUE = {
    "repostar_veiculo": "publicar",
    "publicar_veiculo": "publicar",
    "despublicar_veiculo": "despublicar",
}


class AcaoRecusada(RuntimeError):
    def __init__(self, code: str, mensagem: str):
        super().__init__(mensagem)
        self.code = code


def _dec(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError):
        return None


def _max_acoes_hora() -> int:
    try:
        return int(os.getenv("PORTAL_COPILOTO_MAX_ACOES_HORA", "20"))
    except ValueError:
        return 20


def validar_ajuste_preco(preco_atual: Decimal, preco_novo: Decimal) -> Decimal:
    """Banda de ±X% e piso. "preço > 0" deixa passar R$ 1 — não basta."""
    novo = _dec(preco_novo)
    atual = _dec(preco_atual)
    if novo is None or novo <= 0:
        raise AcaoRecusada("preco_invalido", "preço inválido")
    piso = Decimal(str(settings.copiloto_preco_minimo))
    if novo < piso:
        raise AcaoRecusada("piso", f"preço abaixo do piso de {piso}")
    if atual is None or atual <= 0:
        raise AcaoRecusada("preco_invalido", "preço atual desconhecido")
    banda = Decimal(str(settings.copiloto_banda_preco_pct)) / Decimal("100")
    minimo = (atual * (Decimal("1") - banda)).quantize(CENTAVOS)
    maximo = (atual * (Decimal("1") + banda)).quantize(CENTAVOS)
    if not (minimo <= novo <= maximo):
        raise AcaoRecusada(
            "banda",
            f"variação acima do limite permitido (de {minimo} a {maximo})",
        )
    return novo


def _checar_rate_limit(db: Session, loja_slug: str, agora: datetime) -> None:
    desde = agora - timedelta(hours=1)
    executadas = (
        db.query(CopilotoAcao)
        .filter(
            CopilotoAcao.loja_slug == loja_slug,
            CopilotoAcao.executada_em >= desde,
            CopilotoAcao.estado != "falhou",
        )
        .count()
    )
    if executadas >= _max_acoes_hora():
        raise AcaoRecusada("rate_limit", "limite de ações por hora atingido")


def executar_acao(
    db: Session,
    ctx: CopilotoContexto,
    *,
    acao: str,
    parametros: dict,
    estoque,
    turno_id: str | None = None,
    agora: datetime | None = None,
) -> CopilotoAcao:
    ref = agora or datetime.now(timezone.utc)

    # 1) whitelist — antes de qualquer rede
    if acao not in ACOES_PERMITIDAS:
        raise AcaoRecusada("acao_invalida", f"ação não permitida: {acao}")

    veiculo_id = str((parametros or {}).get("veiculo_id") or "").strip()
    if not veiculo_id:
        raise AcaoRecusada("parametro", "veículo não informado")

    # 6) rate-limit
    _checar_rate_limit(db, ctx.loja_slug, ref)

    # 3) escopo de loja — falha fechado
    try:
        garantir_escopo_loja(estoque, ctx.loja_slug)
    except EscopoLojaDivergente as exc:
        raise AcaoRecusada("escopo", str(exc)) from exc
    except EstoqueIndisponivel as exc:
        raise AcaoRecusada("indisponivel", "estoque indisponível agora") from exc

    # 5) releitura imediatamente antes de escrever
    try:
        veiculo = estoque.obter(veiculo_id)
    except VeiculoNaoEncontrado as exc:
        raise AcaoRecusada("nao_encontrado", "veículo não encontrado") from exc
    except EstoqueIndisponivel as exc:
        raise AcaoRecusada("indisponivel", "estoque indisponível agora") from exc

    preco_atual = _dec(veiculo.get("preco"))
    esperado = _dec((parametros or {}).get("preco_esperado"))
    if esperado is not None and preco_atual != esperado:
        raise AcaoRecusada(
            "divergencia",
            f"o preço mudou para {preco_atual} desde que o cartão foi montado",
        )

    valor_novo: Decimal | None = None
    if acao == "ajustar_preco":
        # 4) banda + piso
        valor_novo = validar_ajuste_preco(
            preco_atual or Decimal("0"), (parametros or {}).get("novo_preco")
        )

    registro = CopilotoAcao(
        loja_slug=ctx.loja_slug,
        turno_id=turno_id,
        ator_email=ctx.ator_email,
        acao=acao,
        entidade_ref=veiculo_id,
        valor_anterior=preco_atual,
        valor_novo=valor_novo,
        estado="executada",
        executada_em=ref,
        desfazer_ate=ref + timedelta(minutes=settings.copiloto_desfazer_minutos),
    )
    db.add(registro)

    try:
        if acao == "ajustar_preco":
            estoque.atualizar(veiculo_id, {"preco": float(valor_novo)})
        else:
            estoque.acao(veiculo_id, VERBO_ESTOQUE[acao])
    except (VeiculoNaoEncontrado, ConflitoEstoque, EstoqueIndisponivel, Exception) as exc:
        registro.estado = "falhou"
        registro.erro_code = type(exc).__name__[:40]
        # 7) auditoria também no fracasso
        registrar_auditoria_copiloto(
            db, loja_slug=ctx.loja_slug, acao=acao, ator_email=ctx.ator_email,
            success=False, error_code=type(exc).__name__,
        )
        db.commit()
        logger.warning("copiloto_acao falha acao=%s tipo=%s", acao, type(exc).__name__)
        raise AcaoRecusada("execucao", "não consegui executar a ação agora") from exc

    # 7) auditoria com anterior → novo
    registrar_auditoria_copiloto(
        db, loja_slug=ctx.loja_slug, acao=acao, ator_email=ctx.ator_email, success=True
    )
    db.commit()
    db.refresh(registro)
    # SQLite (testes) não preserva tzinfo em DateTime(timezone=True) — o
    # refresh acima devolve naive. Normaliza de volta, mesmo padrão já usado
    # em desfazer_acao/sinais_store, para o cartão e o desfazer receberem
    # sempre aware.
    if registro.executada_em is not None and registro.executada_em.tzinfo is None:
        registro.executada_em = registro.executada_em.replace(tzinfo=timezone.utc)
    if registro.desfazer_ate is not None and registro.desfazer_ate.tzinfo is None:
        registro.desfazer_ate = registro.desfazer_ate.replace(tzinfo=timezone.utc)
    logger.info(
        "copiloto_acao ok acao=%s loja=%s veiculo=%s de=%s para=%s",
        acao, ctx.loja_slug, veiculo_id, preco_atual, valor_novo,
    )
    return registro


def desfazer_acao(
    db: Session,
    ctx: CopilotoContexto,
    acao_id: str,
    *,
    estoque,
    agora: datetime | None = None,
) -> bool:
    """Desfazer em um clique dentro do prazo. Fora dele, não."""
    ref = agora or datetime.now(timezone.utc)
    registro = (
        db.query(CopilotoAcao)
        .filter(
            CopilotoAcao.id == acao_id,
            CopilotoAcao.loja_slug == ctx.loja_slug,
            CopilotoAcao.estado == "executada",
        )
        .first()
    )
    if registro is None:
        return False
    prazo = registro.desfazer_ate
    if prazo is not None and prazo.tzinfo is None:
        prazo = prazo.replace(tzinfo=timezone.utc)
    if prazo is None or ref > prazo:
        return False
    if registro.acao != "ajustar_preco" or registro.valor_anterior is None:
        return False

    try:
        garantir_escopo_loja(estoque, ctx.loja_slug)
        estoque.atualizar(
            registro.entidade_ref, {"preco": float(registro.valor_anterior)}
        )
    except Exception:
        return False

    registro.estado = "desfeita"
    registro.desfeita_em = ref
    registrar_auditoria_copiloto(
        db, loja_slug=ctx.loja_slug, acao="desfazer", ator_email=ctx.ator_email,
        success=True,
    )
    db.commit()
    return True
