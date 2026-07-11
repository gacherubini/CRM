"""API do Motor de Simulação (contrato público v1)."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import config, servico
from app.motor.base import SolicitacaoSimulacao
from app.motor.mock import TAXAS_MOCK

app = FastAPI(title="Motor de Simulação")


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    # Milestone 1 não tem dependências externas; passa a checar Postgres na Task 4.
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


@app.post("/v1/simulacoes", status_code=201)
def criar_simulacao(sol: SolicitacaoSimulacao):
    try:
        sim = servico.criar_simulacao(sol)
    except servico.ErroValidacao as e:
        return JSONResponse(
            status_code=422, content={"erro": {"code": e.code, "message": e.message}}
        )
    # Mock conclui de forma síncrona (atalho permitido pelo Plano #0).
    return {"id": sim.id, "status": sim.status, "criada_em": sim.criada_em}


@app.get("/v1/simulacoes/{sim_id}")
def obter_simulacao(sim_id: str):
    sim = servico.obter_simulacao(sim_id)
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "nao_encontrada", "message": "Simulação não encontrada"}},
        )
    return sim
