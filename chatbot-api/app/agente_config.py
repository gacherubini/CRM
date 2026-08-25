"""Versões da config do agente: rascunho, publicada, histórico (spec §3.2).

Restaurar uma versão antiga carrega os campos dela para dentro do rascunho
atual (sobrescrevendo o que estava lá). Nenhuma versão publicada ou arquivada
é alterada, e nada do histórico é apagado.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models_db
from app.agente_prompt import CAMPOS_PADRAO_REVY, CamposAgente, montar_prompt


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _config(db: Session, loja_id: str) -> models_db.AgenteConfig:
    cfg = db.get(models_db.AgenteConfig, loja_id)
    if cfg is None:
        cfg = models_db.AgenteConfig(loja_id=loja_id)
        db.add(cfg)
        db.flush()
    return cfg


def _versao_publicada(db: Session, loja_id: str) -> models_db.AgenteConfigVersao | None:
    cfg = db.get(models_db.AgenteConfig, loja_id)
    if cfg is None or cfg.versao_publicada_id is None:
        return None
    return db.get(models_db.AgenteConfigVersao, cfg.versao_publicada_id)


def obter_rascunho(db: Session, loja_id: str) -> models_db.AgenteConfigVersao:
    """Rascunho vivo da loja; nasce da publicada, ou do padrão Revy."""
    rascunho = (
        db.query(models_db.AgenteConfigVersao)
        .filter(
            models_db.AgenteConfigVersao.loja_id == loja_id,
            models_db.AgenteConfigVersao.estado == "rascunho",
        )
        .order_by(models_db.AgenteConfigVersao.criado_em.desc())
        .first()
    )
    if rascunho is not None:
        return rascunho
    base = _versao_publicada(db, loja_id)
    campos = (
        CamposAgente(**base.campos) if base is not None else CAMPOS_PADRAO_REVY
    )
    return salvar_rascunho(db, loja_id, campos, autor=None)


def salvar_rascunho(
    db: Session, loja_id: str, campos: CamposAgente, autor: str | None
) -> models_db.AgenteConfigVersao:
    _config(db, loja_id)
    atual = (
        db.query(models_db.AgenteConfigVersao)
        .filter(
            models_db.AgenteConfigVersao.loja_id == loja_id,
            models_db.AgenteConfigVersao.estado == "rascunho",
        )
        .first()
    )
    if atual is None:
        atual = models_db.AgenteConfigVersao(
            id=str(uuid.uuid4()), loja_id=loja_id, estado="rascunho", criado_em=_agora()
        )
        db.add(atual)
    atual.campos = campos.model_dump()
    atual.prompt_gerado = montar_prompt(campos)
    atual.autor = autor
    db.commit()
    db.refresh(atual)
    return atual


def publicar(db: Session, loja_id: str, autor: str | None) -> models_db.AgenteConfigVersao:
    rascunho = obter_rascunho(db, loja_id)
    anterior = _versao_publicada(db, loja_id)
    if anterior is not None:
        anterior.estado = "arquivada"
    rascunho.estado = "publicada"
    rascunho.autor = autor
    rascunho.publicado_em = _agora()
    _config(db, loja_id).versao_publicada_id = rascunho.id
    db.commit()
    db.refresh(rascunho)
    return rascunho


def listar_versoes(db: Session, loja_id: str) -> list[models_db.AgenteConfigVersao]:
    return (
        db.query(models_db.AgenteConfigVersao)
        .filter(models_db.AgenteConfigVersao.loja_id == loja_id)
        .order_by(models_db.AgenteConfigVersao.criado_em.desc())
        .all()
    )


def restaurar(
    db: Session, loja_id: str, versao_id: str, autor: str | None
) -> models_db.AgenteConfigVersao:
    """Carrega os campos de uma versão antiga para dentro do rascunho atual.

    Não cria versão publicada nem arquivada nova, e não apaga nada do
    histórico: quem muda é só o rascunho, via `salvar_rascunho` (que
    reaproveita a linha de rascunho em andamento, se houver uma). Se o
    lojista tiver um rascunho não publicado em curso, o conteúdo dele é
    sobrescrito em silêncio — a tela é quem avisa antes de chamar isto.
    """
    antiga = db.get(models_db.AgenteConfigVersao, versao_id)
    if antiga is None or antiga.loja_id != loja_id:
        raise LookupError("versão não é desta loja")
    return salvar_rascunho(db, loja_id, CamposAgente(**antiga.campos), autor)


def campos_publicados(db: Session, loja_id: str) -> CamposAgente:
    versao = _versao_publicada(db, loja_id)
    if versao is None:
        return CAMPOS_PADRAO_REVY
    return CamposAgente(**versao.campos)


def prompt_publicado(db: Session, loja_id: str) -> str:
    """Congelado no publicar. Loja sem config cai no padrão — o bot nunca fica mudo."""
    versao = _versao_publicada(db, loja_id)
    if versao is None:
        return montar_prompt(CAMPOS_PADRAO_REVY)
    return versao.prompt_gerado
