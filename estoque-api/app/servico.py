"""Regras do Estoque: validação, CRUD escopado por loja e transições de estado."""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import config
from app.auth import hash_token
from app.models_db import CredencialServico, Loja, Veiculo


def criar_loja(
    db: Session, nome: str, slug: str, whatsapp: str | None = None, papel: str = "dono"
) -> tuple[Loja, str]:
    """Cria a loja + uma credencial de serviço. Retorna (loja, token em claro)."""
    if db.query(Loja).filter(Loja.slug == slug).first():
        raise HTTPException(status_code=409, detail="slug já existe")
    loja = Loja(id=str(uuid.uuid4()), nome=nome, slug=slug, whatsapp=whatsapp)
    db.add(loja)
    db.flush()
    token = secrets.token_urlsafe(24)
    db.add(CredencialServico(token_hash=hash_token(token), loja_id=loja.id, papel=papel))
    db.commit()
    db.refresh(loja)
    return loja, token


def _validar(dados: dict) -> None:
    if dados.get("tipo") not in config.TIPOS:
        raise HTTPException(status_code=422, detail="tipo inválido (moto|carro)")
    preco = dados.get("preco")
    if preco is None or float(preco) <= 0:
        raise HTTPException(status_code=422, detail="preço deve ser > 0")
    ano = dados.get("ano_modelo")
    if ano is None or not (1900 <= int(ano) <= 2100):
        raise HTTPException(status_code=422, detail="ano_modelo fora do intervalo")
    if dados.get("km") is not None and int(dados["km"]) < 0:
        raise HTTPException(status_code=422, detail="km não pode ser negativo")
    if dados.get("custo") is not None and float(dados["custo"]) < 0:
        raise HTTPException(status_code=422, detail="custo não pode ser negativo")


def criar_veiculo(db: Session, loja_id: str, dados: dict) -> Veiculo:
    _validar(dados)
    v = Veiculo(id=str(uuid.uuid4()), loja_id=loja_id, **dados)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def listar_veiculos(
    db: Session,
    loja_id: str,
    tipo: str | None = None,
    status: str | None = None,
    publicado: bool | None = None,
    busca: str | None = None,
) -> list[Veiculo]:
    q = db.query(Veiculo).filter(Veiculo.loja_id == loja_id)
    if tipo:
        q = q.filter(Veiculo.tipo == tipo)
    if status:
        q = q.filter(Veiculo.status == status)
    if publicado is not None:
        q = q.filter(Veiculo.publicado == publicado)
    if busca:
        termo = f"%{busca}%"
        q = q.filter((Veiculo.modelo.ilike(termo)) | (Veiculo.marca.ilike(termo)))
    return q.order_by(Veiculo.criado_em.desc()).all()


def obter_veiculo(db: Session, loja_id: str, veiculo_id: str) -> Veiculo:
    """404 se não existir OU pertencer a outra loja (não vaza existência)."""
    v = (
        db.query(Veiculo)
        .filter(Veiculo.id == veiculo_id, Veiculo.loja_id == loja_id)
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="veículo não encontrado")
    return v


def atualizar_veiculo(db: Session, loja_id: str, veiculo_id: str, dados: dict) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    campos = {k: val for k, val in dados.items() if val is not None}
    # Revalida somente os campos afetados, reaproveitando os valores atuais.
    _validar(
        {
            "tipo": campos.get("tipo", v.tipo),
            "preco": campos.get("preco", v.preco),
            "ano_modelo": campos.get("ano_modelo", v.ano_modelo),
            "km": campos.get("km", v.km),
            "custo": campos.get("custo", v.custo),
        }
    )
    for k, val in campos.items():
        setattr(v, k, val)
    v.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


def definir_publicado(db: Session, loja_id: str, veiculo_id: str, publicado: bool) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    if publicado and v.status != "disponivel":
        raise HTTPException(status_code=409, detail="só veículo disponível pode ser publicado")
    v.publicado = publicado
    v.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


def reservar(db: Session, loja_id: str, veiculo_id: str) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    if v.status != "disponivel":
        raise HTTPException(status_code=409, detail="só veículo disponível pode ser reservado")
    v.status = "reservado"
    v.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


def vender(db: Session, loja_id: str, veiculo_id: str) -> Veiculo:
    v = obter_veiculo(db, loja_id, veiculo_id)
    if v.status not in ("disponivel", "reservado"):
        raise HTTPException(status_code=409, detail="veículo não pode ser vendido neste estado")
    v.status = "vendido"
    v.publicado = False
    v.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


# --- API pública (read-only, por slug) ---------------------------------------


def obter_loja_por_slug(db: Session, slug: str) -> Loja:
    loja = db.query(Loja).filter(Loja.slug == slug).first()
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    return loja


def listar_veiculos_publicos(
    db: Session,
    slug: str,
    tipo: str | None = None,
    preco_min: float | None = None,
    preco_max: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Loja, list[Veiculo]]:
    loja = obter_loja_por_slug(db, slug)
    q = db.query(Veiculo).filter(
        Veiculo.loja_id == loja.id,
        Veiculo.status == "disponivel",
        Veiculo.publicado.is_(True),
    )
    if tipo:
        q = q.filter(Veiculo.tipo == tipo)
    if preco_min is not None:
        q = q.filter(Veiculo.preco >= preco_min)
    if preco_max is not None:
        q = q.filter(Veiculo.preco <= preco_max)
    veiculos = q.order_by(Veiculo.criado_em.desc()).offset(offset).limit(min(limit, 100)).all()
    return loja, veiculos


def obter_veiculo_publico(db: Session, slug: str, veiculo_id: str) -> Veiculo:
    loja = obter_loja_por_slug(db, slug)
    v = (
        db.query(Veiculo)
        .filter(
            Veiculo.id == veiculo_id,
            Veiculo.loja_id == loja.id,
            Veiculo.status == "disponivel",
            Veiculo.publicado.is_(True),
        )
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="veículo não encontrado")
    return v


def para_saida_publica(v: Veiculo) -> dict:
    """Saída da API pública — NUNCA inclui custo, código interno ou dados internos."""
    return {
        "id": v.id,
        "tipo": v.tipo,
        "marca": v.marca,
        "modelo": v.modelo,
        "versao": v.versao,
        "ano_modelo": v.ano_modelo,
        "cor": v.cor,
        "km": v.km,
        "preco": float(v.preco),
        "foto_url": v.foto_url,
    }


def para_saida_privada(v: Veiculo) -> dict:
    """Saída da API privada — inclui custo/código interno."""
    return {
        "id": v.id,
        "loja_id": v.loja_id,
        "tipo": v.tipo,
        "marca": v.marca,
        "modelo": v.modelo,
        "versao": v.versao,
        "ano_modelo": v.ano_modelo,
        "cor": v.cor,
        "km": v.km,
        "preco": float(v.preco),
        "custo": float(v.custo) if v.custo is not None else None,
        "status": v.status,
        "publicado": v.publicado,
        "codigo_interno": v.codigo_interno,
        "foto_url": v.foto_url,
        "criado_em": v.criado_em.isoformat() if v.criado_em else None,
        "atualizado_em": v.atualizado_em.isoformat() if v.atualizado_em else None,
    }
