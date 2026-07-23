"""Regras do Chatbot: ingestão idempotente de mensagens, conversa e handoff.

n8n/LLM nunca escrevem no banco direto — passam por esta API (Plano #2A).
"""
import json
import logging
import os
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
    CtwaAuditoria,
    Lead,
    Loja,
    Mensagem,
)

logger = logging.getLogger("chatbot.ctwa")


_CATALOG_REF_RE = re.compile(r"(?<![A-Z0-9])CAT-[A-Z2-7]{10,16}(?![A-Z0-9])", re.IGNORECASE)
# Código curto em mensagem pré-preenchida do CTWA (fallback sem ctwa_clid).
_CTWA_CODIGO_RE = re.compile(
    r"(?:c[oó]d(?:igo)?|ref)\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9_-]{1,39})",
    re.IGNORECASE,
)
_UTM_CAMPAIGN_IN_TEXT_RE = re.compile(
    r"utm_campaign=([A-Za-z0-9][A-Za-z0-9_-]{1,119})",
    re.IGNORECASE,
)


def _limpar_tracking(valor: str | None, *, limite: int = 255) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    return s[:limite]


def extrair_codigo_ctwa_do_texto(texto: str | None) -> str | None:
    """Extrai código da mensagem (Cód: X / ref: X / utm_campaign=X)."""
    if not texto:
        return None
    m = _CTWA_CODIGO_RE.search(texto)
    if m:
        return m.group(1).strip()[:40]
    m2 = _UTM_CAMPAIGN_IN_TEXT_RE.search(texto)
    if m2:
        return m2.group(1).strip()[:40]
    return None


def _set_first_last(lead: Lead, campo: str, valor: str | None) -> None:
    if not valor:
        return
    first_name = f"{campo}_first"
    if hasattr(lead, first_name) and getattr(lead, first_name) is None:
        setattr(lead, first_name, valor)
    if hasattr(lead, campo):
        setattr(lead, campo, valor)


def aplicar_touch_ctwa(
    lead: Lead,
    *,
    ctwa_clid: str | None = None,
    meta_ad_id: str | None = None,
    meta_campaign_id: str | None = None,
    meta_adset_id: str | None = None,
    ctwa_source_type: str | None = None,
    ctwa_codigo: str | None = None,
    texto: str | None = None,
) -> bool:
    """Aplica sinais CTWA no lead (first/last). Retorna True se algo mudou de origem CTWA."""
    clid = _limpar_tracking(ctwa_clid, limite=255)
    ad_id = _limpar_tracking(meta_ad_id, limite=64)
    camp_id = _limpar_tracking(meta_campaign_id, limite=64)
    adset = _limpar_tracking(meta_adset_id, limite=64)
    source = _limpar_tracking(ctwa_source_type, limite=40)
    codigo = _limpar_tracking(ctwa_codigo, limite=40) or extrair_codigo_ctwa_do_texto(texto)

    tem_sinal = bool(clid or ad_id or camp_id or codigo)
    if not tem_sinal and not source:
        return False

    if clid:
        if lead.ctwa_clid_first is None:
            lead.ctwa_clid_first = clid
        lead.ctwa_clid = clid
    if ad_id:
        if lead.meta_ad_id_first is None:
            lead.meta_ad_id_first = ad_id
        lead.meta_ad_id = ad_id
    if camp_id:
        if lead.meta_campaign_id_first is None:
            lead.meta_campaign_id_first = camp_id
        lead.meta_campaign_id = camp_id
    if adset:
        lead.meta_adset_id = adset
    if source:
        lead.ctwa_source_type = source
    if codigo:
        if lead.ctwa_codigo_first is None:
            lead.ctwa_codigo_first = codigo
        lead.ctwa_codigo = codigo
        # Também preenche utm_campaign last se vazio — ajuda ROI por utm.
        if not lead.utm_campaign:
            _set_first_last(lead, "utm_campaign", codigo)

    # Origem tipada quando há sinal de anúncio WA
    if clid or ad_id or camp_id or codigo:
        if lead.origem_first is None:
            lead.origem_first = "meta_ctwa"
        lead.origem_last = "meta_ctwa"
        lead.origem = "meta_ctwa"
        if lead.canal_first is None:
            lead.canal_first = "whatsapp"
        lead.canal_last = "whatsapp"
        lead.canal = "whatsapp"
        if lead.ctwa_atribuido_em is None:
            lead.ctwa_atribuido_em = datetime.now(timezone.utc)
    return True


def _mascarar_telefone_curto(telefone: str) -> str:
    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    if len(digitos) >= 4:
        return f"***{digitos[-4:]}"
    return "***"


def _sufixo_seguro(valor: str | None, n: int = 8) -> str | None:
    if not valor:
        return None
    s = str(valor).strip()
    if not s:
        return None
    return s[-n:] if len(s) > n else s


def registrar_auditoria_ctwa(
    db: Session,
    *,
    loja_id: str,
    telefone: str,
    lead_id: str | None,
    provider_message_id: str | None,
    ctwa_clid: str | None,
    meta_ad_id: str | None,
    meta_campaign_id: str | None,
    meta_adset_id: str | None,
    ctwa_source_type: str | None,
    ctwa_codigo: str | None,
    codigo_do_texto: str | None,
    atribuido_lead: bool,
    forcar: bool = False,
) -> CtwaAuditoria | None:
    """Persiste linha de auditoria + log estruturado (sem telefone/clid completos)."""
    clid = _limpar_tracking(ctwa_clid, limite=255)
    ad_id = _limpar_tracking(meta_ad_id, limite=64)
    camp_id = _limpar_tracking(meta_campaign_id, limite=64)
    adset = _limpar_tracking(meta_adset_id, limite=64)
    source = _limpar_tracking(ctwa_source_type, limite=40)
    codigo = _limpar_tracking(ctwa_codigo, limite=40) or _limpar_tracking(
        codigo_do_texto, limite=40
    )
    tem_sinal = bool(clid or ad_id or camp_id or adset or source or codigo)
    audit_all = (os.getenv("CHATBOT_CTWA_AUDIT_ALL") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not tem_sinal and not forcar and not audit_all:
        return None

    sinais = {
        "tem_ctwa_clid": bool(clid),
        "tem_meta_ad_id": bool(ad_id),
        "tem_meta_campaign_id": bool(camp_id),
        "tem_meta_adset_id": bool(adset),
        "tem_source_type": bool(source),
        "tem_codigo": bool(codigo),
        "codigo_do_texto": bool(codigo_do_texto),
        "atribuido_lead": atribuido_lead,
    }
    # Log operacional: confirma chegada sem vazar identificadores longos.
    logger.info(
        "ctwa_auditoria loja=%s tel=%s clid=%s ad=%s camp=%s codigo=%s atribuido=%s",
        loja_id[:8],
        _mascarar_telefone_curto(telefone),
        "sim" if clid else "nao",
        "sim" if ad_id else "nao",
        "sim" if camp_id else "nao",
        codigo or "-",
        "sim" if atribuido_lead else "nao",
    )

    row = CtwaAuditoria(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        lead_id=lead_id,
        telefone_mascarado=_mascarar_telefone_curto(telefone),
        provider_message_id=_limpar_tracking(provider_message_id, limite=120),
        tem_ctwa_clid=bool(clid),
        ctwa_clid_sufixo=_sufixo_seguro(clid, 8),
        meta_ad_id=ad_id,
        meta_campaign_id=camp_id,
        meta_adset_id=adset,
        ctwa_source_type=source,
        ctwa_codigo=codigo,
        codigo_extraido_texto=bool(codigo_do_texto),
        atribuido_lead=atribuido_lead,
        sinais_json=json.dumps(sinais, ensure_ascii=False, sort_keys=True)[:500],
        criada_em=datetime.now(timezone.utc),
    )
    db.add(row)
    return row


def listar_auditoria_ctwa(
    db: Session,
    loja_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    so_com_clid: bool = False,
) -> list[dict]:
    q = db.query(CtwaAuditoria).filter(CtwaAuditoria.loja_id == loja_id)
    if so_com_clid:
        q = q.filter(CtwaAuditoria.tem_ctwa_clid.is_(True))
    rows = (
        q.order_by(CtwaAuditoria.criada_em.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": r.id,
            "lead_id": r.lead_id,
            "telefone_mascarado": r.telefone_mascarado,
            "provider_message_id": r.provider_message_id,
            "tem_ctwa_clid": r.tem_ctwa_clid,
            "ctwa_clid_sufixo": r.ctwa_clid_sufixo,
            "meta_ad_id": r.meta_ad_id,
            "meta_campaign_id": r.meta_campaign_id,
            "meta_adset_id": r.meta_adset_id,
            "ctwa_source_type": r.ctwa_source_type,
            "ctwa_codigo": r.ctwa_codigo,
            "codigo_extraido_texto": r.codigo_extraido_texto,
            "atribuido_lead": r.atribuido_lead,
            "sinais": json.loads(r.sinais_json) if r.sinais_json else {},
            "criada_em": r.criada_em.isoformat() if r.criada_em else None,
        }
        for r in rows
    ]


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

        # Histórico completo em catalog_attributions; lead guarda first/last touch.
        if not lead.catalog_interest_ref:
            lead.catalog_interest_ref = atribuicao.catalog_interest_ref
            lead.veiculo_ref = atribuicao.veiculo_ref
            lead.atribuida_em = agora
        else:
            # Novo clique: atualiza ref/veículo "atuais" sem apagar first touch.
            lead.catalog_interest_ref = atribuicao.catalog_interest_ref
            lead.veiculo_ref = atribuicao.veiculo_ref or lead.veiculo_ref

        _aplicar_touch_do_atributo(lead, atribuicao)
        lead.atualizada_em = agora
        return atribuicao
    return None


def _aplicar_touch_do_atributo(lead: Lead, atribuicao: CatalogAttribution) -> None:
    """First touch só se vazio; last + utm_* legado sempre atualizam com valor novo."""
    pares = (
        ("origem", "origem"),
        ("canal", "canal"),
        ("utm_source", "utm_source"),
        ("utm_medium", "utm_medium"),
        ("utm_campaign", "utm_campaign"),
        ("utm_content", "utm_content"),
        ("utm_term", "utm_term"),
    )
    for attr_lead, attr_attr in pares:
        valor = getattr(atribuicao, attr_attr, None)
        if not valor:
            continue
        first_name = f"{attr_lead}_first"
        last_name = f"{attr_lead}_last"
        if getattr(lead, first_name, None) is None:
            setattr(lead, first_name, valor)
        setattr(lead, last_name, valor)
        # utm_* e origem/canal legados = last touch (compat Portal)
        setattr(lead, attr_lead, valor)
    if atribuicao.fbclid:
        lead.fbclid = atribuicao.fbclid
    if atribuicao.gclid:
        lead.gclid = atribuicao.gclid


def registrar_mensagem(
    db: Session,
    instancia: str,
    telefone: str,
    texto: str | None,
    provider_message_id: str | None = None,
    from_me: bool = False,
    origem_bot: bool = False,
    tipo: str | None = None,
    *,
    ctwa_clid: str | None = None,
    meta_ad_id: str | None = None,
    meta_campaign_id: str | None = None,
    meta_adset_id: str | None = None,
    ctwa_source_type: str | None = None,
    ctwa_codigo: str | None = None,
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
    ctwa_ok = False
    lead_ctwa_id = None
    if not from_me:
        atribuicao = _correlacionar_catalogo(db, loja.id, telefone, texto)
        # CTWA: cria/enriquece lead com click id ou código na mensagem.
        lead_ctwa = _get_or_create_lead(db, loja.id, telefone)
        codigo_txt = extrair_codigo_ctwa_do_texto(texto)
        ctwa_ok = aplicar_touch_ctwa(
            lead_ctwa,
            ctwa_clid=ctwa_clid,
            meta_ad_id=meta_ad_id,
            meta_campaign_id=meta_campaign_id,
            meta_adset_id=meta_adset_id,
            ctwa_source_type=ctwa_source_type,
            ctwa_codigo=ctwa_codigo,
            texto=texto,
        )
        if ctwa_ok:
            lead_ctwa.atualizada_em = datetime.now(timezone.utc)
            lead_ctwa_id = lead_ctwa.id
        # Auditoria: sempre que houver sinal CTWA (ou CHATBOT_CTWA_AUDIT_ALL=1).
        registrar_auditoria_ctwa(
            db,
            loja_id=loja.id,
            telefone=telefone,
            lead_id=lead_ctwa.id if (ctwa_ok or lead_ctwa) else None,
            provider_message_id=provider_message_id,
            ctwa_clid=ctwa_clid,
            meta_ad_id=meta_ad_id,
            meta_campaign_id=meta_campaign_id,
            meta_adset_id=meta_adset_id,
            ctwa_source_type=ctwa_source_type,
            ctwa_codigo=ctwa_codigo,
            codigo_do_texto=codigo_txt,
            atribuido_lead=ctwa_ok,
        )
        if not ctwa_ok:
            lead_ctwa_id = lead_ctwa.id

    # Uma saída nova com conteúdo que não foi previamente registrada pelo workflow
    # do bot veio do atendente (celular/web). O humano assumiu: pausa automática.
    # Exceção: número autorizado (menu de estoque) não entra em handoff de vendas.
    if from_me and not origem_bot:
        from app import operacao as operacao_mod

        if operacao_mod.esta_autorizado(db, loja.id, telefone):
            # Eco/fromMe da equipe não deve matar o menu de operação.
            pass
        else:
            conversa.bot_ativo = False
            conversa.status = "handoff"
    elif not from_me:
        # Entrada da equipe autorizada: reativa bot (menu de operação).
        from app import operacao as operacao_mod

        if operacao_mod.esta_autorizado(db, loja.id, telefone) and not conversa.bot_ativo:
            conversa.bot_ativo = True
            if conversa.status == "handoff":
                conversa.status = "aberta"

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
        "ctwa_atribuido": bool(ctwa_ok) if not from_me else False,
        "lead_id": lead_ctwa_id if not from_me else None,
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
    fbclid: str | None = None,
    gclid: str | None = None,
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
        fbclid=fbclid,
        gclid=gclid,
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


def atualizar_etapa_lead(
    db: Session, loja_id: str, lead_id: str, etapa: str
) -> Lead:
    """Move um lead no funil sem permitir acesso cruzado entre lojas."""
    lead = obter_lead(db, loja_id, lead_id)
    lead.etapa = etapa
    lead.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
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
        "origem_first": lead.origem_first,
        "canal_first": lead.canal_first,
        "utm_source_first": lead.utm_source_first,
        "utm_medium_first": lead.utm_medium_first,
        "utm_campaign_first": lead.utm_campaign_first,
        "utm_content_first": lead.utm_content_first,
        "utm_term_first": lead.utm_term_first,
        "origem_last": lead.origem_last or lead.origem,
        "canal_last": lead.canal_last or lead.canal,
        "utm_source_last": lead.utm_source_last or lead.utm_source,
        "utm_medium_last": lead.utm_medium_last or lead.utm_medium,
        "utm_campaign_last": lead.utm_campaign_last or lead.utm_campaign,
        "utm_content_last": lead.utm_content_last or lead.utm_content,
        "utm_term_last": lead.utm_term_last or lead.utm_term,
        "fbclid": lead.fbclid,
        "gclid": lead.gclid,
        "ctwa_clid": lead.ctwa_clid,
        "ctwa_clid_first": lead.ctwa_clid_first,
        "meta_ad_id": lead.meta_ad_id,
        "meta_ad_id_first": lead.meta_ad_id_first,
        "meta_campaign_id": lead.meta_campaign_id,
        "meta_campaign_id_first": lead.meta_campaign_id_first,
        "meta_adset_id": lead.meta_adset_id,
        "ctwa_source_type": lead.ctwa_source_type,
        "ctwa_codigo": lead.ctwa_codigo,
        "ctwa_codigo_first": lead.ctwa_codigo_first,
        "ctwa_atribuido_em": lead.ctwa_atribuido_em.isoformat()
        if lead.ctwa_atribuido_em
        else None,
        "veiculo_ref": lead.veiculo_ref,
        "catalog_interest_ref": lead.catalog_interest_ref,
        "atribuida_em": lead.atribuida_em.isoformat() if lead.atribuida_em else None,
        "atualizada_em": lead.atualizada_em.isoformat() if lead.atualizada_em else None,
    }


def _momento_utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def listar_eventos_funil(
    db: Session,
    loja_id: str,
    *,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """Projeta eventos analíticos sem expor telefone, texto ou outros dados pessoais."""
    leads = (
        db.query(Lead)
        .filter(Lead.loja_id == loja_id)
        .order_by(Lead.criada_em.asc(), Lead.id.asc())
        .limit(max(1, min(limit, 1000)))
        .offset(max(0, offset))
        .all()
    )
    if not leads:
        return []

    telefones = {lead.telefone for lead in leads}
    conversas = (
        db.query(Conversa)
        .filter(Conversa.loja_id == loja_id, Conversa.telefone.in_(telefones))
        .all()
    )
    telefone_por_conversa = {conversa.id: conversa.telefone for conversa in conversas}
    saidas_por_telefone: dict[str, list[Mensagem]] = {}
    if telefone_por_conversa:
        mensagens = (
            db.query(Mensagem)
            .filter(
                Mensagem.loja_id == loja_id,
                Mensagem.conversa_id.in_(telefone_por_conversa),
                Mensagem.direcao == "saida",
            )
            .order_by(Mensagem.criada_em.asc(), Mensagem.id.asc())
            .all()
        )
        for mensagem in mensagens:
            telefone = telefone_por_conversa[mensagem.conversa_id]
            saidas_por_telefone.setdefault(telefone, []).append(mensagem)

    eventos: list[dict] = []
    for lead in leads:
        criado_em = _momento_utc(lead.criada_em)
        eventos.append(
            {
                "lead_ref": lead.id,
                "tipo": "lead_criado",
                "ocorrido_em": criado_em.isoformat(),
                "idempotency_key": f"chatbot:lead:{lead.id}:criado",
                # A projeção temporal não precisa de campos livres do lead. Manter
                # payload vazio evita transportar PII acidental entre produtos.
                "payload": None,
            }
        )
        primeira_saida = next(
            (
                mensagem
                for mensagem in saidas_por_telefone.get(lead.telefone, [])
                if _momento_utc(mensagem.criada_em) >= criado_em
            ),
            None,
        )
        if primeira_saida is None:
            continue
        respondido_em = _momento_utc(primeira_saida.criada_em)
        eventos.append(
            {
                "lead_ref": lead.id,
                "tipo": "primeira_resposta",
                "ocorrido_em": respondido_em.isoformat(),
                "idempotency_key": f"chatbot:mensagem:{primeira_saida.id}:primeira-resposta",
                "payload": None,
            }
        )
    return sorted(eventos, key=lambda item: (item["ocorrido_em"], item["idempotency_key"]))
