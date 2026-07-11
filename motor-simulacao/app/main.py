"""API do Motor de Simulação (contrato público v1)."""
import os

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import config, models_db, servico  # noqa: F401 (registra os modelos)
from app.db import Base, engine, get_db
from app.motor.base import SolicitacaoSimulacao
from app.motor.mock import TAXAS_MOCK

app = FastAPI(title="Motor de Simulação")

# Bootstrap de dev: cria as tabelas se ainda não existirem. Em produção as
# migrações Alembic assumem (Plano #1A, Task 4). Sob pytest, os testes criam o
# schema num banco isolado, então pulamos aqui.
if os.getenv("MOTOR_SKIP_INIT") != "1":
    Base.metadata.create_all(bind=engine)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"versao": config.VERSAO, "schema": config.SCHEMA_VERSAO}


@app.get("/v1/provedores")
def provedores():
    return {
        "provedores": [
            {"nome": banco, "habilitado": True, "real": False} for banco in TAXAS_MOCK
        ]
    }


@app.post("/v1/simulacoes")
def criar_simulacao(
    sol: SolicitacaoSimulacao,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    idempotency_key = request.headers.get("Idempotency-Key")
    try:
        sim, criada = servico.criar_simulacao(db, sol, idempotency_key)
    except servico.ErroValidacao as e:
        return JSONResponse(
            status_code=422, content={"erro": {"code": e.code, "message": e.message}}
        )
    except servico.ErroIdempotencia as e:
        return JSONResponse(
            status_code=409, content={"erro": {"code": e.code, "message": e.message}}
        )
    # 201 quando cria de fato; 200 quando reusa por idempotência.
    response.status_code = 201 if criada else 200
    return {"id": sim.id, "status": sim.status, "criada_em": sim.criada_em.isoformat()}


@app.get("/v1/simulacoes/{sim_id}")
def obter_simulacao(sim_id: str, db: Session = Depends(get_db)):
    sim = servico.obter_simulacao(db, sim_id)
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "nao_encontrada", "message": "Simulação não encontrada"}},
        )
    return servico.para_pydantic(sim)


@app.post("/v1/simulacoes/{sim_id}/cancelar")
def cancelar_simulacao(sim_id: str, db: Session = Depends(get_db)):
    sim = servico.cancelar_simulacao(db, sim_id)
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "nao_encontrada", "message": "Simulação não encontrada"}},
        )
    return {"id": sim.id, "status": sim.status}
