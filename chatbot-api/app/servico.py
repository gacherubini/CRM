"""Regras do Chatbot: ingestão idempotente de mensagens, conversa e handoff.

n8n/LLM nunca escrevem no banco direto — passam por esta API (Plano #2A).
"""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth import hash_token
from app.models_db import (
    Consentimento,
    Conversa,
    CredencialServico,
    Lead,
    Loja,
    Mensagem,
)


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


# --- Leads e consentimento (LGPD) --------------------------------------------


def _get_or_create_lead(db: Session, loja_id: str, telefone: str) -> Lead:
    lead = (
        db.query(Lead)
        .filter(Lead.loja_id == loja_id, Lead.telefone == telefone)
        .first()
    )
    if lead is None:
        lead = Lead(id=str(uuid.uuid4()), loja_id=loja_id, telefone=telefone, etapa="novo")
        db.add(lead)
        db.flush()
    return lead


def registrar_consentimento(
    db: Session,
    loja_id: str,
    telefone: str,
    versao_texto: str,
    finalidade: str,
    evidencia: str | None = None,
) -> Lead:
    lead = _get_or_create_lead(db, loja_id, telefone)
    db.add(
        Consentimento(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            lead_id=lead.id,
            telefone=telefone,
            versao_texto=versao_texto,
            finalidade=finalidade,
            evidencia=evidencia,
            aceito_em=datetime.now(timezone.utc),
        )
    )
    lead.consentimento_em = datetime.now(timezone.utc)
    lead.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
    return lead


def registrar_lead(
    db: Session,
    loja_id: str,
    telefone: str,
    nome: str | None = None,
    interesse: str | None = None,
    etapa: str | None = None,
) -> Lead:
    lead = _get_or_create_lead(db, loja_id, telefone)
    # Dados pessoais (nome) exigem consentimento prévio (LGPD).
    if nome and lead.consentimento_em is None:
        raise HTTPException(
            status_code=409, detail="consentimento necessário antes de dados pessoais"
        )
    if nome is not None:
        lead.nome = nome
    if interesse is not None:
        lead.interesse = interesse
    if etapa is not None:
        lead.etapa = etapa
    lead.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
    return lead


def listar_leads(db: Session, loja_id: str, etapa: str | None = None) -> list[Lead]:
    q = db.query(Lead).filter(Lead.loja_id == loja_id)
    if etapa:
        q = q.filter(Lead.etapa == etapa)
    return q.order_by(Lead.criada_em.desc()).all()


def obter_lead(db: Session, loja_id: str, lead_id: str) -> Lead:
    lead = (
        db.query(Lead).filter(Lead.id == lead_id, Lead.loja_id == loja_id).first()
    )
    if lead is None:
        raise HTTPException(status_code=404, detail="lead não encontrado")
    return lead


def para_saida_lead(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "telefone": lead.telefone,
        "nome": lead.nome,
        "interesse": lead.interesse,
        "etapa": lead.etapa,
        "consentimento_em": lead.consentimento_em.isoformat()
        if lead.consentimento_em
        else None,
        "criada_em": lead.criada_em.isoformat() if lead.criada_em else None,
    }
