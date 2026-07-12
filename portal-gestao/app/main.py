import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401
from app.auth import (
    autenticar,
    csrf_token,
    csrf_valido,
    encerrar_sessao,
    iniciar_sessao,
    pode_gerir_estoque,
    pode_ver_custo,
    usuario_atual,
)
from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel, LeadNaoEncontrado
from app.clients.estoque import EstoqueClient, EstoqueIndisponivel
from app.config import settings
from app.db import Base, engine, get_db

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def mascarar_telefone(telefone: str | None) -> str:
    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    if len(digitos) < 4:
        return "•••"
    return f"•••• {digitos[-4:]}"


templates.env.globals["mascarar_telefone"] = mascarar_telefone

app = FastAPI(title="Portal de Gestão", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=settings.secure_cookie,
    same_site="lax",
    max_age=60 * 60 * 10,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

if os.getenv("PORTAL_SKIP_INIT") != "1":
    Base.metadata.create_all(bind=engine)


@app.middleware("http")
async def headers_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resposta


def get_estoque_client() -> EstoqueClient:
    return EstoqueClient(settings.estoque_url, settings.estoque_token, settings.request_timeout)


def get_chatbot_client() -> ChatbotClient:
    return ChatbotClient(settings.chatbot_url, settings.chatbot_token, settings.request_timeout)


def redirecionar_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def contexto(request: Request, usuario=None, **extra):
    return {
        "request": request,
        "usuario": usuario,
        "csrf": csrf_token(request),
        "versao": settings.version,
        **extra,
    }


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "estoque_configurado": bool(settings.estoque_token),
    }


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/app", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_pagina(request: Request, db: Session = Depends(get_db)):
    if usuario_atual(request, db):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse("login.html", contexto(request))


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    if not csrf_valido(request, csrf):
        return templates.TemplateResponse(
            "login.html", contexto(request, erro="Sessão expirada. Tente novamente."), status_code=400
        )
    usuario = autenticar(db, email, senha)
    if not usuario:
        return templates.TemplateResponse(
            "login.html", contexto(request, erro="E-mail ou senha inválidos."), status_code=401
        )
    iniciar_sessao(request, usuario)
    return RedirectResponse("/app", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: Annotated[str, Form()]):
    if csrf_valido(request, csrf):
        encerrar_sessao(request)
    return RedirectResponse("/login", status_code=303)


@app.get("/app", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    veiculos, erro = [], None
    try:
        veiculos = estoque.listar()
    except EstoqueIndisponivel as exc:
        erro = str(exc)
    metricas = {
        "disponiveis": sum(v["status"] == "disponivel" for v in veiculos),
        "reservados": sum(v["status"] == "reservado" for v in veiculos),
        "publicados": sum(bool(v["publicado"]) for v in veiculos),
        "total": len(veiculos),
    }
    return templates.TemplateResponse(
        "dashboard.html",
        contexto(
            request,
            usuario,
            metricas=metricas,
            veiculos=veiculos[:5],
            integracao_erro=erro,
            pode_gerir=pode_gerir_estoque(usuario),
        ),
    )


@app.get("/app/estoque", response_class=HTMLResponse)
def estoque_lista(
    request: Request,
    tipo: str | None = None,
    status: str | None = None,
    publicado: str | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    veiculos, erro = [], None
    publicado_bool = None if publicado in (None, "") else publicado == "true"
    try:
        veiculos = estoque.listar(
            tipo=tipo, status=status, publicado=publicado_bool, busca=busca
        )
    except EstoqueIndisponivel as exc:
        erro = str(exc)
    return templates.TemplateResponse(
        "estoque/lista.html",
        contexto(
            request,
            usuario,
            veiculos=veiculos,
            filtros={"tipo": tipo or "", "status": status or "", "publicado": publicado or "", "busca": busca or ""},
            integracao_erro=erro,
            pode_gerir=pode_gerir_estoque(usuario),
            pode_custo=pode_ver_custo(usuario),
        ),
    )


@app.get("/app/estoque/novo", response_class=HTMLResponse)
def estoque_novo(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_estoque(usuario):
        return RedirectResponse("/app/estoque", status_code=303)
    return templates.TemplateResponse(
        "estoque/form.html",
        contexto(request, usuario, veiculo=None, titulo="Cadastrar veículo", pode_custo=True),
    )


def dados_veiculo(form, incluir_custo: bool) -> dict:
    dados = {
        "tipo": form.get("tipo"),
        "marca": form.get("marca", "").strip(),
        "modelo": form.get("modelo", "").strip(),
        "versao": form.get("versao", "").strip() or None,
        "ano_modelo": int(form.get("ano_modelo")),
        "cor": form.get("cor", "").strip() or None,
        "km": int(form.get("km") or 0),
        "preco": float(str(form.get("preco")).replace(",", ".")),
        "codigo_interno": form.get("codigo_interno", "").strip() or None,
        "foto_url": form.get("foto_url", "").strip() or None,
    }
    if incluir_custo and form.get("custo"):
        dados["custo"] = float(str(form.get("custo")).replace(",", "."))
    return dados


@app.post("/app/estoque/novo")
async def estoque_criar(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_estoque(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/estoque", status_code=303)
    try:
        estoque.criar(dados_veiculo(form, pode_ver_custo(usuario)))
    except (EstoqueIndisponivel, ValueError) as exc:
        return templates.TemplateResponse(
            "estoque/form.html",
            contexto(request, usuario, veiculo=dict(form), titulo="Cadastrar veículo", erro=str(exc), pode_custo=pode_ver_custo(usuario)),
            status_code=422,
        )
    return RedirectResponse("/app/estoque?ok=criado", status_code=303)


@app.get("/app/estoque/{veiculo_id}", response_class=HTMLResponse)
def estoque_editar_pagina(
    request: Request,
    veiculo_id: str,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_estoque(usuario):
        return RedirectResponse("/app/estoque", status_code=303)
    try:
        veiculo = estoque.obter(veiculo_id)
    except EstoqueIndisponivel as exc:
        return templates.TemplateResponse(
            "erro.html", contexto(request, usuario, erro=str(exc)), status_code=503
        )
    return templates.TemplateResponse(
        "estoque/form.html",
        contexto(request, usuario, veiculo=veiculo, titulo="Editar veículo", pode_custo=pode_ver_custo(usuario)),
    )


@app.post("/app/estoque/{veiculo_id}")
async def estoque_editar(
    request: Request,
    veiculo_id: str,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_estoque(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/estoque", status_code=303)
    try:
        estoque.atualizar(veiculo_id, dados_veiculo(form, pode_ver_custo(usuario)))
    except (EstoqueIndisponivel, ValueError) as exc:
        return templates.TemplateResponse(
            "estoque/form.html",
            contexto(request, usuario, veiculo={**dict(form), "id": veiculo_id}, titulo="Editar veículo", erro=str(exc), pode_custo=pode_ver_custo(usuario)),
            status_code=422,
        )
    return RedirectResponse("/app/estoque?ok=atualizado", status_code=303)


@app.post("/app/estoque/{veiculo_id}/{acao}")
async def estoque_acao(
    request: Request,
    veiculo_id: str,
    acao: str,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_estoque(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/estoque", status_code=303)
    if acao not in {"publicar", "despublicar", "reservar", "vender"}:
        return RedirectResponse("/app/estoque?erro=acao", status_code=303)
    try:
        estoque.acao(veiculo_id, acao)
    except (EstoqueIndisponivel, ValueError):
        return RedirectResponse("/app/estoque?erro=acao", status_code=303)
    return RedirectResponse(f"/app/estoque?ok={acao}", status_code=303)


def filtrar_leads(leads: list[dict], busca: str | None) -> list[dict]:
    if not busca:
        return leads
    termo = busca.strip().lower()
    resultado = []
    for lead in leads:
        campos = [lead.get("nome") or "", lead.get("telefone") or "", lead.get("interesse") or ""]
        if any(termo in campo.lower() for campo in campos):
            resultado.append(lead)
    return resultado


@app.get("/app/leads", response_class=HTMLResponse)
def leads_lista(
    request: Request,
    etapa: str | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    leads, erro = [], None
    try:
        leads = filtrar_leads(chatbot.listar_leads(etapa=etapa or None), busca)
    except ChatbotIndisponivel as exc:
        erro = str(exc)
    return templates.TemplateResponse(
        "leads/lista.html",
        contexto(
            request,
            usuario,
            leads=leads,
            filtros={"etapa": etapa or "", "busca": busca or ""},
            integracao_erro=erro,
        ),
    )


@app.get("/app/leads/{lead_id}", response_class=HTMLResponse)
def leads_detalhe(
    request: Request,
    lead_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    try:
        lead = chatbot.obter_lead(lead_id)
    except LeadNaoEncontrado:
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Lead não encontrado."),
            status_code=404,
        )
    except ChatbotIndisponivel as exc:
        return templates.TemplateResponse(
            "leads/lista.html",
            contexto(request, usuario, leads=[], filtros={"etapa": "", "busca": ""}, integracao_erro=str(exc)),
        )
    return templates.TemplateResponse(
        "leads/detalhe.html",
        contexto(request, usuario, lead=lead),
    )


@app.get("/app/conversas", response_class=HTMLResponse)
def conversas_placeholder(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    return templates.TemplateResponse(
        "em-breve.html",
        contexto(request, usuario, titulo="Conversas", texto="Estamos preparando a lista de conversas e o controle de handoff."),
    )


@app.get("/app/simulacoes", response_class=HTMLResponse)
def simulacoes_placeholder(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in {"dono", "gerente", "admin_plataforma"}:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "em-breve.html",
        contexto(request, usuario, titulo="Simulações", texto="A simulação manual será habilitada quando o provedor estiver disponível."),
    )


@app.get("/app/equipe", response_class=HTMLResponse)
def equipe_placeholder(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in {"dono", "admin_plataforma"}:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "em-breve.html",
        contexto(request, usuario, titulo="Equipe", texto="A administração da equipe será conectada ao banco próprio do Portal."),
    )


@app.get("/app/configuracoes", response_class=HTMLResponse)
def configuracoes_placeholder(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in {"dono", "admin_plataforma"}:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "em-breve.html",
        contexto(request, usuario, titulo="Configurações", texto="As integrações serão configuradas sem expor credenciais ao navegador."),
    )
