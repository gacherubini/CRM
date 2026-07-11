"""API privada do Estoque (Plano #4A, `/v1`). API pública `/public/v1` vem depois."""
import os
from typing import Optional

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config, models_db, servico  # noqa: F401 (registra os modelos)
from app.auth import Contexto, get_contexto
from app.db import Base, engine, get_db

app = FastAPI(title="Estoque API")

if os.getenv("ESTOQUE_SKIP_INIT") != "1":
    Base.metadata.create_all(bind=engine)


class VeiculoInput(BaseModel):
    tipo: str
    marca: str
    modelo: str
    ano_modelo: int
    preco: float
    versao: Optional[str] = None
    cor: Optional[str] = None
    km: int = 0
    custo: Optional[float] = None
    codigo_interno: Optional[str] = None
    foto_url: Optional[str] = None


class VeiculoUpdate(BaseModel):
    tipo: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    ano_modelo: Optional[int] = None
    preco: Optional[float] = None
    versao: Optional[str] = None
    cor: Optional[str] = None
    km: Optional[int] = None
    custo: Optional[float] = None
    codigo_interno: Optional[str] = None
    foto_url: Optional[str] = None


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"versao": config.VERSAO, "schema": config.SCHEMA_VERSAO}


@app.post("/v1/veiculos", status_code=201)
def criar_veiculo(
    dados: VeiculoInput, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    v = servico.criar_veiculo(db, ctx.loja_id, dados.model_dump(exclude_none=True))
    return servico.para_saida_privada(v)


@app.get("/v1/veiculos")
def listar_veiculos(
    tipo: Optional[str] = None,
    status: Optional[str] = None,
    publicado: Optional[bool] = None,
    busca: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    veiculos = servico.listar_veiculos(db, ctx.loja_id, tipo, status, publicado, busca)
    return {"veiculos": [servico.para_saida_privada(v) for v in veiculos]}


@app.get("/v1/veiculos/{veiculo_id}")
def obter_veiculo(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_privada(servico.obter_veiculo(db, ctx.loja_id, veiculo_id))


@app.patch("/v1/veiculos/{veiculo_id}")
def atualizar_veiculo(
    veiculo_id: str,
    dados: VeiculoUpdate,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    v = servico.atualizar_veiculo(db, ctx.loja_id, veiculo_id, dados.model_dump(exclude_none=True))
    return servico.para_saida_privada(v)


@app.post("/v1/veiculos/{veiculo_id}/publicar")
def publicar(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_privada(servico.definir_publicado(db, ctx.loja_id, veiculo_id, True))


@app.post("/v1/veiculos/{veiculo_id}/despublicar")
def despublicar(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_privada(servico.definir_publicado(db, ctx.loja_id, veiculo_id, False))


@app.post("/v1/veiculos/{veiculo_id}/reservar")
def reservar(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_privada(servico.reservar(db, ctx.loja_id, veiculo_id))


@app.post("/v1/veiculos/{veiculo_id}/vender")
def vender(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_privada(servico.vender(db, ctx.loja_id, veiculo_id))


# --- API pública (sem autenticação, resolvida por slug) ----------------------


def _loja_publica(loja) -> dict:
    return {"slug": loja.slug, "nome": loja.nome, "whatsapp": loja.whatsapp}


@app.get("/public/v1/lojas/{slug}")
def loja_publica(slug: str, db: Session = Depends(get_db)):
    return _loja_publica(servico.obter_loja_por_slug(db, slug))


@app.get("/public/v1/lojas/{slug}/veiculos")
def veiculos_publicos(
    slug: str,
    tipo: Optional[str] = None,
    preco_min: Optional[float] = None,
    preco_max: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    loja, veiculos = servico.listar_veiculos_publicos(
        db, slug, tipo, preco_min, preco_max, limit, offset
    )
    return {
        "loja": _loja_publica(loja),
        "veiculos": [servico.para_saida_publica(v) for v in veiculos],
    }


@app.get("/public/v1/lojas/{slug}/veiculos/{veiculo_id}")
def veiculo_publico(slug: str, veiculo_id: str, db: Session = Depends(get_db)):
    return servico.para_saida_publica(servico.obter_veiculo_publico(db, slug, veiculo_id))
