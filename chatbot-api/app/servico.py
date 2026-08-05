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
from sqlalchemy import and_, or_
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
    WhatsAppCanal,
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
        codigo = m.group(1).strip()[:40]
        # Referências CAT pertencem ao fluxo do catálogo e nunca devem mudar a
        # origem do lead para meta_ctwa.
        if not _CATALOG_REF_RE.fullmatch(codigo):
            return codigo
    m2 = _UTM_CAMPAIGN_IN_TEXT_RE.search(texto)
    if m2:
        codigo = m2.group(1).strip()[:40]
        if not _CATALOG_REF_RE.fullmatch(codigo):
            return codigo
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

    tem_sinal = bool(clid or ad_id or camp_id or adset or source or codigo)
    if not tem_sinal:
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
    if tem_sinal:
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


def _carregar_tracking_pendente(conversa: Conversa) -> dict:
    if not conversa.tracking_pendente_json:
        return {}
    try:
        dados = json.loads(conversa.tracking_pendente_json)
        return dados if isinstance(dados, dict) else {}
    except (TypeError, ValueError):
        return {}


def _registrar_touch_ctwa_pendente(
    conversa: Conversa,
    *,
    ctwa_clid: str | None = None,
    meta_ad_id: str | None = None,
    meta_campaign_id: str | None = None,
    meta_adset_id: str | None = None,
    ctwa_source_type: str | None = None,
    ctwa_codigo: str | None = None,
    texto: str | None = None,
) -> bool:
    """Preserva o anúncio na conversa sem transformar interesse em lead."""
    valores = {
        "ctwa_clid": _limpar_tracking(ctwa_clid, limite=255),
        "meta_ad_id": _limpar_tracking(meta_ad_id, limite=64),
        "meta_campaign_id": _limpar_tracking(meta_campaign_id, limite=64),
        "meta_adset_id": _limpar_tracking(meta_adset_id, limite=64),
        "ctwa_source_type": _limpar_tracking(ctwa_source_type, limite=40),
        "ctwa_codigo": _limpar_tracking(ctwa_codigo, limite=40)
        or extrair_codigo_ctwa_do_texto(texto),
    }
    if not any(valores.values()):
        return False
    dados = _carregar_tracking_pendente(conversa)
    for campo, valor in valores.items():
        if not valor:
            continue
        primeiro = f"{campo}_first"
        if campo in {"ctwa_clid", "meta_ad_id", "meta_campaign_id", "ctwa_codigo"}:
            dados.setdefault(primeiro, valor)
        dados[campo] = valor
    conversa.tracking_pendente_json = json.dumps(
        dados, ensure_ascii=False, sort_keys=True
    )
    return True


def _aplicar_tracking_pendente_no_lead(conversa: Conversa, lead: Lead) -> bool:
    dados = _carregar_tracking_pendente(conversa)
    if not dados:
        return False
    # CPF da simulação não é tracking de anúncio: preserva ao limpar o restante.
    cpf_cliente = dados.get("cpf_cliente")
    aplicar_touch_ctwa(
        lead,
        ctwa_clid=dados.get("ctwa_clid_first"),
        meta_ad_id=dados.get("meta_ad_id_first"),
        meta_campaign_id=dados.get("meta_campaign_id_first"),
        ctwa_codigo=dados.get("ctwa_codigo_first"),
    )
    aplicado = aplicar_touch_ctwa(
        lead,
        ctwa_clid=dados.get("ctwa_clid"),
        meta_ad_id=dados.get("meta_ad_id"),
        meta_campaign_id=dados.get("meta_campaign_id"),
        meta_adset_id=dados.get("meta_adset_id"),
        ctwa_source_type=dados.get("ctwa_source_type"),
        ctwa_codigo=dados.get("ctwa_codigo"),
    )
    if cpf_cliente and _cpf_valido(str(cpf_cliente)):
        conversa.tracking_pendente_json = json.dumps(
            {"cpf_cliente": str(cpf_cliente)}, ensure_ascii=False, sort_keys=True
        )
    else:
        conversa.tracking_pendente_json = None
    return aplicado


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


def extrair_cpf(texto: str | None) -> str | None:
    """Primeiro CPF válido (11 dígitos) no texto livre, ou None.

    Usado para preservar o valor para a tool de simulação sem expor no histórico
    mascarado (UI/Portal). Não aceita máscara (****) nem sequências inválidas.
    """
    if not texto:
        return None
    for m in _RE_CPF_FMT.finditer(texto):
        digitos = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
        if _cpf_valido(digitos):
            return digitos
    for m in _RE_CPF_BARE.finditer(texto):
        digitos = m.group(1)
        if _cpf_valido(digitos):
            return digitos
    return None


def _salvar_cpf_cliente(conversa: Conversa, cpf_digitos: str) -> None:
    """Guarda CPF na conversa (tracking_pendente_json) para o n8n/simular1."""
    if not cpf_digitos or not _cpf_valido(cpf_digitos):
        return
    dados = _carregar_tracking_pendente(conversa)
    dados["cpf_cliente"] = cpf_digitos
    conversa.tracking_pendente_json = json.dumps(
        dados, ensure_ascii=False, sort_keys=True
    )


def _obter_cpf_cliente(conversa: Conversa) -> str | None:
    digitos = str(_carregar_tracking_pendente(conversa).get("cpf_cliente") or "")
    return digitos if _cpf_valido(digitos) else None


def limpar_cpf_cliente_conversa(db: Session, loja_id: str, telefone: str) -> None:
    """Remove CPF guardado após simulação registrada (minimiza retenção)."""
    from app.hardening import normalizar_telefone_webhook

    try:
        telefone_norm = normalizar_telefone_webhook(telefone)
    except Exception:
        return
    for conversa in _listar_conversas_telefone(db, loja_id, telefone_norm):
        dados = _carregar_tracking_pendente(conversa)
        if "cpf_cliente" not in dados:
            continue
        dados.pop("cpf_cliente", None)
        conversa.tracking_pendente_json = (
            json.dumps(dados, ensure_ascii=False, sort_keys=True) if dados else None
        )
    db.commit()


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
    """Resolve loja pela instância Evolution (compat).

    Preferência: canal em ``whatsapp_canais`` (multi-WA); fallback legado em
    ``Loja.evolution_instance``.
    """
    loja, _canal = resolver_loja_e_canal_por_instancia(db, instancia)
    return loja


def resolver_loja_e_canal_por_instancia(
    db: Session, instancia: str
) -> tuple[Loja, "WhatsAppCanal"]:
    """Resolve loja + canal pela instância; rejeita instância desconhecida.

    Garante canal (backfill legado se necessário) para conversas multi-WA.
    """
    from app import channels
    from app.models_db import WhatsAppCanal

    canal = channels.resolve_canal_for_instance(db, instancia)
    loja = db.get(Loja, canal.loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="instância não reconhecida")
    return loja, canal


def _get_or_create_conversa(
    db: Session,
    loja_id: str,
    telefone: str,
    *,
    canal_id: str | None = None,
) -> Conversa:
    """Cria/localiza conversa.

    Com ``canal_id``: chave (canal_id, telefone) — dois números da mesma loja
    geram conversas distintas para o mesmo cliente. Adota conversa legada
    (canal_id nulo) na primeira mensagem do canal, preservando handoff/estado.
    Sem canal: (loja_id, telefone) como antes.
    """
    if canal_id:
        conversa = (
            db.query(Conversa)
            .filter(Conversa.canal_id == canal_id, Conversa.telefone == telefone)
            .first()
        )
        if conversa is not None:
            return conversa
        # Primeira mensagem neste canal: adota conversa legada sem canal_id.
        legado = (
            db.query(Conversa)
            .filter(
                Conversa.loja_id == loja_id,
                Conversa.telefone == telefone,
                Conversa.canal_id.is_(None),
            )
            .order_by(Conversa.criada_em.asc())
            .first()
        )
        if legado is not None:
            legado.canal_id = canal_id
            db.flush()
            return legado
        conversa = Conversa(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            canal_id=canal_id,
            telefone=telefone,
        )
        db.add(conversa)
        db.flush()
        return conversa

    conversa = (
        db.query(Conversa)
        .filter(Conversa.loja_id == loja_id, Conversa.telefone == telefone)
        .order_by(Conversa.criada_em.asc())
        .first()
    )
    if conversa is None:
        conversa = Conversa(id=str(uuid.uuid4()), loja_id=loja_id, telefone=telefone)
        db.add(conversa)
        db.flush()
    return conversa


def _mensagem_existente(
    db: Session,
    loja_id: str,
    provider_message_id: str,
    *,
    canal_id: str | None = None,
) -> Mensagem | None:
    """Dedupe: por canal quando há canal_id; senão por loja (legado)."""
    if canal_id:
        return (
            db.query(Mensagem)
            .filter(
                Mensagem.canal_id == canal_id,
                Mensagem.provider_message_id == provider_message_id,
            )
            .first()
        )
    return (
        db.query(Mensagem)
        .filter(
            Mensagem.loja_id == loja_id,
            Mensagem.provider_message_id == provider_message_id,
        )
        .first()
    )


def _formatar_historico_recente(
    db: Session, conversa_id: str, *, limit: int = 10
) -> str:
    """Últimas N mensagens da conversa em texto compacto para o prompt do n8n."""
    msgs = (
        db.query(Mensagem)
        .filter(Mensagem.conversa_id == conversa_id)
        .order_by(Mensagem.criada_em.desc(), Mensagem.id.desc())
        .limit(limit)
        .all()
    )
    linhas: list[str] = []
    for m in reversed(msgs):
        txt = (m.texto or "").replace("\n", " ").strip()
        if not txt:
            continue
        if len(txt) > 180:
            txt = txt[:180] + "…"
        tag = "entrada" if m.direcao == "entrada" else "saida"
        linhas.append(f"- [{tag}] {txt}")
    return "\n".join(linhas)


def _conversa_tem_saida(db: Session, conversa_id: str) -> bool:
    return (
        db.query(Mensagem.id)
        .filter(Mensagem.conversa_id == conversa_id, Mensagem.direcao == "saida")
        .first()
        is not None
    )


def _resposta_duplicada(
    conversa: Conversa,
    *,
    captura_passiva: bool = False,
    evolution_instance: str | None = None,
    db: Session | None = None,
) -> dict:
    base: dict = {
        "duplicada": True,
        "conversa_id": conversa.id,
    }
    if evolution_instance:
        base["evolution_instance"] = evolution_instance
        base["canal_id"] = conversa.canal_id
    if db is not None:
        base["tem_saida"] = _conversa_tem_saida(db, conversa.id)
        base["historico_recente"] = _formatar_historico_recente(db, conversa.id)
        base["cpf_cliente"] = _obter_cpf_cliente(conversa)
    if captura_passiva:
        base.update(
            {
                "bot_ativo": False,
                "captura_passiva": True,
                "loja_operacional": False,
            }
        )
        return base
    base["bot_ativo"] = conversa.bot_ativo
    return base


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


def _vincular_catalogo_ao_lead(
    lead: Lead, atribuicao: CatalogAttribution
) -> None:
    """Vincula um clique já correlacionado somente a um lead qualificado."""
    agora = datetime.now(timezone.utc)
    atribuicao.lead_id = lead.id
    if atribuicao.atribuida_em is None:
        atribuicao.atribuida_em = agora
    if not lead.catalog_interest_ref:
        lead.catalog_interest_ref = atribuicao.catalog_interest_ref
        lead.veiculo_ref = atribuicao.veiculo_ref
        lead.atribuida_em = atribuicao.atribuida_em
    else:
        lead.catalog_interest_ref = atribuicao.catalog_interest_ref
        lead.veiculo_ref = atribuicao.veiculo_ref or lead.veiculo_ref
    _aplicar_touch_do_atributo(lead, atribuicao)
    lead.atualizada_em = agora


def _correlacionar_catalogo(
    db: Session, loja_id: str, telefone: str, texto: str | None
) -> CatalogAttribution | None:
    """Guarda a referência no telefone; só cria vínculo com lead já qualificado."""
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
        if atribuicao.telefone and atribuicao.telefone != telefone:
            return None

        agora = datetime.now(timezone.utc)
        if not atribuicao.telefone:
            atribuicao.telefone = telefone
            atribuicao.atribuida_em = agora

        lead = (
            db.query(Lead)
            .filter(Lead.loja_id == loja_id, Lead.telefone == telefone)
            .first()
        )
        if lead is not None and not atribuicao.lead_id:
            _vincular_catalogo_ao_lead(lead, atribuicao)
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
    if atribuicao.gbraid:
        lead.gbraid = atribuicao.gbraid
    if atribuicao.wbraid:
        lead.wbraid = atribuicao.wbraid


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

    Gate operacional (ADR 0001): loja não operacional → CAPTURE (persiste/dedupe),
    força ``bot_ativo: false`` e ``captura_passiva: true`` para o n8n não atender.
    """
    from app import provisioning

    loja, canal = resolver_loja_e_canal_por_instancia(db, instancia)
    canal_id = canal.id
    evolution_instance = canal.evolution_instance
    loja_operacional = provisioning.is_store_operational(db, loja.id)
    captura_passiva = not loja_operacional
    conversa = _get_or_create_conversa(db, loja.id, telefone, canal_id=canal_id)

    if provider_message_id and _mensagem_existente(
        db, loja.id, provider_message_id, canal_id=canal_id
    ):
        return _resposta_duplicada(
            conversa,
            captura_passiva=captura_passiva,
            evolution_instance=evolution_instance,
            db=db,
        )

    # O workflow usa este sinal para humanizar somente a primeira resposta.
    # Consideramos a primeira entrada real do cliente, mesmo que ja exista uma
    # saida anterior na conversa.
    primeira_mensagem = (
        db.query(Mensagem.id)
        .filter(
            Mensagem.conversa_id == conversa.id,
            Mensagem.direcao == "entrada",
        )
        .first()
        is None
    )
    # Sinais para o gate n8n e o prompt da IA (antes de gravar a msg atual).
    tem_saida = _conversa_tem_saida(db, conversa.id)
    historico_recente = _formatar_historico_recente(db, conversa.id)

    # Eventos sem conteúdo (ack/recibo/status/reação ou texto vazio): não pausam e
    # não gravam mensagem fantasma. O n8n idealmente nem encaminha esses eventos.
    if from_me and not origem_bot and _eh_evento_sem_conteudo(texto, tipo):
        if captura_passiva:
            return {
                "duplicada": False,
                "conversa_id": conversa.id,
                "bot_ativo": False,
                "ignorada": True,
                "captura_passiva": True,
                "loja_operacional": False,
                "evolution_instance": evolution_instance,
                "canal_id": canal_id,
            }
        return {
            "duplicada": False,
            "conversa_id": conversa.id,
            "bot_ativo": conversa.bot_ativo,
            "ignorada": True,
            "evolution_instance": evolution_instance,
            "canal_id": canal_id,
        }

    atribuicao = None
    ctwa_ok = False
    ctwa_pendente = False
    lead_ctwa = None
    lead_ctwa_id = None
    lead_criado_auto = False
    if not from_me and loja_operacional:
        # Correlação e touch de lead só quando a loja processa (não só captura).
        atribuicao = _correlacionar_catalogo(db, loja.id, telefone, texto)
        codigo_txt = extrair_codigo_ctwa_do_texto(texto)
        tem_sinal_ctwa = any(
            _limpar_tracking(valor)
            for valor in (
                ctwa_clid,
                meta_ad_id,
                meta_campaign_id,
                meta_adset_id,
                ctwa_source_type,
                ctwa_codigo,
                codigo_txt,
            )
        )
        # Interesse em anúncio não é lead. Se já houver lead qualificado, enriquece;
        # caso contrário, guarda o tracking na conversa até a etapa da simulação.
        if tem_sinal_ctwa:
            lead_ctwa = (
                db.query(Lead)
                .filter(Lead.loja_id == loja.id, Lead.telefone == telefone)
                .first()
            )
            if lead_ctwa is not None:
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
            else:
                ctwa_pendente = _registrar_touch_ctwa_pendente(
                    conversa,
                    ctwa_clid=ctwa_clid,
                    meta_ad_id=meta_ad_id,
                    meta_campaign_id=meta_campaign_id,
                    meta_adset_id=meta_adset_id,
                    ctwa_source_type=ctwa_source_type,
                    ctwa_codigo=ctwa_codigo,
                    texto=texto,
                )
        # Fase 1: o lead nasce na 2ª mensagem de uma conversa originada de anúncio.
        # `primeira_mensagem` foi calculado ANTES de gravar a msg atual: quando é
        # False, o cliente já respondeu de verdade. `lead_ctwa is None` aqui só
        # quando ainda não há lead com sinal CTWA nesta entrada. Escopo restrito a
        # conversas com tracking CTWA pendente (não enche o CRM com não-anúncio);
        # para estender a toda conversa, trocar `tem_ctwa_pend` por `True`.
        if lead_ctwa is None and not primeira_mensagem:
            pend = _carregar_tracking_pendente(conversa)
            tem_ctwa_pend = any(
                pend.get(k)
                for k in ("ctwa_clid", "meta_ad_id", "meta_campaign_id", "ctwa_codigo")
            )
            if tem_ctwa_pend:
                lead_existente = (
                    db.query(Lead)
                    .filter(Lead.loja_id == loja.id, Lead.telefone == telefone)
                    .first()
                )
                if lead_existente is None:
                    lead_novo = _get_or_create_lead(db, loja.id, telefone)
                    _vincular_tracking_pendente_ao_lead(
                        db, loja.id, telefone, lead_novo
                    )
                    if not lead_novo.origem:
                        lead_novo.origem = "meta_ctwa"
                    lead_novo.atualizada_em = datetime.now(timezone.utc)
                    lead_ctwa_id = lead_novo.id
                    lead_criado_auto = True
                else:
                    # Idempotente: lead já existe (ex.: POST /v1/leads anterior).
                    lead_ctwa_id = lead_existente.id
        registrar_auditoria_ctwa(
            db,
            loja_id=loja.id,
            telefone=telefone,
            lead_id=lead_ctwa_id,
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
    elif not from_me and captura_passiva:
        # Captura passiva: auditoria de tracking permanece; sem enriquecer lead.
        codigo_txt = extrair_codigo_ctwa_do_texto(texto)
        tem_sinal_ctwa = any(
            _limpar_tracking(valor)
            for valor in (
                ctwa_clid,
                meta_ad_id,
                meta_campaign_id,
                meta_adset_id,
                ctwa_source_type,
                ctwa_codigo,
                codigo_txt,
            )
        )
        if tem_sinal_ctwa:
            registrar_auditoria_ctwa(
                db,
                loja_id=loja.id,
                telefone=telefone,
                lead_id=None,
                provider_message_id=provider_message_id,
                ctwa_clid=ctwa_clid,
                meta_ad_id=meta_ad_id,
                meta_campaign_id=meta_campaign_id,
                meta_adset_id=meta_adset_id,
                ctwa_source_type=ctwa_source_type,
                ctwa_codigo=ctwa_codigo,
                codigo_do_texto=codigo_txt,
                atribuido_lead=False,
            )

    # Uma saída nova com conteúdo que não foi previamente registrada pelo workflow
    # do bot veio do atendente (celular/web). O humano assumiu: pausa automática.
    # Exceção: número autorizado (menu de estoque) não entra em handoff de vendas.
    # Em captura passiva: não reativa bot para números autorizados (sem atendimento).
    if loja_operacional:
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

            if (
                operacao_mod.esta_autorizado(db, loja.id, telefone)
                and not conversa.bot_ativo
            ):
                conversa.bot_ativo = True
                if conversa.status == "handoff":
                    conversa.status = "aberta"

    # CPF: captura no texto cru antes de mascarar; UI/histórico ficam mascarados.
    cpf_cliente = _obter_cpf_cliente(conversa)
    if not from_me:
        capturado = extrair_cpf(texto)
        if capturado:
            _salvar_cpf_cliente(conversa, capturado)
            cpf_cliente = capturado

    db.add(
        Mensagem(
            id=str(uuid.uuid4()),
            loja_id=loja.id,
            canal_id=canal_id,
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
        # Corrida: outra requisição gravou o mesmo (canal_id, provider_message_id)
        # entre o SELECT acima e o commit. A UNIQUE do banco arbitra; respondemos
        # idempotente em vez de estourar 500.
        db.rollback()
        conversa = _get_or_create_conversa(
            db, loja.id, telefone, canal_id=canal_id
        )
        return _resposta_duplicada(
            conversa,
            captura_passiva=captura_passiva,
            evolution_instance=evolution_instance,
            db=db,
        )
    # Outbound (n8n) deve usar a instância do canal da conversa.
    if captura_passiva:
        return {
            "duplicada": False,
            "conversa_id": conversa.id,
            "bot_ativo": False,
            "primeira_mensagem": primeira_mensagem,
            "tem_saida": tem_saida,
            "historico_recente": historico_recente,
            "cpf_cliente": cpf_cliente,
            "captura_passiva": True,
            "loja_operacional": False,
            "catalog_interest_ref": None,
            "ctwa_atribuido": False,
            "ctwa_pendente": False,
            "lead_criado_auto": False,
            "lead_id": None,
            "evolution_instance": evolution_instance,
            "canal_id": canal_id,
        }
    return {
        "duplicada": False,
        "conversa_id": conversa.id,
        "bot_ativo": conversa.bot_ativo,
        "primeira_mensagem": primeira_mensagem,
        "tem_saida": tem_saida,
        "historico_recente": historico_recente,
        "cpf_cliente": cpf_cliente,
        "catalog_interest_ref": atribuicao.catalog_interest_ref if atribuicao else None,
        "ctwa_atribuido": bool(ctwa_ok) if not from_me else False,
        "ctwa_pendente": bool(ctwa_pendente) if not from_me else False,
        "lead_criado_auto": bool(lead_criado_auto) if not from_me else False,
        "lead_id": (
            lead_ctwa_id
            or (atribuicao.lead_id if atribuicao is not None else None)
        )
        if not from_me
        else None,
        "evolution_instance": evolution_instance,
        "canal_id": canal_id,
    }


def _bot_ativo_efetivo(db: Session, loja_id: str, bot_ativo: bool) -> bool:
    """n8n só deve enviar se bot_ativo e loja operacional (ADR outbound BLOCK)."""
    from app import provisioning

    return bool(bot_ativo) and provisioning.allows_outbound_whatsapp(db, loja_id)


def _canal_id_opcional_por_instance(
    db: Session, loja_id: str, instance: str | None
) -> str | None:
    """Resolve canal_id da loja para escopo multi-WA; None = legado (1ª conversa)."""
    texto = (instance or "").strip()
    if not texto:
        return None
    from app import channels

    canal = channels.resolve_canal_for_instance(db, texto)
    if canal.loja_id != loja_id:
        raise HTTPException(status_code=404, detail="instância não reconhecida")
    return canal.id


def _resolver_canal_id_escopo(
    db: Session,
    loja_id: str,
    *,
    canal_id: str | None = None,
    instance: str | None = None,
) -> str | None:
    """Resolve canal a partir de ``canal_id`` e/ou ``instance`` (multi-WA).

    ``None`` = sem escopo de canal (legado / single-channel).
    Canal inexistente na loja → 404. Conflito canal_id×instance → 409.
    """
    from app import channels

    por_instance = _canal_id_opcional_por_instance(db, loja_id, instance)
    texto = (canal_id or "").strip() or None
    if not texto:
        return por_instance
    canal = channels.get_channel_for_loja(db, loja_id, texto)
    if por_instance is not None and por_instance != canal.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "canal_instance_mismatch",
                "message": "canal_id e instance não correspondem ao mesmo canal",
            },
        )
    return canal.id


def _listar_conversas_telefone(
    db: Session,
    loja_id: str,
    telefone: str,
    *,
    canal_id: str | None = None,
) -> list[Conversa]:
    q = db.query(Conversa).filter(
        Conversa.loja_id == loja_id, Conversa.telefone == telefone
    )
    if canal_id:
        q = q.filter(Conversa.canal_id == canal_id)
    return q.order_by(Conversa.criada_em.asc()).all()


def _exigir_conversa_unica(
    conversas: list[Conversa],
    *,
    canal_id: str | None,
) -> Conversa | None:
    """0 → None; 1 → conversa; >1 sem canal → 409 ambíguo multi-WA."""
    if not conversas:
        return None
    if canal_id is None and len(conversas) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "conversa_ambigua",
                "message": (
                    "múltiplas conversas para o telefone; "
                    "informe canal_id ou instance"
                ),
                "canais": [c.canal_id for c in conversas if c.canal_id],
            },
        )
    return conversas[0]


def conversa_tem_resposta(
    db: Session,
    loja_id: str,
    telefone: str,
    *,
    canal_id: str | None = None,
    instance: str | None = None,
) -> bool:
    """True se a conversa deste telefone já teve alguma saída (bot ou atendente
    já respondeu). O roteamento usa isto para não reavaliar como primeiro
    contato uma conversa que o bot já está tocando."""
    resolved = _resolver_canal_id_escopo(
        db, loja_id, canal_id=canal_id, instance=instance
    )
    conversas = _listar_conversas_telefone(db, loja_id, telefone, canal_id=resolved)
    if not conversas:
        return False
    ids = [c.id for c in conversas]
    return (
        db.query(Mensagem.id)
        .filter(Mensagem.conversa_id.in_(ids), Mensagem.direcao == "saida")
        .first()
        is not None
    )


def obter_estado(
    db: Session,
    loja_id: str,
    telefone: str,
    *,
    canal_id: str | None = None,
    instance: str | None = None,
) -> dict:
    resolved = _resolver_canal_id_escopo(
        db, loja_id, canal_id=canal_id, instance=instance
    )
    conversas = _listar_conversas_telefone(
        db, loja_id, telefone, canal_id=resolved
    )
    conversa = _exigir_conversa_unica(conversas, canal_id=resolved)
    if conversa is None:
        return {
            "bot_ativo": _bot_ativo_efetivo(db, loja_id, True),
            "status": "aberta",
        }
    return {
        "bot_ativo": _bot_ativo_efetivo(db, loja_id, conversa.bot_ativo),
        "status": conversa.status,
    }


def pode_responder_mensagem(
    db: Session,
    loja_id: str,
    telefone: str,
    provider_message_id: str,
    *,
    instance: str,
) -> dict:
    """Autoriza somente a última entrada ainda sem uma saída posterior.

    O n8n chama este juiz depois do debounce. Execuções de mensagens anteriores
    param aqui, assim como uma execução que perdeu a corrida para outra resposta.
    """
    resolved = _resolver_canal_id_escopo(db, loja_id, instance=instance)
    conversas = _listar_conversas_telefone(
        db, loja_id, telefone, canal_id=resolved
    )
    conversa = _exigir_conversa_unica(conversas, canal_id=resolved)
    if conversa is None:
        return {"pode_responder": False, "motivo": "conversa_nao_encontrada"}
    if not _bot_ativo_efetivo(db, loja_id, conversa.bot_ativo):
        return {"pode_responder": False, "motivo": "bot_inativo"}

    ultima = (
        db.query(Mensagem)
        .filter(
            Mensagem.loja_id == loja_id,
            Mensagem.conversa_id == conversa.id,
        )
        .order_by(Mensagem.criada_em.desc(), Mensagem.id.desc())
        .first()
    )
    if ultima is None:
        return {"pode_responder": False, "motivo": "conversa_sem_mensagem"}
    if ultima.direcao != "entrada":
        return {"pode_responder": False, "motivo": "ultima_mensagem_saida"}
    if ultima.provider_message_id != provider_message_id:
        return {"pode_responder": False, "motivo": "mensagem_superada"}
    return {"pode_responder": True, "motivo": "ultima_entrada"}


def definir_bot_ativo(
    db: Session,
    loja_id: str,
    telefone: str,
    ativo: bool,
    *,
    canal_id: str | None = None,
    instance: str | None = None,
) -> dict:
    from app import provisioning

    if ativo and not provisioning.allows_outbound_whatsapp(db, loja_id):
        raise HTTPException(
            status_code=423,
            detail={
                "code": "store_not_operational",
                "message": "loja não operacional",
                "loja_operacional": False,
            },
        )
    resolved = _resolver_canal_id_escopo(
        db, loja_id, canal_id=canal_id, instance=instance
    )
    if resolved is None:
        # Sem canal: se já há várias conversas, não adivinhar qual pausar.
        existentes = _listar_conversas_telefone(db, loja_id, telefone)
        _exigir_conversa_unica(existentes, canal_id=None)
        if len(existentes) == 1:
            resolved = existentes[0].canal_id
    conversa = _get_or_create_conversa(db, loja_id, telefone, canal_id=resolved)
    conversa.bot_ativo = ativo
    conversa.status = "aberta" if ativo else "handoff"
    conversa.atualizada_em = datetime.now(timezone.utc)
    db.commit()
    return {
        "bot_ativo": _bot_ativo_efetivo(db, loja_id, conversa.bot_ativo),
        "status": conversa.status,
    }


# --- Conversas e mensagens (handoff/Portal) ----------------------------------


_PREVIEW_MAX = 120


def listar_conversas(
    db: Session,
    loja_id: str,
    limit: int,
    offset: int,
    busca: str | None = None,
    canal_id: str | None = None,
) -> list[dict]:
    q = db.query(Conversa).filter(Conversa.loja_id == loja_id)
    if busca:
        q = q.filter(Conversa.telefone.contains(busca))
    if canal_id:
        q = q.filter(Conversa.canal_id == canal_id)
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

    canal_ids = {c.canal_id for c in conversas if c.canal_id}
    canais_por_id: dict[str, WhatsAppCanal] = {}
    if canal_ids:
        for canal in (
            db.query(WhatsAppCanal).filter(WhatsAppCanal.id.in_(canal_ids)).all()
        ):
            canais_por_id[canal.id] = canal

    return [
        para_saida_conversa(
            c,
            ultima_por_conversa.get(c.id),
            canal=canais_por_id.get(c.canal_id) if c.canal_id else None,
        )
        for c in conversas
    ]


def listar_mensagens(
    db: Session,
    loja_id: str,
    telefone: str,
    limit: int,
    offset: int,
    *,
    canal_id: str | None = None,
    instance: str | None = None,
    after_id: str | None = None,
    after_criada_em: str | None = None,
) -> dict:
    """Histórico de mensagens da conversa (loja, telefone[, canal]).

    Multi-WA: sem ``canal_id``/``instance`` e com 2+ conversas no telefone → 409.
    Single-channel (1 conversa) continua sem precisar de canal.

    Cursor (polling):
    - ``after_id``: mensagens estritamente posteriores ao id na conversa
      (ordem ``criada_em`` asc, desempate por ``id``). Se o id não existir
      nesta conversa → 404.
    - ``after_criada_em``: ISO timestamp; usado só se ``after_id`` ausente.
      Retorna mensagens com ``criada_em`` estritamente maior.
    - Sem cursor: paginação clássica ``limit``/``offset``.
    """
    resolved = _resolver_canal_id_escopo(
        db, loja_id, canal_id=canal_id, instance=instance
    )
    conversas = _listar_conversas_telefone(
        db, loja_id, telefone, canal_id=resolved
    )
    conversa = _exigir_conversa_unica(conversas, canal_id=resolved)
    if conversa is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")

    base = db.query(Mensagem).filter(
        Mensagem.loja_id == loja_id, Mensagem.conversa_id == conversa.id
    )
    cursor_after_id = (after_id or "").strip() or None
    cursor_after_ts = (after_criada_em or "").strip() or None

    if cursor_after_id:
        cursor_msg = (
            db.query(Mensagem)
            .filter(
                Mensagem.id == cursor_after_id,
                Mensagem.loja_id == loja_id,
                Mensagem.conversa_id == conversa.id,
            )
            .first()
        )
        if cursor_msg is None:
            raise HTTPException(
                status_code=404,
                detail="cursor after_id não encontrado nesta conversa",
            )
        # Estritamente posterior: (criada_em, id) > (cursor.criada_em, cursor.id)
        base = base.filter(
            or_(
                Mensagem.criada_em > cursor_msg.criada_em,
                and_(
                    Mensagem.criada_em == cursor_msg.criada_em,
                    Mensagem.id > cursor_msg.id,
                ),
            )
        )
        mensagens = (
            base.order_by(Mensagem.criada_em.asc(), Mensagem.id.asc())
            .limit(limit)
            .all()
        )
    elif cursor_after_ts:
        try:
            ts = datetime.fromisoformat(cursor_after_ts.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="after_criada_em inválido"
            ) from exc
        mensagens = (
            base.filter(Mensagem.criada_em > ts)
            .order_by(Mensagem.criada_em.asc(), Mensagem.id.asc())
            .limit(limit)
            .all()
        )
    else:
        mensagens = (
            base.order_by(Mensagem.criada_em.asc(), Mensagem.id.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    saida_msgs = [para_saida_mensagem(m) for m in mensagens]
    last_id = saida_msgs[-1]["id"] if saida_msgs else cursor_after_id
    return {
        "telefone": telefone,
        "canal_id": conversa.canal_id,
        "mensagens": saida_msgs,
        "after_id": cursor_after_id,
        "after_criada_em": cursor_after_ts if not cursor_after_id else None,
        "last_id": last_id,
    }


def _provider_id_humano(idempotency_key: str) -> str:
    """Chave estável para dedupe de envio humano (Portal → Chatbot)."""
    chave = (idempotency_key or "").strip()
    if not chave:
        raise HTTPException(status_code=422, detail="idempotency_key obrigatória")
    # Prefixo evita colisão com ids nativos do provedor WhatsApp.
    return f"human:{chave}"[:255]


def _resolver_instance_envio(
    db: Session, loja_id: str, conversa: Conversa
) -> str:
    """Resolve evolution_instance do canal da conversa ou legado da loja."""
    from app.models_db import WhatsAppCanal

    if conversa.canal_id:
        canal = db.get(WhatsAppCanal, conversa.canal_id)
        if canal is not None and (canal.evolution_instance or "").strip():
            return canal.evolution_instance.strip()
    loja = db.get(Loja, loja_id)
    if loja is not None and (loja.evolution_instance or "").strip():
        return loja.evolution_instance.strip()
    raise HTTPException(
        status_code=422,
        detail={
            "code": "evolution_instance_missing",
            "message": "conversa sem instância Evolution para envio",
        },
    )


def _enviar_texto_evolution(
    *,
    instance: str,
    number: str,
    text: str,
    mensagem_id: str,
    canal_id: str | None,
) -> None:
    """Push sendText. Em falha: mensagem já persistida e bot permanece pausado.

    Política: se o humano já assumiu (bot_ativo=False / handoff), NÃO reativamos
    o bot quando a Evolution falha — o atendimento humano continua no histórico
    e o Portal deve reenviar com nova idempotency_key se necessário.
    """
    from app.whatsapp_outbound import WhatsAppOutboundError, get_whatsapp_outbound

    try:
        get_whatsapp_outbound().send_text(
            instance=instance, number=number, text=text
        )
    except WhatsAppOutboundError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": getattr(exc, "code", None) or "evolution_send_failed",
                "message": str(exc) or "falha ao enviar via Evolution",
                "mensagem_id": mensagem_id,
                "bot_ativo": False,
                "status": "handoff",
                "enviado": False,
                "canal_id": canal_id,
                # Mensagem permanece no histórico; bot não é reativado.
                "preservado_no_historico": True,
            },
        ) from exc


def enviar_mensagem_humana(
    db: Session,
    loja_id: str,
    telefone: str,
    texto: str,
    *,
    idempotency_key: str,
    instance: str | None = None,
    ator: str | None = None,
) -> dict:
    """Persiste saída humana na conversa da loja, pausa o bot e envia via Evolution.

    Escopo: somente a loja autenticada (token de serviço) + telefone.
    Idempotente por ``idempotency_key`` (provider_message_id = human:…).
    Segunda chamada com a mesma chave não reenvia à Evolution (dedupe).

    Se a Evolution falhar após o commit: a mensagem permanece no histórico,
    o bot continua pausado (handoff) e a API responde 502 com detalhe.
    """
    from app import provisioning
    from app.hardening import normalizar_telefone_webhook

    if not provisioning.allows_outbound_whatsapp(db, loja_id):
        raise HTTPException(
            status_code=423,
            detail={
                "code": "store_not_operational",
                "message": "loja não operacional",
                "loja_operacional": False,
            },
        )

    try:
        telefone_norm = normalizar_telefone_webhook(telefone)
    except Exception:
        raise HTTPException(status_code=422, detail="telefone inválido") from None

    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        raise HTTPException(status_code=422, detail="texto vazio")
    if len(texto_limpo) > 4096:
        raise HTTPException(status_code=422, detail="texto excede o limite permitido")
    if "\x00" in texto_limpo:
        raise HTTPException(status_code=422, detail="texto inválido")

    provider_message_id = _provider_id_humano(idempotency_key)
    canal_id = _resolver_canal_id_escopo(db, loja_id, instance=instance)

    # Sem instance: reutiliza canal só se houver conversa única (evita .first() multi-WA).
    if canal_id is None:
        existentes = _listar_conversas_telefone(db, loja_id, telefone_norm)
        unica = _exigir_conversa_unica(existentes, canal_id=None)
        if unica is not None:
            canal_id = unica.canal_id

    existente = _mensagem_existente(
        db, loja_id, provider_message_id, canal_id=canal_id
    )
    if existente is not None:
        # Já enviada (ou persistida em tentativa anterior): não reenvia Evolution.
        conversa = db.get(Conversa, existente.conversa_id)
        return {
            "duplicada": True,
            "mensagem_id": existente.id,
            "telefone": telefone_norm,
            "texto": existente.texto,
            "bot_ativo": bool(conversa.bot_ativo) if conversa else False,
            "status": conversa.status if conversa else "handoff",
            "enviado": True,
            "canal_id": existente.canal_id,
            "ator": ator,
        }

    conversa = _get_or_create_conversa(
        db, loja_id, telefone_norm, canal_id=canal_id
    )
    # Humano assume: pausa bot (mesmo contrato do from_me atendente).
    conversa.bot_ativo = False
    conversa.status = "handoff"
    conversa.atualizada_em = datetime.now(timezone.utc)
    if ator and not conversa.responsavel:
        conversa.responsavel = ator[:120]

    mensagem_id = str(uuid.uuid4())
    texto_persistido = mascarar_cpf(texto_limpo) or texto_limpo
    instance_envio = _resolver_instance_envio(db, loja_id, conversa)

    db.add(
        Mensagem(
            id=mensagem_id,
            loja_id=loja_id,
            canal_id=conversa.canal_id,
            conversa_id=conversa.id,
            direcao="saida",
            provider_message_id=provider_message_id,
            texto=texto_persistido,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existente = _mensagem_existente(
            db, loja_id, provider_message_id, canal_id=conversa.canal_id
        )
        if existente is None:
            raise
        conversa = db.get(Conversa, existente.conversa_id)
        return {
            "duplicada": True,
            "mensagem_id": existente.id,
            "telefone": telefone_norm,
            "texto": existente.texto,
            "bot_ativo": bool(conversa.bot_ativo) if conversa else False,
            "status": conversa.status if conversa else "handoff",
            "enviado": True,
            "canal_id": existente.canal_id,
            "ator": ator,
        }

    # Após persistir + pausar: push real. Falha → 502; não desfaz handoff.
    _enviar_texto_evolution(
        instance=instance_envio,
        number=telefone_norm,
        text=texto_limpo,
        mensagem_id=mensagem_id,
        canal_id=conversa.canal_id,
    )

    return {
        "duplicada": False,
        "mensagem_id": mensagem_id,
        "telefone": telefone_norm,
        "texto": texto_persistido,
        "bot_ativo": False,
        "status": "handoff",
        "enviado": True,
        "canal_id": conversa.canal_id,
        "ator": ator,
        "evolution_instance": instance_envio,
    }


def para_saida_mensagem(msg: Mensagem) -> dict:
    return {
        "id": msg.id,
        "direcao": msg.direcao,
        "texto": mascarar_cpf(msg.texto),
        "criada_em": msg.criada_em.isoformat() if msg.criada_em else None,
    }


def _rotulo_canal_operacional(canal: WhatsAppCanal) -> str:
    """Rótulo seguro para UI: mascara E.164; mantém labels operacionais."""
    bruto = (canal.e164_or_label or "").strip()
    digitos = "".join(c for c in bruto if c.isdigit())
    # Número longo parece telefone — mascara; "legado"/"linha-2" passam intactos.
    if len(digitos) >= 8 and len(digitos) >= len(bruto) - 2:
        return _mascarar_telefone_curto(bruto)
    return bruto or canal.evolution_instance or canal.id


def para_saida_conversa(
    conversa: Conversa,
    ultima: Mensagem | None = None,
    *,
    canal: WhatsAppCanal | None = None,
) -> dict:
    ultima_saida = None
    if ultima is not None:
        texto = ultima.texto or ""
        ultima_saida = {
            "texto": texto[:_PREVIEW_MAX],
            "criada_em": ultima.criada_em.isoformat() if ultima.criada_em else None,
            "direcao": ultima.direcao,
        }
    saida: dict = {
        "id": conversa.id,
        "telefone": conversa.telefone,
        "bot_ativo": conversa.bot_ativo,
        "status": conversa.status,
        "atualizada_em": conversa.atualizada_em.isoformat()
        if conversa.atualizada_em
        else None,
        "ultima_mensagem": ultima_saida,
        # Multi-WA expand: campos nulos se conversa legada sem canal.
        "canal_id": conversa.canal_id,
        "evolution_instance": None,
        "canal_label": None,
        "numero_mascarado": None,
        "canal_ativo": None,
        "canal_estado": None,
    }
    if canal is not None:
        digitos = "".join(c for c in (canal.e164_or_label or "") if c.isdigit())
        saida["evolution_instance"] = canal.evolution_instance
        saida["canal_label"] = _rotulo_canal_operacional(canal)
        saida["numero_mascarado"] = (
            _mascarar_telefone_curto(canal.e164_or_label)
            if len(digitos) >= 4
            else None
        )
        saida["canal_ativo"] = bool(canal.ativo)
        saida["canal_estado"] = canal.estado
    return saida


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


def _vincular_tracking_pendente_ao_lead(
    db: Session, loja_id: str, telefone: str, lead: Lead
) -> None:
    atribuicoes = (
        db.query(CatalogAttribution)
        .filter(
            CatalogAttribution.loja_id == loja_id,
            CatalogAttribution.telefone == telefone,
            CatalogAttribution.lead_id.is_(None),
        )
        .order_by(CatalogAttribution.occurred_at.asc())
        .all()
    )
    for atribuicao in atribuicoes:
        _vincular_catalogo_ao_lead(lead, atribuicao)

    conversa = (
        db.query(Conversa)
        .filter(Conversa.loja_id == loja_id, Conversa.telefone == telefone)
        .first()
    )
    if conversa is not None:
        _aplicar_tracking_pendente_no_lead(conversa, lead)


def registrar_lead(
    db: Session,
    loja_id: str,
    telefone: str,
    nome: str | None = None,
    interesse: str | None = None,
    etapa: str | None = None,
) -> Lead:
    lead = _get_or_create_lead(db, loja_id, telefone)
    _vincular_tracking_pendente_ao_lead(db, loja_id, telefone, lead)
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
    gbraid: str | None = None,
    wbraid: str | None = None,
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
        gbraid=gbraid,
        wbraid=wbraid,
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
        "gbraid": lead.gbraid,
        "wbraid": lead.wbraid,
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
