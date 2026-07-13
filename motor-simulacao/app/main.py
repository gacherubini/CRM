"""API do Motor de Simulação (contrato público v1)."""
import hmac
import os

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import auth, config, credenciais, models_db, observabilidade, servico  # noqa: F401
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


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request, db: Session = Depends(get_db)):
    """Métricas Prometheus agregadas; token dedicado e opcional para o scraper."""
    token = config.METRICS_TOKEN
    recebido = request.headers.get("Authorization", "")
    if token and not hmac.compare_digest(recebido, f"Bearer {token}"):
        return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return Response(
        content=observabilidade.gerar_metricas(db),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _nomes_provedores() -> list[str]:
    """Provedores conhecidos do Motor. Hoje só o mock; drivers reais entram na Task 12."""
    return list(TAXAS_MOCK)


def _ator(request: Request, cliente) -> str:
    """Identidade de quem alterou a credencial (Portal repassa via header X-Ator)."""
    return request.headers.get("X-Ator") or getattr(cliente, "nome", "desconhecido")


@app.get("/v1/provedores")
def provedores():
    return {
        "provedores": [
            {"nome": banco, "habilitado": True, "real": False} for banco in TAXAS_MOCK
        ]
    }


@app.get("/v1/provedores/credenciais")
def listar_credenciais_provedor(
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    return {
        "credenciais": credenciais.listar_credenciais(db, cliente.id, _nomes_provedores())
    }


@app.get("/v1/provedores/{nome}/credenciais")
def obter_credencial_provedor(
    nome: str,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    cred = credenciais.obter_credencial_mascarada(db, cliente.id, nome)
    if cred is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "sem_credencial", "message": "Credencial não configurada"}},
        )
    return cred


@app.put("/v1/provedores/{nome}/credenciais")
def upsert_credencial_provedor(
    nome: str,
    dados: credenciais.CredencialEntrada,
    request: Request,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    credenciais.upsert_credencial(db, cliente.id, nome, dados, _ator(request, cliente))
    # Nunca ecoa a senha; devolve só a projeção mascarada.
    return credenciais.obter_credencial_mascarada(db, cliente.id, nome)


@app.post("/v1/provedores/{nome}/testar-login")
def testar_login_provedor(
    nome: str,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    resultado = credenciais.testar_login(db, cliente.id, nome)
    if resultado is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "sem_credencial", "message": "Credencial não configurada"}},
        )
    return resultado


@app.post("/v1/simulacoes")
def criar_simulacao(
    sol: SolicitacaoSimulacao,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    idempotency_key = request.headers.get("Idempotency-Key")
    try:
        sim, criada = servico.criar_simulacao(db, sol, cliente.id, idempotency_key)
    except servico.ErroValidacao as e:
        return JSONResponse(
            status_code=422, content={"erro": {"code": e.code, "message": e.message}}
        )
    except servico.ErroIdempotencia as e:
        return JSONResponse(
            status_code=409, content={"erro": {"code": e.code, "message": e.message}}
        )
    # 202 quando enfileira de fato (job assíncrono); 200 quando reusa por idempotência.
    response.status_code = 202 if criada else 200
    return {"id": sim.id, "status": sim.status, "criada_em": sim.criada_em.isoformat()}


@app.get("/v1/simulacoes/{sim_id}")
def obter_simulacao(
    sim_id: str,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    sim = servico.obter_simulacao(db, sim_id, cliente.id)
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "nao_encontrada", "message": "Simulação não encontrada"}},
        )
    return servico.para_pydantic(sim)


@app.post("/v1/simulacoes/{sim_id}/cancelar")
def cancelar_simulacao(
    sim_id: str,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    sim = servico.cancelar_simulacao(db, sim_id, cliente.id)
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "nao_encontrada", "message": "Simulação não encontrada"}},
        )
    return {"id": sim.id, "status": sim.status}
