"""API do Motor de Simulação (contrato público v1)."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app import auth, config, credenciais, models_db, observabilidade, servico  # noqa: F401
from app.db import Base, engine, get_db
from app.motor.base import SolicitacaoSimulacao
from app.motor.mock import TAXAS_MOCK
from app.motor.providers import listar_provedores as listar_provedores_reais
from app.motor.providers import nomes_provedores_reais

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
    """Provedores reais configuráveis por cliente."""
    return nomes_provedores_reais()


def _ator(request: Request, cliente) -> str:
    """Identidade de quem alterou a credencial (Portal repassa via header X-Ator)."""
    return request.headers.get("X-Ator") or getattr(cliente, "nome", "desconhecido")


@app.get("/v1/provedores")
def provedores():
    return {
        "provedores": [
            {
                "nome": "mock",
                "rotulo": "Bancos de demonstração",
                "habilitado": True,
                "real": False,
                "modo": "mock",
                "campos_credencial": [],
            },
            *listar_provedores_reais(),
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
    # Quem disparou (Portal repassa email do usuário logado via X-Ator). Sem
    # header fica nulo — chamada direta à API não tem "ator" de histórico.
    solicitado_por = request.headers.get("X-Ator")
    try:
        sim, criada = servico.criar_simulacao(
            db, sol, cliente.id, idempotency_key, solicitado_por=solicitado_por
        )
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


@app.get("/v1/simulacoes")
def listar_simulacoes(
    request: Request,
    status: str | None = None,
    solicitado_por: str | None = None,
    desde: str | None = None,
    ate: str | None = None,
    limite: int = Query(servico.LISTAGEM_LIMITE_PADRAO, ge=1),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    """Histórico de simulações do cliente (tenancy). Filtros e paginação.

    Nunca decifra o payload pessoal — devolve só a projeção não sensível
    (placa, referência, provedores, prazos, status).
    """
    if isinstance(cliente, JSONResponse):
        return cliente
    itens, total, limite_aplicado, offset_aplicado = servico.listar_simulacoes(
        db,
        cliente.id,
        status=status,
        solicitado_por=solicitado_por,
        desde=desde,
        ate=ate,
        limite=limite,
        offset=offset,
    )
    projetados = [servico.simulacao_resumo(s) for s in itens]
    return {
        "itens": projetados,
        "total": total,
        "limite": limite_aplicado,
        "offset": offset_aplicado,
        "resumo": {"total": total, "retornados": len(projetados)},
    }


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


@app.get("/v1/simulacoes/{sim_id}/eventos")
def listar_eventos_simulacao(
    sim_id: str,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    sim, eventos = servico.listar_eventos_simulacao(db, sim_id, cliente.id)
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "nao_encontrada", "message": "Simulação não encontrada"}},
        )
    return {
        "simulacao_id": sim.id,
        "status": sim.status,
        "eventos": [servico.evento_publico(e) for e in eventos],
    }


@app.get("/v1/simulacoes/{sim_id}/eventos/{evento_id}/print")
def obter_print_evento(
    sim_id: str,
    evento_id: int,
    db: Session = Depends(get_db),
    cliente=Depends(auth.autenticar_cliente),
):
    if isinstance(cliente, JSONResponse):
        return cliente
    sim, eventos = servico.listar_eventos_simulacao(db, sim_id, cliente.id)
    evento = next((e for e in eventos if e.id == evento_id), None)
    if sim is None or evento is None:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "print_nao_encontrado", "message": "Print não encontrado"}},
        )
    # Preferência: blob gravado no evento (workers sob demanda em outras Machines).
    blob = getattr(evento, "screenshot_conteudo", None)
    if blob:
        from fastapi.responses import Response

        raw = bytes(blob)
        # JPEG (novos) ou PNG (legado) — detecta pelo magic number.
        if raw[:3] == b"\xff\xd8\xff":
            media = "image/jpeg"
            ext = "jpg"
        else:
            media = "image/png"
            ext = "png"
        return Response(
            content=raw,
            media_type=media,
            headers={
                "Content-Disposition": f'inline; filename="simulacao-{sim_id}-{evento_id}.{ext}"',
                "Cache-Control": "private, no-store",
            },
        )
    if not evento.screenshot_path:
        return JSONResponse(
            status_code=404,
            content={"erro": {"code": "print_nao_encontrado", "message": "Print não encontrado"}},
        )
    raiz = Path(config.SCREENSHOT_DIR).resolve()
    arquivo = Path(evento.screenshot_path).resolve()
    try:
        arquivo.relative_to(raiz)
    except ValueError:
        return JSONResponse(status_code=404, content={"erro": {"code": "print_invalido"}})
    if not arquivo.is_file():
        return JSONResponse(status_code=404, content={"erro": {"code": "print_ausente"}})
    return FileResponse(arquivo, media_type="image/png", filename=f"simulacao-{sim_id}.png")


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
