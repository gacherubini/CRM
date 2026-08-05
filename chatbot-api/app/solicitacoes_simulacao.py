"""Solicitação de simulação humana: lead + pausa bot + alerta no grupo de estoque.

Endpoint canônico usado pelas tools n8n (simular1 e fallback TEMP). Idempotente por
``Idempotency-Key`` (providerMessageId).

O alerta do grupo inclui telefone, CPF e nascimento completos (operação da equipe);
não inventa dados ausentes.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, operacao, provisioning, servico
from app.hardening import normalizar_telefone_webhook
from app.models_db import NotificacaoOperacional
from app.whatsapp_outbound import WhatsAppOutboundError, get_whatsapp_outbound

logger = logging.getLogger("chatbot.solicitacoes_simulacao")

TIPO_SIMULACAO_HUMANA = "simulacao_humana"
_MENSAGEM_CLIENTE = "certinho. vou preparar a simulação pra você."
_VENDEDOR_NAO_IDENTIFICADO = "não identificado"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _normalizar_cnh(valor: str | None) -> str:
    """Retorna SIM, NÃO ou NÃO INFORMADO (maiúsculas, como no modelo do grupo)."""
    raw = (valor or "").strip().lower()
    if raw.startswith(("s", "sim", "tenho", "possuo", "true", "1")):
        return "SIM"
    if raw.startswith(("n", "nao", "não", "false", "0")):
        return "NÃO"
    return "NÃO INFORMADO"


def _normalizar_cpf(valor: str | None) -> str | None:
    """Só dígitos; 11 posições. None se ausente/inválido (não inventa)."""
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) != 11:
        return None
    return digitos


def _formatar_cpf(cpf_digitos: str | None) -> str:
    if not cpf_digitos or len(cpf_digitos) != 11:
        return "não informado"
    return f"{cpf_digitos[:3]}.{cpf_digitos[3:6]}.{cpf_digitos[6:9]}-{cpf_digitos[9:]}"


def _formatar_nascimento(valor: str | None) -> str:
    """Aceita YYYY-MM-DD ou DD/MM/YYYY; devolve DD/MM/YYYY ou 'não informado'."""
    if valor is None:
        return "não informado"
    bruto = str(valor).strip()
    if not bruto:
        return "não informado"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", bruto)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", bruto)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    # Não inventa: se o formato for desconhecido, devolve o texto recebido se curto.
    if len(bruto) <= 32 and re.search(r"\d", bruto):
        return bruto
    return "não informado"


def _rotulo_vendedor(db: Session, loja_id: str, instance: str | None) -> str:
    """Canal/WhatsApp de origem do lead (de qual vendedor veio a conversa)."""
    from app import channels

    inst = (instance or "").strip()
    if not inst:
        return _VENDEDOR_NAO_IDENTIFICADO
    canal = channels.get_channel_by_instance(db, inst)
    if canal is not None and canal.loja_id == loja_id:
        label = (canal.e164_or_label or "").strip()
        if label:
            return label
        ev = (canal.evolution_instance or "").strip()
        if ev:
            return ev
    # Instance conhecida mas sem label amigável: ainda identifica a origem.
    return inst


def _montar_texto_grupo(
    *,
    telefone: str,
    interesse: str,
    tem_cnh: str | None,
    cpf: str | None,
    nascimento: str | None,
    vendedor: str,
    fallback_temporario: bool = False,
) -> str:
    digitos = "".join(ch for ch in telefone if ch.isdigit()) or telefone
    cnh = _normalizar_cnh(tem_cnh)
    cpf_fmt = _formatar_cpf(_normalizar_cpf(cpf))
    nasc_fmt = _formatar_nascimento(nascimento)
    vend = (vendedor or "").strip() or _VENDEDOR_NAO_IDENTIFICADO
    portal = (
        f"{config.PORTAL_BASE_URL}/app/loja/atendimento/{quote(telefone, safe='')}"
    )
    linhas = [
        "🚨 PRECISA DE SIMULAÇÃO HUMANA",
        "",
    ]
    if fallback_temporario:
        linhas.append("Fallback temporário: moto fora do estoque digital")
        linhas.append("")
    linhas.extend(
        [
            f"Cliente final: {digitos}",
            f"CPF: {cpf_fmt}",
            f"Data de nascimento: {nasc_fmt}",
            f"CNH: {cnh}",
            f"Vendedor de origem: {vend[:80]}",
            f"Interesse: {(interesse or '—')[:120]}",
            "",
            "Faça a simulação no portal e responda ao cliente:",
            portal,
        ]
    )
    return "\n".join(linhas)


def _saida(
    *,
    notificacao: NotificacaoOperacional,
    telefone: str,
    duplicada: bool,
    alerta_enviado: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "simulacao_humana_solicitada": True,
        "duplicada": duplicada,
        "notificacao_id": notificacao.id,
        "status_alerta": notificacao.status,
        "alerta_enviado": alerta_enviado,
        "bot_pausado": True,
        "telefone": telefone,
        "mensagem": _MENSAGEM_CLIENTE,
        "last_error_code": notificacao.last_error_code,
    }


def solicitar_simulacao_humana(
    db: Session,
    loja_id: str,
    *,
    telefone: str,
    interesse: str | None = None,
    tem_cnh: str | None = None,
    instance: str | None = None,
    cpf: str | None = None,
    nascimento: str | None = None,
    cpf_recebido: bool = False,
    nascimento_recebido: bool = False,
    fallback_temporario: bool = False,
    nome: str | None = None,
    entrada: float | int | None = None,
    idempotency_key: str,
) -> dict[str, Any]:
    """Aceita pedido humano: qualifica lead, pausa bot e alerta o grupo de estoque.

    Idempotente por ``(loja_id, idempotency_key)``. Segunda chamada não reenvia.
    """
    if not provisioning.is_store_operational(db, loja_id):
        raise HTTPException(
            status_code=423,
            detail={
                "code": "store_not_operational",
                "message": "loja não operacional",
                "loja_operacional": False,
            },
        )

    chave = (idempotency_key or "").strip()
    if not chave or len(chave) > 255:
        raise HTTPException(status_code=422, detail="Idempotency-Key obrigatória")

    try:
        telefone_norm = normalizar_telefone_webhook(telefone)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="telefone inválido") from exc

    interesse_limpo = (interesse or "").strip()[:160] or "simulação de financiamento"
    vendedor = _rotulo_vendedor(db, loja_id, instance)
    cpf_norm = _normalizar_cpf(cpf)
    if cpf_norm is None and cpf_recebido and cpf:
        # Valor veio mas inválido: não inventa; mensagem dirá "não informado".
        cpf_norm = None
    # cpf_recebido sem valor: também "não informado" no texto.
    if cpf_norm is not None:
        cpf_recebido = True
    nasc_limpo = (nascimento or "").strip() or None
    if nasc_limpo:
        nascimento_recebido = True

    entrada_val: float | None = None
    if entrada is not None:
        try:
            entrada_val = float(entrada)
            if entrada_val < 0 or entrada_val != entrada_val:
                entrada_val = None
        except (TypeError, ValueError):
            entrada_val = None

    existente = (
        db.query(NotificacaoOperacional)
        .filter(
            NotificacaoOperacional.loja_id == loja_id,
            NotificacaoOperacional.idempotency_key == chave,
        )
        .first()
    )
    if existente is not None:
        return _saida(
            notificacao=existente,
            telefone=telefone_norm,
            duplicada=True,
            alerta_enviado=existente.status == "sent",
        )

    # Lead + pausa + notificação pending (efeitos duráveis antes do envio).
    lead = servico.registrar_lead(
        db,
        loja_id,
        telefone_norm,
        nome=nome,
        interesse=interesse_limpo,
        etapa="qualificado",
    )
    del lead  # lead persistido; não expomos no retorno

    servico.definir_bot_ativo(
        db, loja_id, telefone_norm, False, instance=instance
    )
    canal_id = None
    try:
        # Reaproveita resolução de canal do estado/conversa quando possível.
        from app.servico import _resolver_canal_id_escopo

        canal_id = _resolver_canal_id_escopo(db, loja_id, instance=instance)
    except Exception:
        canal_id = None

    grupo = operacao.obter_grupo_estoque(db, loja_id)
    destino_jid = grupo.grupo_jid if grupo is not None else None

    # Resumo operacional: não grava CPF completo no JSON de auditoria.
    resumo = {
        "telefone": telefone_norm,
        "vendedor": vendedor[:80],
        "entrada": entrada_val,
        "interesse": interesse_limpo[:80],
        "tem_cnh": _normalizar_cnh(tem_cnh),
        "cpf_recebido": bool(cpf_recebido) or cpf_norm is not None,
        "nascimento_recebido": bool(nascimento_recebido) or bool(nasc_limpo),
        "nascimento": _formatar_nascimento(nasc_limpo) if nasc_limpo else None,
        "fallback_temporario": bool(fallback_temporario),
    }

    notificacao = NotificacaoOperacional(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        canal_id=canal_id,
        tipo=TIPO_SIMULACAO_HUMANA,
        idempotency_key=chave,
        destino_jid=destino_jid,
        status="pending",
        attempts=0,
        provider_message_id=chave,
        payload_resumo=json.dumps(resumo, ensure_ascii=False),
        created_at=_agora(),
    )
    db.add(notificacao)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Corrida: outra execução inseriu a mesma chave.
        existente = (
            db.query(NotificacaoOperacional)
            .filter(
                NotificacaoOperacional.loja_id == loja_id,
                NotificacaoOperacional.idempotency_key == chave,
            )
            .first()
        )
        if existente is None:
            raise
        return _saida(
            notificacao=existente,
            telefone=telefone_norm,
            duplicada=True,
            alerta_enviado=existente.status == "sent",
        )
    db.refresh(notificacao)

    if destino_jid is None:
        notificacao.status = "failed"
        notificacao.last_error_code = "grupo_estoque_nao_configurado"
        notificacao.attempts = 1
        db.commit()
        logger.info(
            "alerta simulação sem grupo loja_sufixo=%s notif=%s",
            loja_id[-8:],
            notificacao.id,
        )
        # Aceite durável (lead + handoff) mesmo sem grupo; cliente pode ser confirmado.
        # status_alerta=failed permite observabilidade.
        return _saida(
            notificacao=notificacao,
            telefone=telefone_norm,
            duplicada=False,
            alerta_enviado=False,
        )

    # Sempre prefere o canal principal de estoque (um número manda no grupo).
    from app import channels
    from app.models_db import Loja

    instancia = channels.resolve_instance_principal_estoque(db, loja_id) or ""
    if not instancia:
        instancia = (instance or "").strip()
    if not instancia:
        loja = db.get(Loja, loja_id)
        if loja is not None:
            instancia = channels.resolve_evolution_instance_for_loja(db, loja)

    texto = _montar_texto_grupo(
        telefone=telefone_norm,
        interesse=interesse_limpo,
        tem_cnh=tem_cnh,
        cpf=cpf_norm,
        nascimento=nasc_limpo,
        vendedor=vendedor,
        fallback_temporario=fallback_temporario,
    )

    notificacao.attempts = 1
    try:
        get_whatsapp_outbound().send_text(
            instance=instancia,
            number=destino_jid,
            text=texto,
        )
        notificacao.status = "sent"
        notificacao.sent_at = _agora()
        notificacao.last_error_code = None
        db.commit()
        logger.info(
            "alerta simulação enviado notif=%s loja_sufixo=%s",
            notificacao.id,
            loja_id[-8:],
        )
        return _saida(
            notificacao=notificacao,
            telefone=telefone_norm,
            duplicada=False,
            alerta_enviado=True,
        )
    except WhatsAppOutboundError as exc:
        code = getattr(exc, "code", None) or "evolution_send_failed"
        notificacao.status = "failed"
        notificacao.last_error_code = code
        db.commit()
        logger.warning(
            "alerta simulação falhou notif=%s code=%s",
            notificacao.id,
            code,
        )
        # Lead e handoff já aceitos; 202 com ok e alerta_enviado=false.
        return _saida(
            notificacao=notificacao,
            telefone=telefone_norm,
            duplicada=False,
            alerta_enviado=False,
        )
