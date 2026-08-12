"""Execução das ações propostas pelo Copiloto.

A ação NUNCA é executada pelo turno do LLM. O modelo propõe; isto aqui roda
depois do clique humano, com sete guardas server-side.

A guarda 5 (releitura antes de escrever) existe porque o PATCH da
estoque-api não tem idempotência nem If-Match/ETag (Idempotency-Key só
existe no POST de criação, ``estoque-api/app/main.py:204``). Sem ela, o
Copiloto sobrescreve em silêncio a alteração que outra pessoa fez dois
segundos antes. A mesma guarda vale para o desfazer (revisão de 2026-08-12,
achado I-2 da revisão): ele também é uma escrita real num estoque real, e
também relê antes de escrever.

``agora`` é ponto de injeção **de teste** (relógio determinístico para
rate-limit, carimbo e prazo de desfazer). Quem chama estas funções a partir
de uma rota HTTP (Task 6) NUNCA pode derivar ``agora`` de um dado vindo do
cliente — um relógio controlável pelo chamador fura o rate-limit e envenena
a auditoria e o prazo de desfazer ao mesmo tempo (achado I-4 da revisão).

Por que ``pendente`` pode ser o estado FINAL de uma ação, não só um passo de
transição (achado I-1 da revisão de 2026-08-12): ``EstoqueClient._request``
colapsa timeout, erro de conexão e 5xx no mesmo ``EstoqueIndisponivel`` — se
isso acontece DEPOIS do PATCH ter saído, o Portal não sabe se a escrita
pegou. Gravar ``falhou`` nesse caso afirmaria com confiança o que não se
sabe, e isso é pior que admitir a dúvida: o dono leria "não aconteceu nada"
justo na hora em que o botão Desfazer sumiria — o mecanismo desenhado
exatamente para resolver essa dúvida. Por isso ``executar_acao`` deixa a
linha ``pendente`` (em vez de promovê-la para ``falhou``) quando o erro é
``EstoqueIndisponivel``, e ``desfazer_acao`` aceita linhas ``pendente``: a
releitura da guarda 5 decide sozinha — valor bate com ``valor_novo``? o PATCH
pegou, reverte. Não bate? não havia o que reverter, devolve ``False``.
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
# dono confirmou no cartão. O desfazer reaproveita este mesmo vocabulário: não
# inventa um terceiro jeito de nomear "publicado"/"despublicado".
VERBO_ESTOQUE = {
    "repostar_veiculo": "publicar",
    "publicar_veiculo": "publicar",
    "despublicar_veiculo": "despublicar",
}
VERBOS_VALIDOS = frozenset(VERBO_ESTOQUE.values())


class AcaoRecusada(RuntimeError):
    def __init__(self, code: str, mensagem: str):
        super().__init__(mensagem)
        self.code = code


def _dec(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        bruto = Decimal(str(valor))
    except (ArithmeticError, ValueError):
        return None
    # NaN passa pelo Decimal(...) sem levantar (json.loads aceita o literal
    # NaN) e só explodiria mais adiante, em decimal.InvalidOperation, na
    # primeira comparação. Infinity já cairia no quantize abaixo, mas checar
    # aqui deixa as duas recusas de não-finito no mesmo lugar (achado I-6).
    if not bruto.is_finite():
        return None
    try:
        return bruto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError):
        return None


def _max_acoes_hora() -> int:
    try:
        return int(os.getenv("PORTAL_COPILOTO_MAX_ACOES_HORA", "20"))
    except ValueError:
        return 20


def _estado_publicacao_atual(veiculo: dict) -> str:
    """Verbo do Estoque que RESTAURA o estado de publicação atual do veículo."""
    return "publicar" if veiculo.get("publicado") else "despublicar"


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
    """Conta TODAS as tentativas da janela, inclusive as que falharam.

    Revisão de 2026-08-12 (achado I-3): o rate-limit existe para limitar
    dano e custo de um laço; um laço que martela o botão com a estoque-api
    fora do ar é exatamente o caso que precisa ser freado — não só as ações
    que tiveram sucesso.
    """
    desde = agora - timedelta(hours=1)
    tentativas = (
        db.query(CopilotoAcao)
        .filter(
            CopilotoAcao.loja_slug == loja_slug,
            CopilotoAcao.executada_em >= desde,
        )
        .count()
    )
    if tentativas >= _max_acoes_hora():
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

    # Revisão de 2026-08-12 (achado C-1, Critical): preco_esperado é
    # OBRIGATÓRIO para ajustar_preco. Sem ele a guarda 5 (releitura x
    # cartão, abaixo) não tem nada para comparar e vira decorativa — o PATCH
    # segue com o preço fresco, seja ele qual for. Quem monta o cartão
    # sempre sabe o preço que mostrou; não existe caso legítimo de
    # ajustar_preco sem preco_esperado.
    esperado: Decimal | None = None
    if acao == "ajustar_preco":
        esperado = _dec((parametros or {}).get("preco_esperado"))
        if esperado is None:
            raise AcaoRecusada(
                "preco_esperado_ausente",
                "preco_esperado é obrigatório para ajustar_preco",
            )

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
    if acao == "ajustar_preco" and preco_atual != esperado:
        raise AcaoRecusada(
            "divergencia",
            f"o preço mudou para {preco_atual} desde que o cartão foi montado",
        )

    valor_novo: Decimal | None = None
    estado_anterior: str | None = None
    if acao == "ajustar_preco":
        # 4) banda + piso
        valor_novo = validar_ajuste_preco(
            preco_atual or Decimal("0"), (parametros or {}).get("novo_preco")
        )
    else:
        # Achado I-1 da revisão: guarda o verbo que RESTAURA o estado de
        # publicação de ANTES da ação — lido agora, na mesma releitura da
        # guarda 5, não inferido do nome da ação.
        estado_anterior = _estado_publicacao_atual(veiculo)

    # Achado I-5 (Important) da revisão: grava a INTENÇÃO e comita ANTES de
    # tocar a rede. Se o processo morrer entre a escrita real no estoque e a
    # promoção para "executada", esta linha "pendente" é o único jeito de
    # alguém descobrir depois que o preço/estado de uma loja real mudou.
    registro = CopilotoAcao(
        loja_slug=ctx.loja_slug,
        turno_id=turno_id,
        ator_email=ctx.ator_email,
        acao=acao,
        entidade_ref=veiculo_id,
        valor_anterior=preco_atual,
        valor_novo=valor_novo,
        estado_anterior=estado_anterior,
        estado="pendente",
        executada_em=ref,
        desfazer_ate=ref + timedelta(minutes=settings.copiloto_desfazer_minutos),
    )
    db.add(registro)
    db.commit()

    try:
        if acao == "ajustar_preco":
            estoque.atualizar(veiculo_id, {"preco": float(valor_novo)})
        else:
            estoque.acao(veiculo_id, VERBO_ESTOQUE[acao])
    except EstoqueIndisponivel as exc:
        # Revisão de 2026-08-12 (achado I-1, Important): `EstoqueClient._request`
        # colapsa timeout, erro de conexão e 5xx num único `EstoqueIndisponivel`
        # — deste lado do Portal o resultado é genuinamente INDETERMINADO, não
        # uma certeza de que nada mudou. O PATCH pode ter chegado ao Estoque e
        # só a RESPOSTA se perdeu. Gravar "falhou" aqui seria afirmar com
        # confiança o que não se sabe: o dono leria "não aconteceu nada" bem na
        # hora em que o botão Desfazer sumiria — justo o caso em que ele é mais
        # necessário. Por isso a linha continua "pendente" (o estado que a
        # escrita em duas fases já criou para representar "não sei", achado
        # I-5) — só o erro_code muda. `desfazer_acao` relê o estoque antes de
        # escrever (guarda 5): se o valor bater com valor_novo, o PATCH pegou
        # e ele reverte; se não bater, não havia o que reverter e ele devolve
        # False sem tocar a rede. A releitura que já existia por outro motivo
        # é a resposta certa para esta indeterminação — "falhou" fecharia essa
        # porta bem no caso em que ela precisa ficar aberta.
        registro.erro_code = type(exc).__name__[:40]
        registrar_auditoria_copiloto(
            db, loja_slug=ctx.loja_slug, acao=acao, ator_email=ctx.ator_email,
            success=False, error_code=type(exc).__name__,
        )
        db.commit()
        logger.warning(
            "copiloto_acao indeterminado acao=%s tipo=%s", acao, type(exc).__name__
        )
        raise AcaoRecusada(
            "indisponivel",
            "não sei se a ação chegou a ser aplicada — confira o veículo antes de tentar de novo",
        ) from exc
    except Exception as exc:
        # Aqui SÓ chegam erros que PROVAM que a escrita não aconteceu:
        # VeiculoNaoEncontrado (404), ConflitoEstoque (409) — a estoque-api
        # respondeu, e respondeu recusando. Não há indeterminação para
        # resolver: "falhou" é a verdade.
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

    registro.estado = "executada"
    # 7) auditoria com anterior → novo
    registrar_auditoria_copiloto(
        db, loja_slug=ctx.loja_slug, acao=acao, ator_email=ctx.ator_email, success=True
    )
    db.commit()
    db.refresh(registro)
    # SQLite (usado nos testes e em qualquer deploy sem Postgres — o default
    # de PORTAL_DATABASE_URL é sqlite) não preserva tzinfo em
    # DateTime(timezone=True). Normaliza de volta pro mesmo padrão já usado
    # em outros pontos do repo (app/tokens.py, loja/estoque_overview.py...).
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
    """Desfazer em um clique dentro do prazo. Fora dele, não.

    Escreve de verdade no estoque de uma loja real — por isso relê
    imediatamente antes de escrever, a mesma guarda 5 de ``executar_acao``
    (achado I-2 da revisão de 2026-08-12): se o valor/estado atual não bater
    com o que a ação original gravou, alguém mexeu depois e a restauração
    aborta em vez de sobrescrever.

    Aceita linhas ``pendente`` além de ``executada`` (achado I-1 da revisão de
    2026-08-12): uma linha ``pendente`` significa "não sei se o PATCH foi
    aplicado", não "não aconteceu nada". A MESMA releitura acima já resolve a
    dúvida sem lógica nova: se o valor atual do Estoque bater com
    ``valor_novo``, o PATCH pegou — reverte. Se não bater, o PATCH não pegou —
    não há o que reverter, e devolve ``False`` sem escrever. Recusar o
    desfazer de uma linha ``pendente`` fecharia a única saída justo no caso em
    que ela é mais necessária: preço mudou de verdade, e o sistema afirma que
    não mudou.
    """
    ref = agora or datetime.now(timezone.utc)
    registro = (
        db.query(CopilotoAcao)
        .filter(
            CopilotoAcao.id == acao_id,
            CopilotoAcao.loja_slug == ctx.loja_slug,
            CopilotoAcao.estado.in_(("executada", "pendente")),
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

    try:
        garantir_escopo_loja(estoque, ctx.loja_slug)
        veiculo = estoque.obter(registro.entidade_ref)
    except Exception:
        return False

    if registro.acao == "ajustar_preco":
        if registro.valor_anterior is None or registro.valor_novo is None:
            return False
        atual = _dec(veiculo.get("preco"))
        if atual != registro.valor_novo:
            logger.warning(
                "copiloto_desfazer divergiu_apos_acao acao_id=%s de=%s para=%s",
                acao_id, registro.valor_novo, atual,
            )
            return False
        try:
            estoque.atualizar(
                registro.entidade_ref, {"preco": float(registro.valor_anterior)}
            )
        except Exception:
            return False
    elif registro.acao in VERBO_ESTOQUE:
        # Achado I-1: linhas de antes da migration 0022 não têm
        # estado_anterior — falha fechado em vez de adivinhar o verbo.
        if registro.estado_anterior not in VERBOS_VALIDOS:
            return False
        esperado_apos_acao = VERBO_ESTOQUE[registro.acao]
        atual_verbo = _estado_publicacao_atual(veiculo)
        if atual_verbo != esperado_apos_acao:
            logger.warning(
                "copiloto_desfazer divergiu_apos_acao acao_id=%s esperado=%s atual=%s",
                acao_id, esperado_apos_acao, atual_verbo,
            )
            return False
        try:
            estoque.acao(registro.entidade_ref, registro.estado_anterior)
        except Exception:
            return False
    else:
        return False

    registro.estado = "desfeita"
    registro.desfeita_em = ref
    registrar_auditoria_copiloto(
        db, loja_slug=ctx.loja_slug, acao="desfazer", ator_email=ctx.ator_email,
        success=True,
    )
    db.commit()
    return True
