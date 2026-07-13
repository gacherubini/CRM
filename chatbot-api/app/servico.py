"""Regras do Chatbot: ingestão idempotente de mensagens, conversa e handoff.

n8n/LLM nunca escrevem no banco direto — passam por esta API (Plano #2A).
"""
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_token
from app.models_db import (
    CatalogAttribution,
    Consentimento,
    Conversa,
    CredencialServico,
    Lead,
    Loja,
    Mensagem,
)


_CATALOG_REF_RE = re.compile(r"(?<![A-Z0-9])CAT-[A-Z2-7]{10,16}(?![A-Z0-9])", re.IGNORECASE)


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


def _mensagem_existente(
    db: Session, loja_id: str, provider_message_id: str
) -> Mensagem | None:
    return (
        db.query(Mensagem)
        .filter(
            Mensagem.loja_id == loja_id,
            Mensagem.provider_message_id == provider_message_id,
        )
        .first()
    )


def _resposta_duplicada(conversa: Conversa) -> dict:
    return {
        "duplicada": True,
        "conversa_id": conversa.id,
        "bot_ativo": conversa.bot_ativo,
    }


# Eventos Evolution sem conteúdo de mensagem (ack/status/reação). Não pausam o bot.
_TIPOS_SEM_CONTEUDO = frozenset(
    {"status", "ack", "reaction", "recibo", "receipt", "update", "messages.update"}
)


def _tem_conteudo(texto: str | None) -> bool:
    return bool(texto and str(texto).strip())


def _eh_evento_sem_conteudo(texto: str | None, tipo: str | None = None) -> bool:
    """True para ack/status/reação ou saída sem texto (não deve alterar bot_ativo)."""
    if tipo and str(tipo).strip().lower() in _TIPOS_SEM_CONTEUDO:
        return True
    return not _tem_conteudo(texto)


def _correlacionar_catalogo(
    db: Session, loja_id: str, telefone: str, texto: str | None
) -> CatalogAttribution | None:
    """Vincula uma referência pendente apenas uma vez e sempre dentro da loja."""
    if not texto:
        return None
    referencias = dict.fromkeys(ref.upper() for ref in _CATALOG_REF_RE.findall(texto))
    for referencia in referencias:
        atribuicao = (
            db.query(CatalogAttribution)
            .filter(
                CatalogAttribution.loja_id == loja_id,
                CatalogAttribution.catalog_interest_ref == referencia,
            )
            .first()
        )
        if atribuicao is None:
            continue
        if atribuicao.telefone:
            return atribuicao if atribuicao.telefone == telefone else None

        agora = datetime.now(timezone.utc)
        lead = _get_or_create_lead(db, loja_id, telefone)
        atribuicao.telefone = telefone
        atribuicao.lead_id = lead.id
        atribuicao.atribuida_em = agora

        # A leitura de lead representa a primeira origem atribuída; o histórico
        # completo permanece em catalog_attributions.
        if not lead.catalog_interest_ref:
            for campo in (
                "catalog_interest_ref", "veiculo_ref", "origem", "canal",
                "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
            ):
                setattr(lead, campo, getattr(atribuicao, campo))
            lead.atribuida_em = agora
            lead.atualizada_em = agora
        return atribuicao
    return None


def registrar_mensagem(
    db: Session,
    instancia: str,
    telefone: str,
    texto: str | None,
    provider_message_id: str | None = None,
    from_me: bool = False,
    origem_bot: bool = False,
    tipo: str | None = None,
) -> dict:
    """Persiste a mensagem de forma idempotente e garante a conversa.

    Contrato auto-pausa (E3):
    - `from_me=True` + `origem_bot=False` + conteúdo → atendente no app → `bot_ativo=False`.
    - Saída do bot: registrar com `origem_bot=True` e o mesmo `provider_message_id` que a
      Evolution devolve no envio; o eco `fromMe` chega depois e cai na dedupe (não pausa).
    - Ack/status/reação ou `from_me` sem texto → não alteram `bot_ativo` (nem poluem histórico).
    """
    loja = resolver_loja_por_instancia(db, instancia)
    conversa = _get_or_create_conversa(db, loja.id, telefone)

    if provider_message_id and _mensagem_existente(db, loja.id, provider_message_id):
        return _resposta_duplicada(conversa)

    # Eventos sem conteúdo (ack/recibo/status/reação ou texto vazio): não pausam e
    # não gravam mensagem fantasma. O n8n idealmente nem encaminha esses eventos.
    if from_me and not origem_bot and _eh_evento_sem_conteudo(texto, tipo):
        return {
            "duplicada": False,
            "conversa_id": conversa.id,
            "bot_ativo": conversa.bot_ativo,
            "ignorada": True,
        }

    atribuicao = None
    if not from_me:
        atribuicao = _correlacionar_catalogo(db, loja.id, telefone, texto)

    # Uma saída nova com conteúdo que não foi previamente registrada pelo workflow
    # do bot veio do atendente (celular/web). O humano assumiu: pausa automática.
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
    try:
        db.commit()
    except IntegrityError:
        # Corrida: outra requisição gravou o mesmo (loja_id, provider_message_id)
        # entre o SELECT acima e o commit. A UNIQUE do banco arbitra; respondemos
        # idempotente em vez de estourar 500.
        db.rollback()
        conversa = _get_or_create_conversa(db, loja.id, telefone)
        return _resposta_duplicada(conversa)
    return {
        "duplicada": False,
        "conversa_id": conversa.id,
        "bot_ativo": conversa.bot_ativo,
        "catalog_interest_ref": atribuicao.catalog_interest_ref if atribuicao else None,
    }


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


def ingerir_interesse_catalogo(
    db: Session,
    loja_id: str,
    *,
    event_id: str,
    loja_slug: str,
    catalog_interest_ref: str,
    veiculo_ref: str,
    origem: str,
    canal: str,
    occurred_at: datetime,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_content: str | None = None,
    utm_term: str | None = None,
) -> tuple[CatalogAttribution, bool]:
    loja = db.get(Loja, loja_id)
    if loja is None or loja.slug != loja_slug:
        raise HTTPException(status_code=403, detail="evento não pertence à loja autenticada")

    existente = (
        db.query(CatalogAttribution)
        .filter(
            CatalogAttribution.loja_id == loja_id,
            CatalogAttribution.event_id == event_id,
        )
        .first()
    )
    if existente:
        if not existente.telefone and _correlacionar_atribuicao_tardia(db, existente):
            db.commit()
            db.refresh(existente)
        return existente, True

    referencia = catalog_interest_ref.upper()
    conflito = (
        db.query(CatalogAttribution)
        .filter(
            CatalogAttribution.loja_id == loja_id,
            CatalogAttribution.catalog_interest_ref == referencia,
        )
        .first()
    )
    if conflito:
        raise HTTPException(status_code=409, detail="referência já usada por outro evento")

    atribuicao = CatalogAttribution(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        event_id=event_id,
        catalog_interest_ref=referencia,
        veiculo_ref=veiculo_ref,
        origem=origem,
        canal=canal,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        utm_content=utm_content,
        utm_term=utm_term,
        occurred_at=occurred_at,
    )
    db.add(atribuicao)
    try:
        db.flush()
        _correlacionar_atribuicao_tardia(db, atribuicao)
        db.commit()
    except IntegrityError:
        db.rollback()
        existente = (
            db.query(CatalogAttribution)
            .filter(
                CatalogAttribution.loja_id == loja_id,
                CatalogAttribution.event_id == event_id,
            )
            .first()
        )
        if existente:
            return existente, True
        raise
    db.refresh(atribuicao)
    return atribuicao, False


def _correlacionar_atribuicao_tardia(
    db: Session, atribuicao: CatalogAttribution
) -> CatalogAttribution | None:
    """Fecha a corrida em que a mensagem chega antes da entrega da outbox."""
    resultados = (
        db.query(Mensagem, Conversa)
        .join(Conversa, Mensagem.conversa_id == Conversa.id)
        .filter(
            Mensagem.loja_id == atribuicao.loja_id,
            Mensagem.direcao == "entrada",
            Mensagem.texto.ilike(f"%{atribuicao.catalog_interest_ref}%"),
        )
        .order_by(Mensagem.criada_em.asc())
        .limit(100)
        .all()
    )
    for mensagem, conversa in resultados:
        refs = {ref.upper() for ref in _CATALOG_REF_RE.findall(mensagem.texto or "")}
        if atribuicao.catalog_interest_ref not in refs:
            continue
        return _correlacionar_catalogo(
            db, atribuicao.loja_id, conversa.telefone, mensagem.texto
        )
    return None


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
        "origem": lead.origem,
        "canal": lead.canal,
        "utm_source": lead.utm_source,
        "utm_medium": lead.utm_medium,
        "utm_campaign": lead.utm_campaign,
        "utm_content": lead.utm_content,
        "utm_term": lead.utm_term,
        "veiculo_ref": lead.veiculo_ref,
        "catalog_interest_ref": lead.catalog_interest_ref,
        "atribuida_em": lead.atribuida_em.isoformat() if lead.atribuida_em else None,
    }
