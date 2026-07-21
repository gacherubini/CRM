"""Operação via WhatsApp (E5): números autorizados + cadastro de veículo no Estoque.

O n8n/LLM extrai campos e chama esta API. O Chatbot valida autorização e
delega a gravação ao Estoque (HTTP privado). Nunca grava veículo localmente
como fonte de verdade.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import config
from app.inventory import InventoryWriteClient
from app.models_db import NumeroAutorizado
from app.vehicle_photo import VehiclePhotoProcessor

# Alinhado ao Estoque: Mercosul ABC1D23 ou antigo ABC1234.
_PLACA_RE = re.compile(r"^[A-Z]{3}[0-9][0-9A-Z][0-9]{2}$")
_PAPEIS = frozenset({"dono", "vendedor"})
_TIPOS = frozenset({"moto", "carro"})
_PLACA_NA_LEGENDA_RE = re.compile(r"\b([A-Z]{3})[-\s]?([0-9][A-Z0-9][0-9]{2})\b", re.I)
logger = logging.getLogger("chatbot.operacao")


def normalizar_telefone(valor: str | None) -> str:
    """Mantém só dígitos (DDI/DDD/número). Vazio vira string vazia."""
    if not valor:
        return ""
    return re.sub(r"\D", "", str(valor))


def normalizar_placa(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpa = re.sub(r"[\s\-]", "", str(valor)).upper()
    return limpa or None


def validar_placa(valor: str | None) -> str:
    placa = normalizar_placa(valor)
    if not placa:
        raise HTTPException(status_code=422, detail="faltou placa")
    if not _PLACA_RE.match(placa):
        raise HTTPException(
            status_code=422,
            detail="placa inválida (use Mercosul ABC1D23 ou antigo ABC1234)",
        )
    return placa


def _para_saida_numero(n: NumeroAutorizado) -> dict:
    return {
        "id": n.id,
        "telefone": n.telefone,
        "papel": n.papel,
        "ativo": n.ativo,
        "criado_em": n.criado_em.isoformat() if n.criado_em else None,
    }


def listar_numeros(db: Session, loja_id: str) -> list[dict]:
    rows = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.loja_id == loja_id)
        .order_by(NumeroAutorizado.criado_em.desc())
        .all()
    )
    return [_para_saida_numero(r) for r in rows]


def adicionar_numero(
    db: Session,
    loja_id: str,
    telefone: str,
    papel: str = "vendedor",
    ativo: bool = True,
) -> dict:
    tel = normalizar_telefone(telefone)
    if len(tel) < 10:
        raise HTTPException(status_code=422, detail="telefone inválido")
    papel_norm = (papel or "vendedor").strip().lower()
    if papel_norm not in _PAPEIS:
        raise HTTPException(status_code=422, detail="papel inválido (dono|vendedor)")

    existente = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.loja_id == loja_id, NumeroAutorizado.telefone == tel)
        .first()
    )
    if existente:
        existente.papel = papel_norm
        existente.ativo = ativo
        if not ativo:
            existente.foto_placa_atual = None
            existente.foto_sessao_expira_em = None
        db.commit()
        db.refresh(existente)
        return _para_saida_numero(existente)

    row = NumeroAutorizado(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone=tel,
        papel=papel_norm,
        ativo=ativo,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="número já cadastrado") from exc
    db.refresh(row)
    return _para_saida_numero(row)


def remover_numero(db: Session, loja_id: str, telefone: str) -> dict:
    tel = normalizar_telefone(telefone)
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.loja_id == loja_id, NumeroAutorizado.telefone == tel)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="número não encontrado")
    db.delete(row)
    db.commit()
    return {"removido": True, "telefone": tel}


def esta_autorizado(db: Session, loja_id: str, telefone: str) -> bool:
    tel = normalizar_telefone(telefone)
    if not tel:
        return False
    row = (
        db.query(NumeroAutorizado)
        .filter(
            NumeroAutorizado.loja_id == loja_id,
            NumeroAutorizado.telefone == tel,
            NumeroAutorizado.ativo.is_(True),
        )
        .first()
    )
    return row is not None


def _numero_autorizado_ativo(
    db: Session, loja_id: str, telefone: str
) -> NumeroAutorizado | None:
    tel = normalizar_telefone(telefone)
    if not tel:
        return None
    return (
        db.query(NumeroAutorizado)
        .filter(
            NumeroAutorizado.loja_id == loja_id,
            NumeroAutorizado.telefone == tel,
            NumeroAutorizado.ativo.is_(True),
        )
        .first()
    )


def _ativar_sessao_fotos(
    db: Session, loja_id: str, telefone: str, placa: str
) -> bool:
    ttl = config.IMAGE_SESSION_TTL_SECONDS
    numero = _numero_autorizado_ativo(db, loja_id, telefone)
    if numero is None or ttl <= 0:
        return False
    numero.foto_placa_atual = validar_placa(placa)
    numero.foto_sessao_expira_em = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    db.commit()
    return True


def _placa_da_sessao_fotos(
    db: Session, loja_id: str, telefone: str
) -> str | None:
    numero = _numero_autorizado_ativo(db, loja_id, telefone)
    if numero is None or not numero.foto_placa_atual or not numero.foto_sessao_expira_em:
        return None
    expira = numero.foto_sessao_expira_em
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if expira <= datetime.now(timezone.utc):
        numero.foto_placa_atual = None
        numero.foto_sessao_expira_em = None
        db.commit()
        return None
    return validar_placa(numero.foto_placa_atual)


def _tentar_ativar_sessao_fotos(
    db: Session, loja_id: str, telefone: str, placa: str
) -> bool:
    try:
        return _ativar_sessao_fotos(db, loja_id, telefone, placa)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("sessão de fotos não persistida")
        return False


def _minutos_sessao_fotos() -> int:
    return max(1, (config.IMAGE_SESSION_TTL_SECONDS + 59) // 60)


def _exigir_autorizado(db: Session, loja_id: str, telefone: str) -> str:
    tel = normalizar_telefone(telefone)
    if not tel:
        raise HTTPException(status_code=422, detail="faltou telefone do solicitante")
    if not esta_autorizado(db, loja_id, tel):
        raise HTTPException(status_code=403, detail="não autorizado")
    return tel


def _validar_campos_veiculo(dados: dict[str, Any]) -> dict[str, Any]:
    """Validação orientada a WhatsApp — mensagens curtas e legíveis."""
    faltas: list[str] = []

    tipo = (dados.get("tipo") or "").strip().lower()
    if not tipo:
        faltas.append("tipo")
    elif tipo not in _TIPOS:
        raise HTTPException(status_code=422, detail="tipo inválido (moto|carro)")

    marca = (dados.get("marca") or "").strip()
    if not marca:
        faltas.append("marca")

    modelo = (dados.get("modelo") or "").strip()
    if not modelo:
        faltas.append("modelo")

    ano = dados.get("ano_modelo")
    if ano is None:
        faltas.append("ano")
    else:
        try:
            ano = int(ano)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="ano inválido") from exc
        if not (1900 <= ano <= 2100):
            raise HTTPException(status_code=422, detail="ano inválido")

    preco = dados.get("preco")
    if preco is None:
        faltas.append("valor")
    else:
        try:
            preco = float(preco)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="valor inválido") from exc
        if preco <= 0:
            raise HTTPException(status_code=422, detail="valor deve ser > 0")

    if faltas:
        # Uma falta → mensagem singular; várias → lista.
        if faltas == ["valor"]:
            raise HTTPException(status_code=422, detail="faltou valor")
        if len(faltas) == 1:
            raise HTTPException(status_code=422, detail=f"faltou {faltas[0]}")
        raise HTTPException(
            status_code=422, detail="faltou " + ", ".join(faltas)
        )

    placa = validar_placa(dados.get("placa"))

    km = dados.get("km", 0)
    try:
        km = int(km if km is not None else 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="km inválido") from exc
    if km < 0:
        raise HTTPException(status_code=422, detail="km não pode ser negativo")

    payload: dict[str, Any] = {
        "tipo": tipo,
        "marca": marca,
        "modelo": modelo,
        "ano_modelo": ano,
        "preco": preco,
        "km": km,
        "placa": placa,
        # Cadastro operacional pelo WhatsApp deve chegar até a vitrine.
        "publicado": True,
    }
    for opcional in ("versao", "cor", "codigo_interno", "foto_url"):
        val = dados.get(opcional)
        if val is not None and str(val).strip():
            payload[opcional] = str(val).strip()
    return payload


def _resumo_veiculo(v: dict) -> str:
    marca = v.get("marca") or ""
    modelo = v.get("modelo") or ""
    ano = v.get("ano_modelo") or ""
    preco = v.get("preco")
    placa = v.get("placa") or ""
    try:
        preco_fmt = f"R$ {float(preco):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        preco_fmt = str(preco)
    return f"{marca} {modelo} {ano} — {preco_fmt} — placa {placa}".strip()


def criar_veiculo_autorizado(
    db: Session,
    loja_id: str,
    telefone_solicitante: str,
    dados_veiculo: dict[str, Any],
    write_client: InventoryWriteClient,
    idempotency_key: str | None = None,
) -> dict:
    """Autoriza o telefone, valida campos e cria no Estoque via HTTP."""
    tel = _exigir_autorizado(db, loja_id, telefone_solicitante)
    payload = _validar_campos_veiculo(dados_veiculo)

    # Idempotency-Key: se o caller não mandar, deriva de loja+placa+campos estáveis
    # para reenvios do mesmo cadastro no WhatsApp não duplicarem quando o Estoque suportar.
    key = idempotency_key or f"wa-veiculo:{loja_id}:{payload['placa']}:{payload['marca']}:{payload['modelo']}:{payload['ano_modelo']}"

    criado = write_client.criar_veiculo(payload, idempotency_key=key)
    sessao_ativa = _tentar_ativar_sessao_fotos(
        db, loja_id, tel, payload["placa"]
    )
    resumo = _resumo_veiculo(criado)
    mensagem = f"Veículo cadastrado e publicado no catálogo: {resumo}"
    if sessao_ativa:
        mensagem += (
            " Agora envie as fotos; pelas próximas "
            f"{_minutos_sessao_fotos()} min não precisa repetir a placa."
        )
    return {
        "ok": True,
        "mensagem": mensagem,
        "veiculo": {
            "id": criado.get("id"),
            "tipo": criado.get("tipo"),
            "marca": criado.get("marca"),
            "modelo": criado.get("modelo"),
            "ano_modelo": criado.get("ano_modelo"),
            "preco": criado.get("preco"),
            "km": criado.get("km"),
            "placa": criado.get("placa"),
            "status": criado.get("status"),
            "publicado": criado.get("publicado"),
            "foto_url": criado.get("foto_url"),
        },
        "solicitante": tel,
    }


def anexar_foto_whatsapp(
    db: Session,
    loja_id: str,
    instancia: str,
    telefone_solicitante: str,
    provider_message_id: str,
    legenda: str | None,
    mime_type: str | None,
    processor: VehiclePhotoProcessor,
) -> dict:
    """Autoriza cedo e vincula imagem pela placa explícita ou sessão curta."""
    if _numero_autorizado_ativo(db, loja_id, telefone_solicitante) is None:
        return {
            "ok": False,
            "mensagem": "Somente números autorizados da equipe podem adicionar fotos ao estoque.",
        }
    encontrada = _PLACA_NA_LEGENDA_RE.search(str(legenda or "").upper())
    placa_explicita = bool(encontrada)
    placa = (
        validar_placa("".join(encontrada.groups()))
        if encontrada
        else _placa_da_sessao_fotos(db, loja_id, telefone_solicitante)
    )
    if not placa:
        return {
            "ok": False,
            "mensagem": "Envie a primeira foto com a placa na legenda, por exemplo: ABC1D23. As próximas podem ser enviadas sem repetir a placa.",
        }
    resultado = processor.processar(
        instancia,
        provider_message_id,
        placa,
        mime_type,
    )
    if resultado.get("ok"):
        sessao_ativa = _tentar_ativar_sessao_fotos(
            db, loja_id, telefone_solicitante, placa
        )
        if placa_explicita and sessao_ativa:
            resultado["mensagem"] = str(
                resultado.get("mensagem") or "Foto adicionada ao estoque e ao catálogo."
            ) + (
                " As próximas fotos podem ser enviadas sem repetir a placa por "
                f"{_minutos_sessao_fotos()} min."
            )
    return resultado
