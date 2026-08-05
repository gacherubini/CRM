"""Solicitação de simulação humana: lead + pausa bot + alerta no grupo de estoque.

Endpoint canônico usado pelas tools n8n (simular1 e fallback TEMP). Idempotente por
``Idempotency-Key`` (providerMessageId). Não persiste CPF/nascimento.
"""
from __future__ import annotations

import json
import logging
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


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _mascarar_telefone(telefone: str) -> str:
    digitos = "".join(ch for ch in telefone if ch.isdigit())
    if len(digitos) < 4:
        return "****"
    return f"***{digitos[-4:]}"


def _normalizar_cnh(valor: str | None) -> str:
    raw = (valor or "").strip().lower()
    if raw.startswith(("s", "sim", "tenho", "possuo", "true", "1")):
        return "sim"
    if raw.startswith(("n", "nao", "não", "false", "0")):
        return "não"
    return "não informado"


def _montar_texto_grupo(
    *,
    telefone: str,
    interesse: str,
    tem_cnh: str | None,
    cpf_recebido: bool,
    nascimento_recebido: bool,
    fallback_temporario: bool,
) -> str:
    final = _mascarar_telefone(telefone)
    cnh = _normalizar_cnh(tem_cnh)
    linhas = [
        "precisa de simulação humana",
    ]
    if fallback_temporario:
        linhas.append("fallback temporário: moto fora do estoque digital")
    linhas.extend(
        [
            f"cliente final {final}",
            (
                "cpf e data de nascimento recebidos"
                if cpf_recebido and nascimento_recebido
                else "dados de simulação recebidos"
            ),
            f"cnh: {cnh}",
            f"interesse: {(interesse or '—')[:80]}",
            "faça a simulação no portal e responda o cliente",
            f"portal: {config.PORTAL_BASE_URL}/app/loja/atendimento/{quote(telefone, safe='')}",
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
    cpf_recebido: bool = False,
    nascimento_recebido: bool = False,
    fallback_temporario: bool = False,
    nome: str | None = None,
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

    resumo = {
        "telefone_mascarado": _mascarar_telefone(telefone_norm),
        "interesse": interesse_limpo[:80],
        "tem_cnh": _normalizar_cnh(tem_cnh),
        "cpf_recebido": bool(cpf_recebido),
        "nascimento_recebido": bool(nascimento_recebido),
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

    instancia = (instance or "").strip()
    if not instancia:
        # Fallback: instância da loja legada.
        from app import channels
        from app.models_db import Loja

        loja = db.get(Loja, loja_id)
        if loja is not None:
            instancia = channels.resolve_evolution_instance_for_loja(db, loja)

    texto = _montar_texto_grupo(
        telefone=telefone_norm,
        interesse=interesse_limpo,
        tem_cnh=tem_cnh,
        cpf_recebido=cpf_recebido,
        nascimento_recebido=nascimento_recebido,
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
