"""Canais WhatsApp da loja (Fase 5 multi-WA).

Chatbot é dono de `whatsapp_canais`. Número/instância nunca muda de loja:
`loja_id` é imutável após o registro. Inativação é lógica (sem delete).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import config
from app.models_db import Loja, WhatsAppCanal
from app.whatsapp_provider import (
    ESTADO_CONECTADO,
    ESTADO_INATIVO,
    ESTADO_PENDENTE,
    WhatsAppProvider,
    WhatsAppProvisionError,
    get_whatsapp_provider,
)


def _canal_dict(canal: WhatsAppCanal) -> dict[str, Any]:
    return {
        "id": canal.id,
        "loja_id": canal.loja_id,
        "e164_or_label": canal.e164_or_label,
        "evolution_instance": canal.evolution_instance,
        "ativo": canal.ativo,
        "estado": canal.estado,
        "principal_estoque": bool(canal.principal_estoque),
        "criado_em": canal.criado_em.isoformat() if canal.criado_em else None,
        # Estado do onboarding Cloud, lido pela tela da Revy Loja: `waba_id` é o
        # que marca o canal como Modo 2, os dois `onboarding_*` dizem em que elo
        # parou. Canal Modo 1 devolve `None`, não ausência — a Loja lê direto.
        # Campos listados um a um de propósito: nunca devolver o modelo inteiro
        # nem usar `exclude`, senão a próxima coluna (token/PIN) volta a vazar.
        "waba_id": canal.waba_id,
        "template_oferta": canal.template_oferta,
        "onboarding_elo": canal.onboarding_elo,
        "onboarding_erro": canal.onboarding_erro,
    }


def _loja_tem_principal_estoque(db: Session, loja_id: str) -> bool:
    return (
        db.query(WhatsAppCanal)
        .filter(
            WhatsAppCanal.loja_id == loja_id,
            WhatsAppCanal.ativo.is_(True),
            WhatsAppCanal.principal_estoque.is_(True),
        )
        .first()
        is not None
    )


def obter_canal_principal_estoque(
    db: Session, loja_id: str
) -> WhatsAppCanal | None:
    """Canal que opera o grupo de estoque (menu + alertas de simulação).

    Preferência: flag ``principal_estoque``. Fallback: canal ativo mais antigo
    (compat multi-WA sem escolha explícita — evita dois bots respondendo).
    """
    explicit = (
        db.query(WhatsAppCanal)
        .filter(
            WhatsAppCanal.loja_id == loja_id,
            WhatsAppCanal.ativo.is_(True),
            WhatsAppCanal.principal_estoque.is_(True),
        )
        .order_by(WhatsAppCanal.criado_em.asc())
        .first()
    )
    if explicit is not None:
        return explicit
    return (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja_id, WhatsAppCanal.ativo.is_(True))
        .order_by(WhatsAppCanal.criado_em.asc())
        .first()
    )


def instance_opera_estoque(
    db: Session, loja_id: str, instance: str | None
) -> bool:
    """True se esta instância Evolution pode responder/operar o grupo de estoque."""
    principal = obter_canal_principal_estoque(db, loja_id)
    if principal is None:
        # Sem canais cadastrados (legado/testes): qualquer instance da loja opera.
        return True
    inst = (instance or "").strip()
    if not inst:
        return False
    return (principal.evolution_instance or "").strip() == inst


def definir_principal_estoque(
    db: Session, loja_id: str, canal_id: str
) -> dict[str, Any]:
    """Marca um canal como único principal de estoque da loja."""
    canal = get_channel_for_loja(db, loja_id, canal_id)
    if not canal.ativo or canal.estado == ESTADO_INATIVO:
        raise HTTPException(status_code=409, detail="canal inativo")
    outros = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja_id)
        .all()
    )
    for item in outros:
        item.principal_estoque = item.id == canal.id
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def resolve_instance_principal_estoque(db: Session, loja_id: str) -> str | None:
    """Instance Evolution do canal principal (envio de alerta no grupo)."""
    canal = obter_canal_principal_estoque(db, loja_id)
    if canal is None:
        return None
    inst = (canal.evolution_instance or "").strip()
    return inst or None


def list_channels(db: Session, loja_id: str) -> list[dict[str, Any]]:
    """Lista canais da loja (ativos e inativos), ordenados por criação."""
    rows = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja_id)
        .order_by(WhatsAppCanal.criado_em.asc())
        .all()
    )
    return [_canal_dict(c) for c in rows]


def _sanitizar_nome(bruto: str) -> str:
    """Reduz a [a-z0-9-]: o nome vira segmento de URL na Evolution."""
    limpo = re.sub(r"[^a-z0-9-]+", "-", (bruto or "").strip().lower())
    return re.sub(r"-{2,}", "-", limpo).strip("-")


def gerar_nome_instancia(db: Session, loja: Loja) -> str:
    """Nome novo e livre: {slug}-{4 hex}. Colisão é improvável mas tratada."""
    base = _sanitizar_nome(loja.slug) or "loja"
    for _ in range(10):
        candidato = f"{base}-{uuid.uuid4().hex[:4]}"
        ja_existe = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.evolution_instance == candidato)
            .first()
        )
        if ja_existe is None:
            return candidato
    raise HTTPException(
        status_code=503,
        detail="não foi possível gerar nome de instância; tente novamente",
    )


def register_channel(
    db: Session,
    loja_id: str,
    instance: str | None,
    label: str,
) -> dict[str, Any]:
    """Registra um canal na loja. Não toca a Evolution — só persiste.

    ``instance`` ausente faz o Chatbot gerar o nome (a Loja nunca escolhe).
    Com MULTI_WHATSAPP desligado, só permite 1 canal ativo por loja.
    Instância já existente em qualquer loja → 409.
    """
    instance = (instance or "").strip()
    label = (label or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="e164_or_label é obrigatório")

    loja = db.get(Loja, loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")

    if not instance:
        instance = gerar_nome_instancia(db, loja)

    existente = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == instance)
        .first()
    )
    if existente is not None:
        if existente.loja_id != loja_id:
            raise HTTPException(
                status_code=409,
                detail="instância já vinculada a outra loja",
            )
        # Idempotente: mesma loja + mesma instância devolve o canal existente.
        return _canal_dict(existente)

    if not config.MULTI_WHATSAPP_ENABLED:
        ativos = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.loja_id == loja_id, WhatsAppCanal.ativo.is_(True))
            .count()
        )
        if ativos >= 1:
            raise HTTPException(
                status_code=409,
                detail="multi-whatsapp desabilitado: apenas 1 canal por loja",
            )

    # Primeiro canal ativo da loja vira principal de estoque por padrão.
    tornar_principal = not _loja_tem_principal_estoque(db, loja_id)
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label=label,
        evolution_instance=instance,
        ativo=True,
        estado=ESTADO_PENDENTE,
        principal_estoque=tornar_principal,
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def inactivate_channel(db: Session, loja_id: str, canal_id: str) -> dict[str, Any]:
    """Inativa o canal (não apaga histórico). loja_id deve bater."""
    canal = db.get(WhatsAppCanal, canal_id)
    if canal is None or canal.loja_id != loja_id:
        raise HTTPException(status_code=404, detail="canal não encontrado")
    if not canal.ativo and canal.estado == ESTADO_INATIVO:
        return _canal_dict(canal)
    era_principal = bool(canal.principal_estoque)
    canal.ativo = False
    canal.estado = ESTADO_INATIVO
    canal.principal_estoque = False
    db.flush()
    if era_principal:
        # Passa o bastão ao canal ativo mais antigo.
        sucessor = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.loja_id == loja_id, WhatsAppCanal.ativo.is_(True))
            .order_by(WhatsAppCanal.criado_em.asc())
            .first()
        )
        if sucessor is not None:
            sucessor.principal_estoque = True
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def get_channel_for_loja(
    db: Session, loja_id: str, canal_id: str
) -> WhatsAppCanal:
    canal = db.get(WhatsAppCanal, canal_id)
    if canal is None or canal.loja_id != loja_id:
        raise HTTPException(status_code=404, detail="canal não encontrado")
    return canal


def connect_channel(
    db: Session,
    loja_id: str,
    canal_id: str,
    provider: WhatsAppProvider | None = None,
) -> dict[str, Any]:
    """Inicia conexão/pareamento. Devolve QR efêmero (sem log)."""
    if not config.MULTI_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="multi-whatsapp desabilitado")
    canal = get_channel_for_loja(db, loja_id, canal_id)
    if not canal.ativo or canal.estado == ESTADO_INATIVO:
        raise HTTPException(status_code=409, detail="canal inativo")
    prov = provider or get_whatsapp_provider()
    # getattr porque MemoryWhatsAppProvider e o stub não têm ensure_instance
    # — e não devem ganhar.
    ensure = getattr(prov, "ensure_instance", None)
    try:
        if callable(ensure):
            ensure(canal)
        result = prov.connect(canal)
    except WhatsAppProvisionError as exc:
        # Estado persistido não muda: o canal segue pendente e o botão
        # "conectar" é o retry natural.
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    db.refresh(canal)
    out = _canal_dict(canal)
    out["estado"] = result.estado
    if result.qr_payload is not None:
        out["qr_payload"] = result.qr_payload
    if result.expires_in_seconds is not None:
        out["expires_in_seconds"] = result.expires_in_seconds
    if result.pairing_code is not None:
        out["pairing_code"] = result.pairing_code
    return out


def channel_status(
    db: Session,
    loja_id: str,
    canal_id: str,
    provider: WhatsAppProvider | None = None,
) -> dict[str, Any]:
    """Consulta estado live do canal e persiste no DB se mudou.

    O poll da UI (GET status) devolve ``estado`` da Evolution; sem gravar,
    a lista de canais (só DB) ficava em ``pendente`` após leitura do QR.
    Canal inativo não é reativado nem tem ``estado`` sobrescrito por status.
    """
    if not config.MULTI_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="multi-whatsapp desabilitado")
    canal = get_channel_for_loja(db, loja_id, canal_id)
    prov = provider or get_whatsapp_provider()
    try:
        st = prov.status(canal)
    except WhatsAppProvisionError as exc:
        # Coerente com connect: falha do provider não inventa estado.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Sincroniza DB com o live apenas para canais ativos.
    if (
        canal.ativo
        and canal.estado != ESTADO_INATIVO
        and st.estado != canal.estado
    ):
        canal.estado = st.estado
        db.commit()
        db.refresh(canal)

    out = _canal_dict(canal)
    out["estado"] = st.estado
    out["ativo"] = st.ativo
    return out


def disconnect_channel(
    db: Session,
    loja_id: str,
    canal_id: str,
    provider: WhatsAppProvider | None = None,
) -> dict[str, Any]:
    """Desconecta o canal (permanece na loja; reconectável)."""
    if not config.MULTI_WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="multi-whatsapp desabilitado")
    canal = get_channel_for_loja(db, loja_id, canal_id)
    if not canal.ativo or canal.estado == ESTADO_INATIVO:
        raise HTTPException(status_code=409, detail="canal inativo")
    prov = provider or get_whatsapp_provider()
    st = prov.disconnect(canal)
    db.commit()
    db.refresh(canal)
    out = _canal_dict(canal)
    out["estado"] = st.estado
    return out


def backfill_legacy_from_loja(db: Session, loja_id: str) -> dict[str, Any] | None:
    """Cria canal legado a partir de Loja.evolution_instance + whatsapp.

    Idempotente: se a instância já existe em canais, devolve o existente.
    Não cria se a loja não tiver evolution_instance.
    """
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")

    instance = (loja.evolution_instance or "").strip()
    if not instance:
        return None

    existente = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == instance)
        .first()
    )
    if existente is not None:
        return _canal_dict(existente)

    label = (loja.whatsapp or "").strip() or "legado"
    tornar_principal = not _loja_tem_principal_estoque(db, loja.id)
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja.id,
        e164_or_label=label,
        evolution_instance=instance,
        ativo=True,
        estado=ESTADO_CONECTADO,  # legado já em operação
        principal_estoque=tornar_principal,
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)
    return _canal_dict(canal)


def get_channel_by_instance(db: Session, instance: str) -> WhatsAppCanal | None:
    """Busca canal pela instância Evolution (qualquer loja)."""
    if not instance:
        return None
    return (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == instance)
        .first()
    )


def resolve_evolution_instance_for_loja(db: Session, loja: Loja) -> str:
    """Instância Evolution para operações de loja (ex.: listar grupos do estoque).

    Preferência: canal **principal de estoque**; senão conectado ativo; senão
    qualquer ativo; senão ``Loja.evolution_instance`` legado.
    """
    principal = obter_canal_principal_estoque(db, loja.id)
    if principal is not None and (principal.evolution_instance or "").strip():
        return principal.evolution_instance.strip()
    canais = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja.id, WhatsAppCanal.ativo.is_(True))
        .order_by(WhatsAppCanal.criado_em.desc())
        .all()
    )
    for canal in canais:
        if canal.estado == ESTADO_CONECTADO and (canal.evolution_instance or "").strip():
            return canal.evolution_instance.strip()
    for canal in canais:
        if (canal.evolution_instance or "").strip():
            return canal.evolution_instance.strip()
    return (loja.evolution_instance or "").strip()


def resolve_canal_for_instance(db: Session, instancia: str) -> WhatsAppCanal:
    """Resolve canal pela instância; backfill legado se só existir em Loja.

    Instância desconhecida → 404 (alerta operacional / n8n).
    """
    instancia = (instancia or "").strip()
    if not instancia:
        raise HTTPException(status_code=404, detail="instância não reconhecida")

    canal = get_channel_by_instance(db, instancia)
    if canal is not None:
        return canal

    loja = (
        db.query(Loja).filter(Loja.evolution_instance == instancia).first()
    )
    if loja is None:
        raise HTTPException(status_code=404, detail="instância não reconhecida")

    backfill_legacy_from_loja(db, loja.id)
    canal = get_channel_by_instance(db, instancia)
    if canal is None:
        raise HTTPException(status_code=404, detail="instância não reconhecida")
    return canal
