"""API privada do Estoque (Plano #4A, `/v1`). API pública `/public/v1` vem depois."""
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import timezone
from email.utils import format_datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import config, models_db, provisioning, servico  # noqa: F401 (registra os modelos)
from app.admin import router as admin_router
from app.auth import Contexto, get_contexto
from app.db import get_db
from app import media

app = FastAPI(title="Estoque API")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    https_only=config.SESSION_SECURE_COOKIE,
    same_site="lax",
    max_age=60 * 60 * 10,
)
app.mount(
    "/admin-static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="admin-static",
)
app.include_router(admin_router)

_rate_lock = Lock()
_rate_publico: dict[tuple[str, int], int] = defaultdict(int)


@app.middleware("http")
async def limitar_api_publica(request: Request, call_next):
    if not request.url.path.startswith("/public/v1/"):
        return await call_next(request)
    limite = config.PUBLIC_RATE_LIMIT_PER_MINUTE
    minuto = int(time.time() // 60)
    cliente = request.client.host if request.client else "desconhecido"
    chave = (cliente, minuto)
    with _rate_lock:
        _rate_publico[chave] += 1
        usados = _rate_publico[chave]
        if len(_rate_publico) > 10000:
            for antiga in [k for k in _rate_publico if k[1] < minuto - 1]:
                _rate_publico.pop(antiga, None)
    if usados > limite:
        return JSONResponse(
            {"detail": "limite de consultas públicas excedido"},
            status_code=429,
            headers={"Retry-After": str(60 - int(time.time() % 60))},
        )
    resposta = await call_next(request)
    resposta.headers["X-RateLimit-Limit"] = str(limite)
    resposta.headers["X-RateLimit-Remaining"] = str(max(limite - usados, 0))
    return resposta

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
    placa: Optional[str] = None
    codigo_interno: Optional[str] = None
    foto_url: Optional[str] = None
    publicado: bool = False


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
    placa: Optional[str] = None
    codigo_interno: Optional[str] = None
    foto_url: Optional[str] = None


class OrdemVitrineItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    ordem_vitrine: int = Field(ge=0, le=1_000_000)


class OrdemVitrineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itens: list[OrdemVitrineItem] = Field(min_length=1, max_length=500)


class FotoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = Field(default=None, max_length=config.MEDIA_URL_MAX_CHARS)
    storage_key: Optional[str] = Field(default=None, max_length=512)
    content_type: str
    tamanho_bytes: int = Field(ge=1)
    ordem: Optional[int] = Field(default=None, ge=0)
    capa: Optional[bool] = None


class FotosInput(BaseModel):
    """Contrato detalhado; ``urls`` continua aceito para clientes legados."""

    model_config = ConfigDict(extra="forbid")

    fotos: Optional[list[FotoInput]] = Field(default=None, max_length=config.MEDIA_MAX_FOTOS)
    urls: Optional[list[str]] = Field(default=None, max_length=config.MEDIA_MAX_FOTOS)

    @model_validator(mode="after")
    def uma_forma_de_entrada(self):
        if (self.fotos is None) == (self.urls is None):
            raise ValueError("informe exatamente fotos ou urls")
        return self


def _pode_ver_custo(ctx: Contexto) -> bool:
    return ctx.papel in {"dono", "gerente"}


def _exigir_operacao(ctx: Contexto) -> None:
    if ctx.papel not in {"dono", "gerente", "operador"}:
        raise HTTPException(status_code=403, detail="papel sem permissão para alterar estoque")


def _exigir_gestao(ctx: Contexto) -> None:
    if ctx.papel not in {"dono", "gerente"}:
        raise HTTPException(status_code=403, detail="papel sem permissão de gestão")


def _exigir_loja_operacional(db: Session, loja_id: str) -> None:
    """Bloqueia novos efeitos quando a projeção do Control não autoriza o módulo estoque."""
    if not provisioning.allows_processing(db, loja_id, module="estoque"):
        raise HTTPException(
            status_code=423,
            detail={"code": "store_not_operational", "message": "loja não operacional"},
        )


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1 FROM idempotencias_criacao_veiculo LIMIT 1"))
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"versao": config.VERSAO, "schema": config.SCHEMA_VERSAO}


@app.post("/v1/internal/provisioning/state")
def receber_estado_provisionamento(
    payload: dict,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Recebe snapshot operacional do Control e aplica projeção monotônica local."""
    loja = db.get(models_db.Loja, ctx.loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    if payload.get("loja_slug") != loja.slug:
        raise HTTPException(status_code=403, detail="slug da loja não confere")
    reasons = provisioning.apply_payload(db, ctx.loja_id, payload)
    db.commit()
    return {
        "ok": True,
        "reasons": reasons,
        "allows_processing": provisioning.allows_processing(
            db, ctx.loja_id, module="estoque"
        ),
    }


@app.post("/v1/veiculos", status_code=201)
def criar_veiculo(
    dados: VeiculoInput,
    idempotency_key: Optional[str] = Header(
        default=None, alias="Idempotency-Key", max_length=512
    ),
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    if dados.custo is not None and not _pode_ver_custo(ctx):
        raise HTTPException(status_code=403, detail="papel sem permissão para informar custo")
    v = servico.criar_veiculo(
        db,
        ctx.loja_id,
        dados.model_dump(exclude_none=True),
        ctx.papel,
        idempotency_key=idempotency_key,
    )
    return servico.para_saida_privada(v, _pode_ver_custo(ctx))


@app.get("/v1/veiculos")
def listar_veiculos(
    tipo: Optional[str] = None,
    status: Optional[str] = None,
    publicado: Optional[bool] = None,
    busca: Optional[str] = None,
    placa: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    veiculos = servico.listar_veiculos(db, ctx.loja_id, tipo, status, publicado, busca, placa)
    return {
        "veiculos": [servico.para_saida_privada(v, _pode_ver_custo(ctx)) for v in veiculos]
    }


@app.put("/v1/veiculos/ordem-vitrine")
def reordenar_vitrine(
    dados: OrdemVitrineInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Reordena veículos na vitrine pública (ordem_vitrine ASC)."""
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    atualizados = servico.reordenar_vitrine(
        db,
        ctx.loja_id,
        [item.model_dump() for item in dados.itens],
        ctx.papel,
    )
    return {
        "ok": True,
        "atualizados": len(atualizados),
        "veiculos": [
            servico.para_saida_privada(v, _pode_ver_custo(ctx)) for v in atualizados
        ],
    }


@app.get("/v1/veiculos/por-placa/{placa}")
def obter_veiculo_por_placa(
    placa: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    """Resolve a unidade da loja autenticada pela placa (privado, escopado por tenancy)."""
    return servico.para_saida_privada(
        servico.obter_veiculo_por_placa(db, ctx.loja_id, placa), _pode_ver_custo(ctx)
    )


@app.get("/v1/veiculos/{veiculo_id}")
def obter_veiculo(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.para_saida_privada(
        servico.obter_veiculo(db, ctx.loja_id, veiculo_id), _pode_ver_custo(ctx)
    )


@app.patch("/v1/veiculos/{veiculo_id}")
def atualizar_veiculo(
    veiculo_id: str,
    dados: VeiculoUpdate,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    if dados.custo is not None and not _pode_ver_custo(ctx):
        raise HTTPException(status_code=403, detail="papel sem permissão para alterar custo")
    v = servico.atualizar_veiculo(
        db, ctx.loja_id, veiculo_id, dados.model_dump(exclude_none=True), ctx.papel
    )
    return servico.para_saida_privada(v, _pode_ver_custo(ctx))


@app.post("/v1/veiculos/{veiculo_id}/publicar")
def publicar(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    return servico.para_saida_privada(
        servico.definir_publicado(db, ctx.loja_id, veiculo_id, True, ctx.papel),
        _pode_ver_custo(ctx),
    )


@app.post("/v1/veiculos/{veiculo_id}/despublicar")
def despublicar(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    # Despublicar permanece permitido sob suspensão (ação de redução de risco / ADR).
    _exigir_operacao(ctx)
    return servico.para_saida_privada(
        servico.definir_publicado(db, ctx.loja_id, veiculo_id, False, ctx.papel),
        _pode_ver_custo(ctx),
    )


@app.post("/v1/veiculos/{veiculo_id}/reservar")
def reservar(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    return servico.para_saida_privada(
        servico.reservar(db, ctx.loja_id, veiculo_id, ctx.papel), _pode_ver_custo(ctx)
    )


@app.post("/v1/veiculos/{veiculo_id}/vender")
def vender(
    veiculo_id: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    return servico.para_saida_privada(
        servico.vender(db, ctx.loja_id, veiculo_id, ctx.papel), _pode_ver_custo(ctx)
    )


@app.put("/v1/veiculos/{veiculo_id}/fotos")
def substituir_fotos(
    veiculo_id: str,
    dados: FotosInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    legado = dados.urls is not None
    fotos = (
        [{"url": url, "capa": indice == 0, "ordem": indice} for indice, url in enumerate(dados.urls)]
        if legado
        else [foto.model_dump(exclude_none=True) for foto in dados.fotos]
    )
    v = servico.substituir_fotos(
        db, ctx.loja_id, veiculo_id, fotos, ctx.papel, legado=legado
    )
    return servico.para_saida_privada(v, _pode_ver_custo(ctx))


@app.post("/v1/veiculos/{veiculo_id}/fotos/upload", status_code=201)
async def upload_foto(
    veiculo_id: str,
    request: Request,
    publicar: bool = Query(default=False),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=512),
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Recebe bytes autenticados, persiste em volume e anexa à galeria do veículo."""
    _exigir_operacao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    mime = media.normalizar_mime_imagem(request.headers.get("content-type"))
    try:
        declarado = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Content-Length inválido") from exc
    if declarado > config.MEDIA_MAX_BYTES:
        raise HTTPException(status_code=413, detail="foto acima do limite")

    bruto = bytearray()
    async for parte in request.stream():
        bruto.extend(parte)
        if len(bruto) > config.MEDIA_MAX_BYTES:
            raise HTTPException(status_code=413, detail="foto acima do limite")
    conteudo = bytes(bruto)
    if not conteudo:
        raise HTTPException(status_code=422, detail="foto vazia")
    media.validar_assinatura(conteudo, mime)

    storage_key = media.gerar_storage_key(
        ctx.loja_id, veiculo_id, mime, idempotency_key
    )
    # Valida tenancy/estado e a URL pública antes de gravar bytes no volume.
    servico.obter_veiculo(db, ctx.loja_id, veiculo_id)
    url = servico._url_por_storage_key(storage_key)
    caminho, criado = media.salvar(storage_key, conteudo)
    try:
        v = servico.adicionar_foto(
            db,
            ctx.loja_id,
            veiculo_id,
            {
                "url": url,
                "content_type": mime,
                "tamanho_bytes": len(conteudo),
                "capa": True,
            },
            ctx.papel,
            publicar=publicar,
        )
    except Exception:
        media.remover_se_novo(caminho, criado)
        raise
    return servico.para_saida_privada(v, _pode_ver_custo(ctx))


@app.get("/v1/auditoria")
def auditoria(
    limit: int = 100,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_gestao(ctx)
    return {
        "eventos": [
            {
                "id": item.id,
                "recurso": item.recurso,
                "recurso_id": item.recurso_id,
                "acao": item.acao,
                "ator_papel": item.ator_papel,
                "dados": item.dados,
                "criada_em": item.criada_em.isoformat(),
            }
            for item in servico.listar_auditoria(db, ctx.loja_id, limit)
        ]
    }


@app.get("/v1/eventos")
def eventos_saida(
    status: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_gestao(ctx)
    return {
        "eventos": [
            {
                "id": item.id,
                "tipo": item.tipo,
                "agregado_id": item.agregado_id,
                "payload": item.payload,
                "status": item.status,
                "tentativas": item.tentativas,
                "criada_em": item.criada_em.isoformat(),
            }
            for item in servico.listar_eventos(db, ctx.loja_id, status)
        ]
    }


class WebhookInput(BaseModel):
    url: str
    segredo: str
    ativo: bool = True


@app.get("/v1/webhook")
def obter_webhook(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    _exigir_gestao(ctx)
    destino = servico.obter_webhook_destino(db, ctx.loja_id)
    if destino is None:
        return {"configurado": False}
    # Nunca devolve o segredo, nem cifrado.
    return {
        "configurado": True,
        "url": destino.url,
        "ativo": destino.ativo,
        "atualizada_em": destino.atualizada_em.isoformat(),
    }


@app.put("/v1/webhook")
def configurar_webhook(
    dados: WebhookInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_gestao(ctx)
    loja = db.get(models_db.Loja, ctx.loja_id)
    destino = servico.configurar_webhook_destino(
        db, loja.slug, dados.url, dados.segredo, dados.ativo
    )
    return {"url": destino.url, "ativo": destino.ativo}


@app.get("/v1/entregas")
def listar_entregas(
    limit: int = Query(default=100, ge=1, le=500),
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_gestao(ctx)
    return {
        "entregas": [
            {
                "id": e.id,
                "evento_id": e.evento_id,
                "destino_url": e.destino_url,
                "tentativa": e.tentativa,
                "status_http": e.status_http,
                "sucesso": e.sucesso,
                "erro": e.erro,
                "criada_em": e.criada_em.isoformat(),
            }
            for e in servico.listar_entregas(db, ctx.loja_id, limit)
        ]
    }


@app.post("/v1/importacoes/csv/preview")
def preview_csv(
    conteudo: bytes = Body(media_type="text/csv"),
    ctx: Contexto = Depends(get_contexto),
):
    return servico.previsualizar_csv(conteudo)


@app.post("/v1/importacoes/csv", status_code=201)
def importar_csv(
    nome_arquivo: str = "estoque.csv",
    conteudo: bytes = Body(media_type="text/csv"),
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_operacao(ctx)
    resultado = servico.importar_csv(
        db, ctx.loja_id, conteudo, nome_arquivo, ctx.papel, _pode_ver_custo(ctx)
    )
    return {
        "id": resultado.id,
        "status": resultado.status,
        "total_linhas": resultado.total_linhas,
        "importadas": resultado.importadas,
        "atualizadas": resultado.atualizadas,
        "erros": resultado.erros,
    }


@app.get("/v1/importacoes")
def listar_importacoes(
    ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    _exigir_gestao(ctx)
    itens = (
        db.query(models_db.Importacao)
        .filter(models_db.Importacao.loja_id == ctx.loja_id)
        .order_by(models_db.Importacao.criada_em.desc())
        .limit(100)
        .all()
    )
    return {
        "importacoes": [
            {
                "id": item.id,
                "nome_arquivo": item.nome_arquivo,
                "status": item.status,
                "total_linhas": item.total_linhas,
                "importadas": item.importadas,
                "atualizadas": item.atualizadas,
                "erros": item.erros,
                "criada_em": item.criada_em.isoformat(),
            }
            for item in itens
        ]
    }


@app.get("/v1/veiculos.csv")
def exportar_csv(
    ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    conteudo = servico.exportar_csv(db, ctx.loja_id, _pode_ver_custo(ctx))
    return Response(
        content="\ufeff" + conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=estoque.csv"},
    )


# --- API pública (sem autenticação, resolvida por slug) ----------------------


@app.get("/public/v1/media/{loja_id}/{veiculo_id}/{arquivo}")
def media_publica(
    loja_id: str,
    veiculo_id: str,
    arquivo: str,
    w: Optional[int] = Query(default=None, description="largura do thumbnail (160|320|640)"),
):
    if w is not None:
        caminho, content_type = media.resolver_thumbnail(loja_id, veiculo_id, arquivo, w)
    else:
        caminho, content_type = media.resolver_publica(loja_id, veiculo_id, arquivo)
    return FileResponse(
        caminho,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _loja_publica(loja) -> dict:
    return {"slug": loja.slug, "nome": loja.nome, "whatsapp": loja.whatsapp}


def _resposta_publica_cache(request: Request, payload: dict, atualizado_em) -> Response:
    bruto = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    etag = f'"{hashlib.sha256(bruto).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60, stale-while-revalidate=300"}
    if atualizado_em:
        if atualizado_em.tzinfo is None:
            atualizado_em = atualizado_em.replace(tzinfo=timezone.utc)
        else:
            atualizado_em = atualizado_em.astimezone(timezone.utc)
        headers["Last-Modified"] = format_datetime(atualizado_em, usegmt=True)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)


@app.get("/public/v1/lojas/{slug}")
def loja_publica(request: Request, slug: str, db: Session = Depends(get_db)):
    loja = servico.obter_loja_por_slug(db, slug)
    return _resposta_publica_cache(request, _loja_publica(loja), loja.criada_em)


class LojaWhatsappUpdate(BaseModel):
    """Atualiza o WhatsApp usado no CTA do catálogo público."""

    model_config = ConfigDict(extra="forbid")

    whatsapp: Optional[str] = Field(default=None, max_length=32)


@app.get("/v1/loja")
def obter_loja_atual(
    ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    loja = db.get(models_db.Loja, ctx.loja_id)
    if loja is None:
        raise HTTPException(status_code=404, detail="loja não encontrada")
    return {"slug": loja.slug, "nome": loja.nome, "whatsapp": loja.whatsapp}


@app.patch("/v1/loja")
def atualizar_loja_atual(
    dados: LojaWhatsappUpdate,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    _exigir_gestao(ctx)
    _exigir_loja_operacional(db, ctx.loja_id)
    loja = servico.atualizar_whatsapp_loja(db, ctx.loja_id, dados.whatsapp)
    return {"slug": loja.slug, "nome": loja.nome, "whatsapp": loja.whatsapp}


@app.get("/public/v1/lojas/{slug}/veiculos")
def veiculos_publicos(
    request: Request,
    slug: str,
    tipo: Optional[str] = None,
    marca: Optional[str] = None,
    preco_min: Optional[float] = None,
    preco_max: Optional[float] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    loja, veiculos, total = servico.listar_veiculos_publicos(
        db, slug, tipo, marca, preco_min, preco_max, limit, offset
    )
    payload = {
        "loja": _loja_publica(loja),
        "veiculos": [servico.para_saida_publica(v) for v in veiculos],
        "paginacao": {
            "limit": limit,
            "offset": offset,
            "quantidade": len(veiculos),
            "total": total,
        },
    }
    atualizado = max((v.atualizado_em for v in veiculos if v.atualizado_em), default=loja.criada_em)
    return _resposta_publica_cache(request, payload, atualizado)


@app.get("/public/v1/lojas/{slug}/veiculos/{veiculo_id}")
def veiculo_publico(
    request: Request, slug: str, veiculo_id: str, db: Session = Depends(get_db)
):
    veiculo = servico.obter_veiculo_publico(db, slug, veiculo_id)
    return _resposta_publica_cache(
        request, servico.para_saida_publica(veiculo), veiculo.atualizado_em
    )
