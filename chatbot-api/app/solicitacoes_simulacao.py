"""Solicitação de simulação humana: lead + pausa bot + alerta no grupo de estoque.

Endpoint canônico usado pelas tools n8n (simular1 e fallback TEMP). Idempotente por
``Idempotency-Key`` (providerMessageId).

O alerta do grupo inclui telefone, CPF e nascimento completos (operação da equipe);
não inventa dados ausentes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, operacao, provisioning, servico
from app.hardening import normalizar_telefone_webhook
from app.models_db import NotificacaoOperacional
from app.whatsapp_outbound import WhatsAppOutboundError, get_whatsapp_outbound

logger = logging.getLogger("chatbot.solicitacoes_simulacao")

TIPO_SIMULACAO_HUMANA = "simulacao_humana"
_MENSAGEM_CLIENTE = (
    "certo, já tenho seus dados. vou encaminhar pro setor de simulação e te retorno "
    "por aqui. atendemos das 8h30 às 18h; fora desse horário, respondo no próximo dia útil."
)
_VENDEDOR_NAO_IDENTIFICADO = "não identificado"


def _int_env(nome: str, default: int) -> int:
    try:
        return int(os.getenv(nome, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _float_env(nome: str, default: float) -> float:
    try:
        return float(os.getenv(nome, str(default)) or default)
    except (TypeError, ValueError):
        return default


# Reenvio do alerta: cada envio conta uma tentativa; o drenador reprocessa
# pending/failed com backoff exponencial até MAX_TENTATIVAS_ALERTA.
MAX_TENTATIVAS_ALERTA = _int_env("CHATBOT_NOTIF_MAX_ATTEMPTS", 6)
_BACKOFF_BASE_SECONDS = _float_env("CHATBOT_NOTIF_BACKOFF_BASE_SECONDS", 30)
_BACKOFF_MAX_SECONDS = _float_env("CHATBOT_NOTIF_BACKOFF_MAX_SECONDS", 1800)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _proximo_attempt_at(attempts: int) -> datetime:
    """Backoff exponencial a partir da tentativa já contabilizada."""
    atraso = min(
        _BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)), _BACKOFF_MAX_SECONDS
    )
    return _agora() + timedelta(seconds=atraso)


def _resolver_instancia_alerta(
    db: Session, loja_id: str, instance: str | None
) -> str:
    """Número que fala no grupo: canal principal de estoque, senão o da conversa."""
    from app import channels
    from app.models_db import Loja

    instancia = channels.resolve_instance_principal_estoque(db, loja_id) or ""
    if not instancia:
        instancia = (instance or "").strip()
    if not instancia:
        loja = db.get(Loja, loja_id)
        if loja is not None:
            instancia = channels.resolve_evolution_instance_for_loja(db, loja)
    return instancia


def _despachar_alerta(
    db: Session, notificacao: NotificacaoOperacional, *, instancia: str, texto: str
) -> bool:
    """Envia (ou reenvia) o alerta ao grupo e persiste o resultado. True se enviou.

    Em falha, agenda ``next_attempt_at`` para o drenador reprocessar, até esgotar
    ``MAX_TENTATIVAS_ALERTA`` (quando para de reagendar e fica ``failed`` visível).
    """
    notificacao.attempts = (notificacao.attempts or 0) + 1
    try:
        get_whatsapp_outbound().send_text(
            instance=instancia,
            number=notificacao.destino_jid,
            text=texto,
        )
    except WhatsAppOutboundError as exc:
        code = getattr(exc, "code", None) or "evolution_send_failed"
        notificacao.status = "failed"
        notificacao.last_error_code = code
        notificacao.next_attempt_at = (
            None
            if notificacao.attempts >= MAX_TENTATIVAS_ALERTA
            else _proximo_attempt_at(notificacao.attempts)
        )
        db.commit()
        logger.warning(
            "alerta simulação falhou notif=%s code=%s tentativa=%s",
            notificacao.id,
            code,
            notificacao.attempts,
        )
        return False
    notificacao.status = "sent"
    notificacao.sent_at = _agora()
    notificacao.last_error_code = None
    notificacao.next_attempt_at = None
    db.commit()
    logger.info(
        "alerta simulação enviado notif=%s loja_sufixo=%s tentativa=%s",
        notificacao.id,
        notificacao.loja_id[-8:],
        notificacao.attempts,
    )
    return True


def _texto_do_resumo(notif: NotificacaoOperacional) -> str:
    """Reconstrói o texto do alerta a partir do resumo persistido.

    O CPF completo não é persistido (privacidade), então o reenvio pelo drenador
    o omite ("não informado"); a equipe age pelo link do portal. O caminho normal
    e o reenvio por rechamada (mesma Idempotency-Key) mantêm o CPF, pois recebem
    os dados frescos da requisição.
    """
    dados = json.loads(notif.payload_resumo or "{}")
    cnh_render = {"SIM": "sim", "NÃO": "nao"}.get(dados.get("tem_cnh"))
    return _montar_texto_grupo(
        telefone=dados.get("telefone") or "",
        interesse=dados.get("interesse") or "",
        tem_cnh=cnh_render,
        cpf=None,
        nascimento=dados.get("nascimento"),
        vendedor=dados.get("vendedor") or "",
        fallback_temporario=bool(dados.get("fallback_temporario")),
    )


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
        if existente.status == "sent":
            return _saida(
                notificacao=existente,
                telefone=telefone_norm,
                duplicada=True,
                alerta_enviado=True,
            )
        # Tentativa anterior não concluiu (pending/failed): reprocessa com os
        # dados desta chamada, que ainda trazem o CPF completo (não persistido).
        grupo = operacao.obter_grupo_estoque(db, loja_id)
        destino_jid = grupo.grupo_jid if grupo is not None else None
        if destino_jid is None:
            return _saida(
                notificacao=existente,
                telefone=telefone_norm,
                duplicada=True,
                alerta_enviado=False,
            )
        existente.destino_jid = destino_jid
        instancia = _resolver_instancia_alerta(db, loja_id, instance)
        texto = _montar_texto_grupo(
            telefone=telefone_norm,
            interesse=interesse_limpo,
            tem_cnh=tem_cnh,
            cpf=cpf_norm,
            nascimento=nasc_limpo,
            vendedor=vendedor,
            fallback_temporario=fallback_temporario,
        )
        enviado = _despachar_alerta(
            db, existente, instancia=instancia, texto=texto
        )
        return _saida(
            notificacao=existente,
            telefone=telefone_norm,
            duplicada=True,
            alerta_enviado=enviado,
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

    # Minimiza retenção: CPF e moto só existiam para a tool / simulação.
    try:
        servico.limpar_cpf_cliente_conversa(db, loja_id, telefone_norm)
    except Exception:
        logger.exception("falha ao limpar cpf_cliente pos-simulacao")
    try:
        servico.limpar_moto_escolhida_conversa(db, loja_id, telefone_norm)
    except Exception:
        logger.exception("falha ao limpar moto_escolhida pos-simulacao")

    if destino_jid is None:
        notificacao.status = "failed"
        notificacao.last_error_code = "grupo_estoque_nao_configurado"
        notificacao.attempts = 1
        # Reagenda: o drenador reconsulta o grupo e reenvia quando for configurado.
        notificacao.next_attempt_at = _proximo_attempt_at(1)
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

    instancia = _resolver_instancia_alerta(db, loja_id, instance)
    texto = _montar_texto_grupo(
        telefone=telefone_norm,
        interesse=interesse_limpo,
        tem_cnh=tem_cnh,
        cpf=cpf_norm,
        nascimento=nasc_limpo,
        vendedor=vendedor,
        fallback_temporario=fallback_temporario,
    )

    enviado = _despachar_alerta(db, notificacao, instancia=instancia, texto=texto)
    # Lead e handoff já aceitos; falha vira 202 com alerta_enviado=false e retry.
    return _saida(
        notificacao=notificacao,
        telefone=telefone_norm,
        duplicada=False,
        alerta_enviado=enviado,
    )


def processar_pendentes(
    db_factory: Callable[[], Session], *, limite: int = 50
) -> dict[str, int]:
    """Drena alertas pending/failed cujo ``next_attempt_at`` já venceu e reenvia.

    Rede de segurança para falhas transitórias da Evolution: sem isto, um único
    envio malsucedido perde o alerta para sempre. Roda no worker de background.
    """
    db = db_factory()
    resultado = {"encontrados": 0, "enviados": 0, "falharam": 0}
    try:
        agora = _agora()
        pendentes = (
            db.query(NotificacaoOperacional)
            .filter(
                NotificacaoOperacional.tipo == TIPO_SIMULACAO_HUMANA,
                NotificacaoOperacional.status.in_(("pending", "failed")),
                NotificacaoOperacional.attempts < MAX_TENTATIVAS_ALERTA,
                or_(
                    NotificacaoOperacional.next_attempt_at.is_(None),
                    NotificacaoOperacional.next_attempt_at <= agora,
                ),
            )
            .order_by(NotificacaoOperacional.created_at.asc())
            .limit(limite)
            .all()
        )
        resultado["encontrados"] = len(pendentes)
        for notif in pendentes:
            destino_jid = notif.destino_jid
            if not destino_jid:
                grupo = operacao.obter_grupo_estoque(db, notif.loja_id)
                destino_jid = grupo.grupo_jid if grupo is not None else None
                if not destino_jid:
                    notif.attempts = (notif.attempts or 0) + 1
                    notif.last_error_code = "grupo_estoque_nao_configurado"
                    notif.next_attempt_at = (
                        None
                        if notif.attempts >= MAX_TENTATIVAS_ALERTA
                        else _proximo_attempt_at(notif.attempts)
                    )
                    db.commit()
                    resultado["falharam"] += 1
                    continue
                notif.destino_jid = destino_jid
            texto = _texto_do_resumo(notif)
            instancia = _resolver_instancia_alerta(db, notif.loja_id, None)
            enviado = _despachar_alerta(
                db, notif, instancia=instancia, texto=texto
            )
            resultado["enviados" if enviado else "falharam"] += 1
        return resultado
    finally:
        db.close()
