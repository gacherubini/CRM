"""CRUD de conversa e turno. Escopo de loja em toda leitura."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import PERGUNTA_MAX, CopilotoConversa, CopilotoTurno

ESTADOS_CANCELAVEIS = ("pendente", "executando")


def _titulo(pergunta: str) -> str:
    limpo = " ".join((pergunta or "").split())
    return (limpo[:80] + "…") if len(limpo) > 80 else (limpo or "Nova conversa")


def criar_turno(
    db: Session,
    *,
    loja_slug: str,
    usuario_id: str,
    pergunta: str,
    conversa_id: str | None = None,
) -> CopilotoTurno:
    texto = (pergunta or "").strip()
    if not texto:
        raise ValueError("pergunta vazia")
    if len(texto) > PERGUNTA_MAX:
        raise ValueError("pergunta longa demais")

    conversa = None
    if conversa_id:
        conversa = (
            db.query(CopilotoConversa)
            .filter(
                CopilotoConversa.id == conversa_id,
                CopilotoConversa.loja_slug == loja_slug,
                CopilotoConversa.usuario_id == usuario_id,
            )
            .first()
        )
    if conversa is None:
        conversa = CopilotoConversa(
            loja_slug=loja_slug, usuario_id=usuario_id, titulo=_titulo(texto)
        )
        db.add(conversa)
        db.flush()

    turno = CopilotoTurno(
        conversa_id=conversa.id,
        loja_slug=loja_slug,
        usuario_id=usuario_id,
        pergunta=texto,
        estado="pendente",
    )
    db.add(turno)
    conversa.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(turno)
    return turno


def obter_turno(db: Session, loja_slug: str, turno_id: str) -> CopilotoTurno | None:
    return (
        db.query(CopilotoTurno)
        .filter(CopilotoTurno.id == turno_id, CopilotoTurno.loja_slug == loja_slug)
        .first()
    )


def atualizar_progresso(
    db: Session,
    turno: CopilotoTurno,
    *,
    estado: str | None = None,
    passos: list[dict] | None = None,
    texto_parcial: str | None = None,
) -> None:
    if estado:
        turno.estado = estado
        if estado == "executando" and turno.iniciado_em is None:
            turno.iniciado_em = datetime.now(timezone.utc)
    if passos is not None:
        turno.passos_json = json.dumps(passos, ensure_ascii=False)
    if texto_parcial is not None:
        turno.texto_parcial = texto_parcial
    db.commit()


def reivindicar_turno(
    db: Session, turno_id: str, *, agora: datetime | None = None
) -> bool:
    """Transição atômica `pendente` → `executando`. True = este processo ganhou.

    Um único UPDATE condicional: quem decide é o banco, não o Python. Sem isto,
    dois processos rodando ``run_once`` leem o mesmo turno `pendente` no mesmo
    lote e ambos chamam o provedor — o custo de LLM sai em dobro pela mesma
    pergunta, e a segunda resposta sobrescreve a primeira.

    ``synchronize_session=False`` porque o objeto ORM não precisa ser
    atualizado aqui: quem ganhou dá ``db.refresh`` antes de usar. Em SQLite o
    UPDATE condicional já é atômico dentro da transação de escrita; em Postgres
    ele é o mecanismo inteiro.
    """
    resultado = db.execute(
        update(CopilotoTurno)
        .where(CopilotoTurno.id == turno_id, CopilotoTurno.estado == "pendente")
        .values(estado="executando", iniciado_em=agora or datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return resultado.rowcount == 1


def concluir_turno(
    db: Session,
    turno: CopilotoTurno,
    *,
    resposta: str,
    passos: list[dict],
    tokens_entrada: int,
    tokens_saida: int,
    custo_estimado: str | Decimal | None,
) -> None:
    turno.estado = "pronto"
    turno.resposta = resposta
    turno.texto_parcial = resposta
    turno.passos_json = json.dumps(passos, ensure_ascii=False)
    turno.tokens_entrada = int(tokens_entrada or 0)
    turno.tokens_saida = int(tokens_saida or 0)
    turno.custo_estimado = (
        Decimal(str(custo_estimado)) if custo_estimado is not None else None
    )
    turno.concluido_em = datetime.now(timezone.utc)
    db.commit()


def falhar_turno(
    db: Session,
    turno: CopilotoTurno,
    *,
    erro_code: str,
    tokens_entrada: int = 0,
    tokens_saida: int = 0,
) -> None:
    """Turno que falha AINDA grava tokens: senão o log mente sobre o consumo."""
    turno.estado = "erro"
    turno.erro_code = erro_code[:40]
    turno.tokens_entrada = int(tokens_entrada or 0)
    turno.tokens_saida = int(tokens_saida or 0)
    turno.concluido_em = datetime.now(timezone.utc)
    db.commit()


def cancelar_turno(db: Session, loja_slug: str, turno_id: str) -> bool:
    turno = obter_turno(db, loja_slug, turno_id)
    if turno is None or turno.estado not in ESTADOS_CANCELAVEIS:
        return False
    turno.estado = "cancelado"
    turno.concluido_em = datetime.now(timezone.utc)
    db.commit()
    return True


def listar_conversas(
    db: Session, loja_slug: str, usuario_id: str, *, limite: int = 20
) -> list[CopilotoConversa]:
    return (
        db.query(CopilotoConversa)
        .filter(
            CopilotoConversa.loja_slug == loja_slug,
            CopilotoConversa.usuario_id == usuario_id,
            CopilotoConversa.arquivada_em.is_(None),
        )
        .order_by(CopilotoConversa.atualizada_em.desc())
        .limit(max(1, limite))
        .all()
    )


def listar_turnos(
    db: Session, loja_slug: str, conversa_id: str
) -> list[CopilotoTurno]:
    """Turnos de uma conversa — escopados por loja, como ``obter_turno``.

    Um ``conversa_id`` sozinho nunca autoriza a leitura: sem o filtro de
    ``loja_slug`` aqui, um chamador que só validasse o dono da conversa (ou
    nem isso) vazaria turnos de outra loja pelo mesmo endpoint.
    """
    return (
        db.query(CopilotoTurno)
        .filter(
            CopilotoTurno.loja_slug == loja_slug,
            CopilotoTurno.conversa_id == conversa_id,
        )
        .order_by(CopilotoTurno.criado_em.asc())
        .all()
    )
