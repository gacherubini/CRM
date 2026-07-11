"""Regras do Chatbot: ingestão idempotente de mensagens, conversa e handoff.

n8n/LLM nunca escrevem no banco direto — passam por esta API (Plano #2A).
"""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth import hash_token
from app.models_db import Conversa, CredencialServico, Loja, Mensagem


def criar_loja(
    db: Session, nome: str, slug: str, evolution_instance: str, whatsapp: str | None = None
) -> tuple[Loja, str]:
    if db.query(Loja).filter(Loja.slug == slug).first():
        raise HTTPException(status_code=409, detail="slug já existe")
    if db.query(Loja).filter(Loja.evolution_instance == evolution_instance).first():
        raise HTTPException(status_code=409, detail="instância já existe")
    loja = Loja(
        id=str(uuid.uuid4()),
        nome=nome,
        slug=slug,
        evolution_instance=evolution_instance,
        whatsapp=whatsapp,
    )
    db.add(loja)
    db.flush()
    token = secrets.token_urlsafe(24)
    db.add(CredencialServico(token_hash=hash_token(token), loja_id=loja.id))
    db.commit()
    db.refresh(loja)
    return loja, token


def resolver_loja_por_instancia(db: Session, instancia: str) -> Loja:
    loja = db.query(Loja).filter(Loja.evolution_instance == instancia).first()
    if loja is None:
        raise HTTPException(status_code=404, detail="instância não reconhecida")
    return loja


def _get_or_create_conversa(db: Session, loja_id: str, telefone: str) -> Conversa:
    conversa = (
        db.query(Conversa)
        .filter(Conversa.loja_id == loja_id, Conversa.telefone == telefone)
        .first()
    )
    if conversa is None:
        conversa = Conversa(id=str(uuid.uuid4()), loja_id=loja_id, telefone=telefone)
        db.add(conversa)
        db.flush()
    return conversa


def registrar_mensagem(
    db: Session,
    instancia: str,
    telefone: str,
    texto: str | None,
    provider_message_id: str | None = None,
    from_me: bool = False,
) -> dict:
    """Persiste a mensagem de forma idempotente e garante a conversa."""
    loja = resolver_loja_por_instancia(db, instancia)
    conversa = _get_or_create_conversa(db, loja.id, telefone)

    if provider_message_id:
        existe = (
            db.query(Mensagem)
            .filter(
                Mensagem.loja_id == loja.id,
                Mensagem.provider_message_id == provider_message_id,
            )
            .first()
        )
        if existe:
            return {
                "duplicada": True,
                "conversa_id": conversa.id,
                "bot_ativo": conversa.bot_ativo,
            }

    db.add(
        Mensagem(
            id=str(uuid.uuid4()),
            loja_id=loja.id,
            conversa_id=conversa.id,
            direcao="saida" if from_me else "entrada",
            provider_message_id=provider_message_id,
            texto=texto,
        )
    )
    conversa.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    return {"duplicada": False, "conversa_id": conversa.id, "bot_ativo": conversa.bot_ativo}


def obter_estado(db: Session, loja_id: str, telefone: str) -> dict:
    conversa = (
        db.query(Conversa)
        .filter(Conversa.loja_id == loja_id, Conversa.telefone == telefone)
        .first()
    )
    if conversa is None:
        return {"bot_ativo": True, "status": "aberta"}
    return {"bot_ativo": conversa.bot_ativo, "status": conversa.status}


def definir_bot_ativo(db: Session, loja_id: str, telefone: str, ativo: bool) -> dict:
    conversa = _get_or_create_conversa(db, loja_id, telefone)
    conversa.bot_ativo = ativo
    conversa.status = "aberta" if ativo else "handoff"
    conversa.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    return {"bot_ativo": conversa.bot_ativo, "status": conversa.status}
