"""Solicitação de simulação humana: lead + pausa bot + alerta no grupo de estoque.

Endpoint canônico usado pelas tools n8n (simular1 e fallback TEMP). Idempotente por
``Idempotency-Key`` (providerMessageId) e, em seguida, por solicitação recente do
mesmo cliente (telefone/CPF) para evitar alertas duplicados no grupo.

Ordem obrigatória antes de enviar ao grupo:
1. validar data de nascimento e maioridade (>= 18);
2. confirmar CNH com sim ou não objetivo;
3. verificar se já existe solicitação recente para o mesmo cliente;
4. somente então qualificar lead, pausar bot e alertar o grupo.

O alerta do grupo inclui telefone, CPF e nascimento completos (operação da equipe);
não inventa dados ausentes. Bloqueios sempre registram ``motivo_bloqueio`` no log
e na resposta.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

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
_MENSAGEM_MENOR_IDADE = (
    "No momento, não é possível liberar financiamento para menores de 18 anos. "
    "Quando você atingir a maioridade, poderemos realizar uma nova simulação para você."
)
_MENSAGEM_CNH = (
    "confirme claramente se o cliente tem CNH. peça resposta objetiva: sim ou não. "
    "insista com educação até obter essa resposta. NÃO diga certinho nem que vai "
    "encaminhar pro setor enquanto a CNH não estiver confirmada."
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
# Janela em que um segundo pedido do mesmo cliente (telefone/CPF) reutiliza o
# atendimento em vez de reenviar alerta ao grupo.
DEDUPE_HORAS = max(1, _int_env("CHATBOT_SIMULACAO_DEDUPE_HORAS", 48))


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
    # Normaliza acentos simples e pontuação residual.
    raw = (
        raw.replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace(".", "")
        .replace("!", "")
        .replace("?", "")
        .strip()
    )
    if raw in {"s", "sim", "ss", "si", "tenho", "possuo", "true", "1", "yes", "y"}:
        return "SIM"
    if raw in {
        "n",
        "nao",
        "nn",
        "no",
        "nop",
        "false",
        "0",
        "nao tenho",
        "nao possuo",
        "sem cnh",
        "sem",
    }:
        return "NÃO"
    # Frases curtas objetivas: "tenho cnh", "possuo sim", "nao tenho cnh".
    if re.fullmatch(r"(sim|tenho|possuo)(\s+\w+){0,3}", raw):
        if re.search(r"\bnao\b", raw):
            return "NÃO"
        return "SIM"
    if re.fullmatch(r"(nao|no)(\s+\w+){0,3}", raw) or raw.startswith("nao "):
        return "NÃO"
    return "NÃO INFORMADO"


def _cnh_confirmada(valor: str | None) -> str | None:
    """SIM/NÃO se objetivo; None se ambíguo (bloqueia envio ao grupo)."""
    normalizado = _normalizar_cnh(valor)
    if normalizado in {"SIM", "NÃO"}:
        return normalizado
    return None


def _normalizar_cpf(valor: str | None) -> str | None:
    """Só dígitos; 11 posições. None se ausente/inválido (não inventa)."""
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) != 11:
        return None
    return digitos


def _cpf_fingerprint(cpf_digitos: str | None) -> str | None:
    """Huella curta do CPF para dedupe sem persistir o documento completo."""
    if not cpf_digitos or len(cpf_digitos) != 11:
        return None
    return hashlib.sha256(cpf_digitos.encode("utf-8")).hexdigest()[:16]


def _formatar_cpf(cpf_digitos: str | None) -> str:
    if not cpf_digitos or len(cpf_digitos) != 11:
        return "não informado"
    return f"{cpf_digitos[:3]}.{cpf_digitos[3:6]}.{cpf_digitos[6:9]}-{cpf_digitos[9:]}"


def _parse_nascimento(valor: str | None) -> date | None:
    """Converte YYYY-MM-DD ou DD/MM/YYYY em ``date``; None se inválido."""
    if valor is None:
        return None
    bruto = str(valor).strip()
    if not bruto:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", bruto)
    if m:
        ano, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", bruto)
        if not m:
            return None
        dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _hoje_brasil() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _calcular_idade(nasc: date, ref: date | None = None) -> int:
    """Idade civil completa (dia/mês/ano) em ``ref`` (default: hoje em America/Sao_Paulo)."""
    hoje = ref or _hoje_brasil()
    anos = hoje.year - nasc.year
    if (hoje.month, hoje.day) < (nasc.month, nasc.day):
        anos -= 1
    return anos


def _formatar_nascimento(valor: str | None) -> str:
    """Aceita YYYY-MM-DD ou DD/MM/YYYY; devolve DD/MM/YYYY ou 'não informado'."""
    parsed = _parse_nascimento(valor)
    if parsed is not None:
        return parsed.strftime("%d/%m/%Y")
    if valor is None:
        return "não informado"
    bruto = str(valor).strip()
    if not bruto:
        return "não informado"
    # Não inventa: se o formato for desconhecido, devolve o texto recebido se curto.
    if len(bruto) <= 32 and re.search(r"\d", bruto):
        return bruto
    return "não informado"


def _log_bloqueio(motivo: str, *, loja_id: str, telefone: str) -> None:
    logger.info(
        "simulação bloqueada motivo=%s loja_sufixo=%s tel_sufixo=%s",
        motivo,
        (loja_id or "")[-8:],
        (telefone or "")[-4:],
    )


def _saida_bloqueada(
    *,
    motivo: str,
    mensagem: str,
    loja_id: str,
    telefone: str,
    faltando: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _log_bloqueio(motivo, loja_id=loja_id, telefone=telefone)
    body: dict[str, Any] = {
        "ok": False,
        "simulacao_humana_solicitada": False,
        "bloqueado": True,
        "motivo_bloqueio": motivo,
        "mensagem": mensagem,
        "telefone": telefone,
    }
    if faltando:
        body["faltando"] = list(faltando)
    if extra:
        body.update(extra)
    return body


def _buscar_solicitacao_recente(
    db: Session,
    loja_id: str,
    *,
    telefone: str,
    cpf_fp: str | None,
    excluir_idempotency_key: str | None = None,
) -> NotificacaoOperacional | None:
    """Localiza pedido recente do mesmo cliente (telefone ou fingerprint de CPF)."""
    desde = _agora() - timedelta(hours=DEDUPE_HORAS)
    candidatos = (
        db.query(NotificacaoOperacional)
        .filter(
            NotificacaoOperacional.loja_id == loja_id,
            NotificacaoOperacional.tipo == TIPO_SIMULACAO_HUMANA,
            NotificacaoOperacional.created_at >= desde,
        )
        .order_by(NotificacaoOperacional.created_at.desc())
        .limit(100)
        .all()
    )
    for notif in candidatos:
        if (
            excluir_idempotency_key
            and notif.idempotency_key == excluir_idempotency_key
        ):
            continue
        try:
            dados = json.loads(notif.payload_resumo or "{}")
        except (TypeError, json.JSONDecodeError):
            dados = {}
        tel = str(dados.get("telefone") or "").strip()
        if tel and tel == telefone:
            return notif
        fp = str(dados.get("cpf_fp") or "").strip()
        if cpf_fp and fp and fp == cpf_fp:
            return notif
    return None


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

    Idempotente por ``(loja_id, idempotency_key)`` e por solicitação recente do
    mesmo cliente (telefone/CPF). Não envia ao grupo sem maioridade e CNH
    confirmada (sim/não).
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
    cpf_fp = _cpf_fingerprint(cpf_norm)

    # --- Gate 1: data de nascimento + maioridade ----------------------------
    nasc_date = _parse_nascimento(nasc_limpo)
    if nasc_date is None:
        return _saida_bloqueada(
            motivo="nascimento_invalido",
            mensagem=(
                "peça a data de nascimento completa (dia, mês e ano) em DD/MM/AAAA. "
                "NÃO diga certinho nem que vai encaminhar pro setor sem data válida."
            ),
            loja_id=loja_id,
            telefone=telefone_norm,
            faltando=["data de nascimento"],
        )
    idade = _calcular_idade(nasc_date)
    if idade < 18:
        return _saida_bloqueada(
            motivo="menor_de_idade",
            mensagem=_MENSAGEM_MENOR_IDADE,
            loja_id=loja_id,
            telefone=telefone_norm,
            extra={"idade": idade},
        )

    # --- Gate 2: CNH objetiva (sim ou não) ----------------------------------
    cnh_ok = _cnh_confirmada(tem_cnh)
    if cnh_ok is None:
        return _saida_bloqueada(
            motivo="cnh_nao_confirmada",
            mensagem=_MENSAGEM_CNH,
            loja_id=loja_id,
            telefone=telefone_norm,
            faltando=["cnh"],
        )

    entrada_val: float | None = None
    if entrada is not None:
        try:
            entrada_val = float(entrada)
            if entrada_val < 0 or entrada_val != entrada_val:
                entrada_val = None
        except (TypeError, ValueError):
            entrada_val = None

    # --- Gate 3a: idempotência por chave de mensagem ------------------------
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
            logger.info(
                "simulação reutilizada motivo=idempotency_key loja_sufixo=%s tel_sufixo=%s",
                loja_id[-8:],
                telefone_norm[-4:],
            )
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
            tem_cnh=cnh_ok,
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

    # --- Gate 3b: dedupe por cliente (telefone ou CPF recente) --------------
    recente = _buscar_solicitacao_recente(
        db,
        loja_id,
        telefone=telefone_norm,
        cpf_fp=cpf_fp,
        excluir_idempotency_key=chave,
    )
    if recente is not None:
        logger.info(
            "simulação reutilizada motivo=solicitacao_recente notif=%s "
            "loja_sufixo=%s tel_sufixo=%s",
            recente.id,
            loja_id[-8:],
            telefone_norm[-4:],
        )
        # Garante handoff no atendimento existente; não reenvia ao grupo se já sent.
        try:
            servico.definir_bot_ativo(
                db, loja_id, telefone_norm, False, instance=instance
            )
        except Exception:
            logger.exception("falha ao reafirmar bot_ativo=false em dedupe")
        if recente.status == "sent":
            return _saida(
                notificacao=recente,
                telefone=telefone_norm,
                duplicada=True,
                alerta_enviado=True,
            )
        # pending/failed: tenta reenviar o alerta já existente (sem criar outro).
        grupo = operacao.obter_grupo_estoque(db, loja_id)
        destino_jid = grupo.grupo_jid if grupo is not None else None
        if destino_jid is None:
            return _saida(
                notificacao=recente,
                telefone=telefone_norm,
                duplicada=True,
                alerta_enviado=False,
            )
        recente.destino_jid = destino_jid
        instancia = _resolver_instancia_alerta(db, loja_id, instance)
        texto = _montar_texto_grupo(
            telefone=telefone_norm,
            interesse=interesse_limpo,
            tem_cnh=cnh_ok,
            cpf=cpf_norm,
            nascimento=nasc_limpo,
            vendedor=vendedor,
            fallback_temporario=fallback_temporario,
        )
        enviado = _despachar_alerta(db, recente, instancia=instancia, texto=texto)
        return _saida(
            notificacao=recente,
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
        "tem_cnh": cnh_ok,
        "cpf_recebido": bool(cpf_recebido) or cpf_norm is not None,
        "cpf_fp": cpf_fp,
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
        tem_cnh=cnh_ok,
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
