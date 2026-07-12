"""Regras do Chatbot: ingestão idempotente de mensagens, conversa e handoff.

n8n/LLM nunca escrevem no banco direto — passam por esta API (Plano #2A).
"""
import re
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


# --- Mascaramento de CPF (LGPD, silencioso) ----------------------------------

_RE_CPF_FMT = re.compile(r"(?<!\d)(\d{3})\.(\d{3})\.(\d{3})-(\d{2})(?!\d)")
_RE_CPF_BARE = re.compile(r"(?<!\d)(\d{11})(?!\d)")


def _cpf_valido(digitos: str) -> bool:
    """Valida os dígitos verificadores; evita mascarar telefones/números comuns."""
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    nums = [int(c) for c in digitos]
    for i in (9, 10):
        soma = sum(nums[j] * ((i + 1) - j) for j in range(i))
        dv = (soma * 10) % 11
        dv = 0 if dv == 10 else dv
        if dv != nums[i]:
            return False
    return True


def mascarar_cpf(texto: str | None) -> str | None:
    """Mascara CPFs no texto livre: formatado por padrão, avulso só se válido."""
    if not texto:
        return texto
    texto = _RE_CPF_FMT.sub(lambda m: "***.***.***-" + m.group(4), texto)

    def _bare(m):
        d = m.group(1)
        return "*" * 9 + d[-2:] if _cpf_valido(d) else d

    return _RE_CPF_BARE.sub(_bare, texto)


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
    origem_bot: bool = False,
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

    # Uma saída nova que não foi previamente registrada pelo workflow do bot
    # veio do atendente (celular/web). O humano assumiu: pausa automática.
    if from_me and not origem_bot:
        conversa.bot_ativo = False
        conversa.status = "handoff"

    db.add(
        Mensagem(
            id=str(uuid.uuid4()),
            loja_id=loja.id,
            conversa_id=conversa.id,
            direcao="saida" if from_me else "entrada",
            provider_message_id=provider_message_id,
            texto=mascarar_cpf(texto),
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


# --- Conversas e mensagens (handoff/Portal) ----------------------------------


_PREVIEW_MAX = 120


def listar_conversas(
    db: Session,
    loja_id: str,
    limit: int,
    offset: int,
    busca: str | None = None,
) -> list[dict]:
    q = db.query(Conversa).filter(Conversa.loja_id == loja_id)
    if busca:
        q = q.filter(Conversa.telefone.contains(busca))
    conversas = (
        q.order_by(Conversa.atualizada_em.desc()).limit(limit).offset(offset).all()
    )
    if not conversas:
        return []

    ids = [c.id for c in conversas]
    mensagens = (
        db.query(Mensagem)
        .filter(Mensagem.loja_id == loja_id, Mensagem.conversa_id.in_(ids))
        .order_by(Mensagem.criada_em.asc())
        .all()
    )
    ultima_por_conversa: dict[str, Mensagem] = {}
    for msg in mensagens:
        ultima_por_conversa[msg.conversa_id] = msg  # asc => sobrescreve com a mais recente

    return [para_saida_conversa(c, ultima_por_conversa.get(c.id)) for c in conversas]


def listar_mensagens(
    db: Session, loja_id: str, telefone: str, limit: int, offset: int
) -> dict:
    conversa = (
        db.query(Conversa)
        .filter(Conversa.loja_id == loja_id, Conversa.telefone == telefone)
        .first()
    )
    if conversa is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    mensagens = (
        db.query(Mensagem)
        .filter(Mensagem.loja_id == loja_id, Mensagem.conversa_id == conversa.id)
        .order_by(Mensagem.criada_em.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return {
        "telefone": telefone,
        "mensagens": [para_saida_mensagem(m) for m in mensagens],
    }


def para_saida_mensagem(msg: Mensagem) -> dict:
    return {
        "direcao": msg.direcao,
        "texto": mascarar_cpf(msg.texto),
        "criada_em": msg.criada_em.isoformat() if msg.criada_em else None,
    }


def para_saida_conversa(conversa: Conversa, ultima: Mensagem | None = None) -> dict:
    ultima_saida = None
    if ultima is not None:
        texto = ultima.texto or ""
        ultima_saida = {
            "texto": texto[:_PREVIEW_MAX],
            "criada_em": ultima.criada_em.isoformat() if ultima.criada_em else None,
            "direcao": ultima.direcao,
        }
    return {
        "id": conversa.id,
        "telefone": conversa.telefone,
        "bot_ativo": conversa.bot_ativo,
        "status": conversa.status,
        "atualizada_em": conversa.atualizada_em.isoformat()
        if conversa.atualizada_em
        else None,
        "ultima_mensagem": ultima_saida,
    }


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
