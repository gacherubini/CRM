import calendar
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
    pode_confirmar_venda,
    pode_gerir_metas,
    pode_gerir_estoque,
    pode_registrar_venda,
    pode_ver_custo,
    pode_ver_financeiro,
    usuario_atual,
)
from app.models import Meta, Venda, VendaCustoDireto, agora
from app.clients.chatbot import (
    ChatbotClient,
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    LeadNaoEncontrado,
    SimulacaoIndisponivel,
)
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


def formatar_horario(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        momento = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return momento.strftime("%d/%m %H:%M")


def mascarar_cpf(cpf: str | None) -> str:
    digitos = "".join(c for c in (cpf or "") if c.isdigit())
    if len(digitos) < 3:
        return "•••"
    return f"•••.•••.•••-{digitos[-2:]}"


def formatar_brl(valor) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    texto = f"{numero:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


templates.env.globals["mascarar_telefone"] = mascarar_telefone
templates.env.globals["formatar_horario"] = formatar_horario
templates.env.globals["mascarar_cpf"] = mascarar_cpf
templates.env.globals["formatar_brl"] = formatar_brl

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
def conversas_lista(
    request: Request,
    busca: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    conversas, erro = [], None
    try:
        conversas = chatbot.listar_conversas(busca=busca or None)
    except ChatbotIndisponivel as exc:
        erro = str(exc)
    return templates.TemplateResponse(
        "conversas/lista.html",
        contexto(
            request,
            usuario,
            conversas=conversas,
            filtros={"busca": busca or ""},
            integracao_erro=erro,
        ),
    )


@app.get("/app/conversas/{telefone}", response_class=HTMLResponse)
def conversas_detalhe(
    request: Request,
    telefone: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    try:
        mensagens = chatbot.listar_mensagens(telefone)
        estado = chatbot.obter_estado(telefone)
    except ConversaNaoEncontrada:
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Conversa não encontrada."),
            status_code=404,
        )
    except ChatbotIndisponivel as exc:
        return templates.TemplateResponse(
            "conversas/lista.html",
            contexto(request, usuario, conversas=[], filtros={"busca": ""}, integracao_erro=str(exc)),
        )
    return templates.TemplateResponse(
        "conversas/detalhe.html",
        contexto(request, usuario, telefone=telefone, mensagens=mensagens, estado=estado),
    )


@app.post("/app/conversas/{telefone}/handoff")
async def conversas_handoff(
    request: Request,
    telefone: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    destino = f"/app/conversas/{telefone}"
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(destino, status_code=303)
    acao = form.get("acao")
    if acao not in {"assumir", "devolver"}:
        return RedirectResponse(f"{destino}?erro=acao", status_code=303)
    try:
        chatbot.definir_bot_ativo(telefone, bot_ativo=acao == "devolver")
    except ChatbotIndisponivel:
        return RedirectResponse(f"{destino}?erro=indisponivel", status_code=303)
    return RedirectResponse(f"{destino}?ok={acao}", status_code=303)


def pode_simular(usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "admin_plataforma"}


def dados_simulacao(form) -> dict:
    payload = {
        "cpf": "".join(c for c in (form.get("cpf") or "") if c.isdigit()),
        "nascimento": form.get("nascimento", "").strip(),
        "valor": float(str(form.get("valor")).replace(",", ".")),
        "prazo_meses": int(form.get("prazo_meses")),
        "entrada": float(str(form.get("entrada") or 0).replace(",", ".")),
        "categoria": form.get("categoria") or "moto",
    }
    if form.get("renda"):
        payload["renda"] = float(str(form.get("renda")).replace(",", "."))
    return payload


@app.get("/app/simulacoes", response_class=HTMLResponse)
def simulacoes_pagina(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "simulacoes/form.html",
        contexto(request, usuario, valores={}),
    )


@app.post("/app/simulacoes", response_class=HTMLResponse)
async def simulacoes_simular(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/simulacoes", status_code=303)
    valores = {
        "nascimento": form.get("nascimento", ""),
        "valor": form.get("valor", ""),
        "prazo_meses": form.get("prazo_meses", ""),
        "entrada": form.get("entrada", ""),
        "renda": form.get("renda", ""),
        "categoria": form.get("categoria", "moto"),
    }
    try:
        payload = dados_simulacao(form)
    except (TypeError, ValueError):
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(request, usuario, valores=valores, erro="Confira os valores informados e tente novamente."),
            status_code=422,
        )
    try:
        resultado = chatbot.simular(payload)
    except SimulacaoIndisponivel:
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(request, usuario, valores=valores, erro="Simulação não habilitada nesta instalação."),
            status_code=409,
        )
    except ChatbotIndisponivel as exc:
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(request, usuario, valores=valores, erro=str(exc)),
            status_code=503,
        )
    return templates.TemplateResponse(
        "simulacoes/resultado.html",
        contexto(
            request,
            usuario,
            valores=valores,
            resultado=resultado,
            cpf_mascarado=mascarar_cpf(payload["cpf"]),
        ),
    )


CATEGORIAS_CUSTO = ["documentacao", "frete", "comissao", "outros"]
STATUS_VENDA = ["registrada", "confirmada", "cancelada"]
TIPOS_META = {
    "quantidade": "Quantidade de vendas",
    "faturamento": "Faturamento",
    "lucro_bruto": "Lucro bruto",
}
CENTAVOS = Decimal("0.01")


def dinheiro(texto) -> Decimal:
    return Decimal(str(texto).replace(",", ".")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _data(momento):
    return momento.date() if isinstance(momento, datetime) else momento


def ultimo_dia_mes(dia: date) -> date:
    return date(dia.year, dia.month, calendar.monthrange(dia.year, dia.month)[1])


def periodo_padrao(inicio: str | None, fim: str | None) -> tuple[date, date]:
    hoje = date.today()
    try:
        d_inicio = date.fromisoformat(inicio) if inicio else hoje.replace(day=1)
    except ValueError:
        d_inicio = hoje.replace(day=1)
    try:
        d_fim = date.fromisoformat(fim) if fim else ultimo_dia_mes(hoje)
    except ValueError:
        d_fim = ultimo_dia_mes(hoje)
    return d_inicio, d_fim


def lucro_bruto_venda(venda: Venda) -> Decimal | None:
    if venda.custo_veiculo is None:
        return None
    custo = venda.custo_veiculo
    diretos = sum((c.valor for c in venda.custos_diretos), Decimal("0"))
    return (venda.preco_venda - custo - diretos).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


@app.get("/app/vendas", response_class=HTMLResponse)
def vendas_lista(
    request: Request,
    status: str | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    consulta = db.query(Venda).filter(Venda.loja_slug == usuario.loja_slug)
    if not pode_ver_financeiro(usuario):
        consulta = consulta.filter(Venda.vendedor_email == usuario.email)
    if status in STATUS_VENDA:
        consulta = consulta.filter(Venda.status == status)
    vendas = [
        v
        for v in consulta.order_by(Venda.criada_em.desc()).all()
        if d_inicio <= _data(v.criada_em) <= d_fim
    ]
    return templates.TemplateResponse(
        "vendas/lista.html",
        contexto(
            request,
            usuario,
            vendas=vendas,
            lucro=lucro_bruto_venda,
            filtros={"status": status or "", "inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            pode_financeiro=pode_ver_financeiro(usuario),
            pode_confirmar=pode_confirmar_venda(usuario),
            pode_registrar=pode_registrar_venda(usuario),
        ),
    )


@app.get("/app/vendas/nova", response_class=HTMLResponse)
def vendas_nova(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_registrar_venda(usuario):
        return RedirectResponse("/app/vendas", status_code=303)
    return templates.TemplateResponse(
        "vendas/form.html",
        contexto(request, usuario, valores={}, categorias=CATEGORIAS_CUSTO, pode_financeiro=pode_ver_financeiro(usuario)),
    )


@app.post("/app/vendas/nova")
async def vendas_criar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_registrar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/vendas", status_code=303)
    valores = {
        campo: (form.get(campo) or "")
        for campo in ("descricao", "preco_venda", "lead_ref", "veiculo_ref", "custo_veiculo", "custo_categoria", "custo_valor")
    }
    descricao = (form.get("descricao") or "").strip()
    try:
        preco = dinheiro(form.get("preco_venda"))
    except (InvalidOperation, TypeError):
        preco = None
    if not descricao or preco is None or preco <= 0:
        return templates.TemplateResponse(
            "vendas/form.html",
            contexto(request, usuario, valores=valores, categorias=CATEGORIAS_CUSTO, pode_financeiro=pode_ver_financeiro(usuario), erro="Informe descrição e preço de venda válidos."),
            status_code=422,
        )
    venda = Venda(
        loja_slug=usuario.loja_slug,
        vendedor_email=usuario.email,
        descricao=descricao,
        preco_venda=preco,
        lead_ref=(form.get("lead_ref") or "").strip() or None,
        veiculo_ref=(form.get("veiculo_ref") or "").strip() or None,
        status="registrada",
    )
    if pode_ver_financeiro(usuario):
        if form.get("custo_veiculo"):
            try:
                venda.custo_veiculo = dinheiro(form.get("custo_veiculo"))
            except (InvalidOperation, TypeError):
                pass
        categoria = form.get("custo_categoria")
        if form.get("custo_valor") and categoria in CATEGORIAS_CUSTO:
            try:
                venda.custos_diretos.append(VendaCustoDireto(categoria=categoria, valor=dinheiro(form.get("custo_valor"))))
            except (InvalidOperation, TypeError):
                pass
    db.add(venda)
    db.commit()
    return RedirectResponse("/app/vendas?ok=registrada", status_code=303)


@app.post("/app/vendas/{venda_id}/confirmar")
async def vendas_confirmar(request: Request, venda_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_confirmar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/vendas", status_code=303)
    venda = db.query(Venda).filter(Venda.id == venda_id, Venda.loja_slug == usuario.loja_slug).first()
    if not venda or venda.status == "cancelada":
        return RedirectResponse("/app/vendas?erro=acao", status_code=303)
    venda.status = "confirmada"
    venda.confirmada_por = usuario.email
    venda.confirmada_em = agora()
    venda.atualizada_em = agora()
    db.commit()
    return RedirectResponse("/app/vendas?ok=confirmada", status_code=303)


@app.post("/app/vendas/{venda_id}/cancelar")
async def vendas_cancelar(request: Request, venda_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_confirmar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/vendas", status_code=303)
    venda = db.query(Venda).filter(Venda.id == venda_id, Venda.loja_slug == usuario.loja_slug).first()
    motivo = (form.get("motivo") or "").strip()
    if not venda:
        return RedirectResponse("/app/vendas?erro=acao", status_code=303)
    if not motivo:
        return RedirectResponse("/app/vendas?erro=motivo", status_code=303)
    venda.status = "cancelada"
    venda.motivo_cancelamento = motivo
    venda.atualizada_em = agora()
    db.commit()
    return RedirectResponse("/app/vendas?ok=cancelada", status_code=303)


def valores_meta_form(form) -> dict[str, str]:
    return {
        campo: (form.get(campo) or "")
        for campo in ("tipo", "periodo_inicio", "periodo_fim", "valor_alvo")
    }


def validar_meta_form(form) -> tuple[str, date, date, Decimal]:
    tipo = (form.get("tipo") or "").strip()
    if tipo not in TIPOS_META:
        raise ValueError("Selecione um tipo de meta válido.")
    try:
        inicio = date.fromisoformat(form.get("periodo_inicio") or "")
        fim = date.fromisoformat(form.get("periodo_fim") or "")
    except ValueError as exc:
        raise ValueError("Informe um período válido.") from exc
    if inicio > fim:
        raise ValueError("A data inicial não pode ser posterior à data final.")
    try:
        alvo = dinheiro(form.get("valor_alvo"))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Informe um alvo válido.") from exc
    if alvo <= 0:
        raise ValueError("O alvo deve ser maior que zero.")
    if tipo == "quantidade" and alvo != alvo.to_integral_value():
        raise ValueError("A meta de quantidade deve ser um número inteiro.")
    return tipo, inicio, fim, alvo


def meta_sobreposta(
    db: Session,
    loja_slug: str,
    tipo: str,
    inicio: date,
    fim: date,
    ignorar_id: str | None = None,
) -> bool:
    consulta = db.query(Meta).filter(
        Meta.loja_slug == loja_slug,
        Meta.escopo == "loja",
        Meta.tipo == tipo,
        Meta.ativa.is_(True),
        Meta.periodo_inicio <= fim,
        Meta.periodo_fim >= inicio,
    )
    if ignorar_id:
        consulta = consulta.filter(Meta.id != ignorar_id)
    return consulta.first() is not None


def render_meta_form(request: Request, usuario, valores, titulo: str, erro: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        "metas/form.html",
        contexto(
            request,
            usuario,
            valores=valores,
            titulo=titulo,
            tipos=TIPOS_META,
            erro=erro,
        ),
        status_code=status_code,
    )


@app.get("/app/metas", response_class=HTMLResponse)
def metas_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    metas = (
        db.query(Meta)
        .filter(Meta.loja_slug == usuario.loja_slug, Meta.escopo == "loja")
        .order_by(Meta.ativa.desc(), Meta.periodo_inicio.desc())
        .all()
    )
    return templates.TemplateResponse(
        "metas/lista.html",
        contexto(
            request,
            usuario,
            metas=metas,
            tipos=TIPOS_META,
            pode_gerir=pode_gerir_metas(usuario),
        ),
    )


@app.get("/app/metas/nova", response_class=HTMLResponse)
def metas_nova(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_metas(usuario):
        return RedirectResponse("/app/metas", status_code=303)
    return render_meta_form(request, usuario, {}, "Cadastrar meta da loja")


@app.post("/app/metas/nova")
async def metas_criar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_metas(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/metas", status_code=303)
    valores = valores_meta_form(form)
    try:
        tipo, inicio, fim, alvo = validar_meta_form(form)
    except ValueError as exc:
        return render_meta_form(request, usuario, valores, "Cadastrar meta da loja", str(exc), 422)
    if meta_sobreposta(db, usuario.loja_slug, tipo, inicio, fim):
        return render_meta_form(
            request,
            usuario,
            valores,
            "Cadastrar meta da loja",
            "Já existe uma meta ativa desse tipo sobrepondo o período informado.",
            422,
        )
    db.add(
        Meta(
            loja_slug=usuario.loja_slug,
            escopo="loja",
            tipo=tipo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            valor_alvo=alvo,
            ativa=True,
        )
    )
    db.commit()
    return RedirectResponse("/app/metas?ok=criada", status_code=303)


@app.get("/app/metas/{meta_id}/editar", response_class=HTMLResponse)
def metas_editar_pagina(request: Request, meta_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_metas(usuario):
        return RedirectResponse("/app/metas", status_code=303)
    meta = db.query(Meta).filter(Meta.id == meta_id, Meta.loja_slug == usuario.loja_slug).first()
    if not meta or not meta.ativa:
        return RedirectResponse("/app/metas?erro=nao-encontrada", status_code=303)
    valores = {
        "tipo": meta.tipo,
        "periodo_inicio": meta.periodo_inicio.isoformat(),
        "periodo_fim": meta.periodo_fim.isoformat(),
        "valor_alvo": str(meta.valor_alvo),
    }
    return render_meta_form(request, usuario, valores, "Editar meta da loja")


@app.post("/app/metas/{meta_id}/editar")
async def metas_editar(request: Request, meta_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_metas(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/metas", status_code=303)
    meta = db.query(Meta).filter(Meta.id == meta_id, Meta.loja_slug == usuario.loja_slug).first()
    if not meta or not meta.ativa:
        return RedirectResponse("/app/metas?erro=nao-encontrada", status_code=303)
    valores = valores_meta_form(form)
    try:
        tipo, inicio, fim, alvo = validar_meta_form(form)
    except ValueError as exc:
        return render_meta_form(request, usuario, valores, "Editar meta da loja", str(exc), 422)
    if meta_sobreposta(db, usuario.loja_slug, tipo, inicio, fim, ignorar_id=meta.id):
        return render_meta_form(
            request,
            usuario,
            valores,
            "Editar meta da loja",
            "Já existe uma meta ativa desse tipo sobrepondo o período informado.",
            422,
        )
    meta.tipo = tipo
    meta.periodo_inicio = inicio
    meta.periodo_fim = fim
    meta.valor_alvo = alvo
    db.commit()
    return RedirectResponse("/app/metas?ok=editada", status_code=303)


@app.post("/app/metas/{meta_id}/desativar")
async def metas_desativar(request: Request, meta_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_metas(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/metas", status_code=303)
    meta = db.query(Meta).filter(Meta.id == meta_id, Meta.loja_slug == usuario.loja_slug).first()
    if not meta:
        return RedirectResponse("/app/metas?erro=nao-encontrada", status_code=303)
    meta.ativa = False
    db.commit()
    return RedirectResponse("/app/metas?ok=desativada", status_code=303)


@app.get("/app/financeiro", response_class=HTMLResponse)
def financeiro_dashboard(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_ver_financeiro(usuario):
        return RedirectResponse("/app", status_code=303)
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    confirmadas = [
        v
        for v in db.query(Venda).filter(Venda.loja_slug == usuario.loja_slug, Venda.status == "confirmada").all()
        if d_inicio <= _data(v.criada_em) <= d_fim
    ]
    faturamento = sum((v.preco_venda for v in confirmadas), Decimal("0"))
    lucros_conhecidos = [valor for venda in confirmadas if (valor := lucro_bruto_venda(venda)) is not None]
    lucro = sum(lucros_conhecidos, Decimal("0"))
    vendas_lucro_incompleto = len(confirmadas) - len(lucros_conhecidos)
    lucro_completo = vendas_lucro_incompleto == 0
    metricas = {
        "quantidade": len(confirmadas),
        "faturamento": faturamento,
        "lucro_bruto": lucro,
        "lucro_completo": lucro_completo,
        "vendas_lucro_incompleto": vendas_lucro_incompleto,
    }
    realizado_por_tipo = {"quantidade": Decimal(len(confirmadas)), "faturamento": faturamento, "lucro_bruto": lucro}
    metas_view = []
    for meta in db.query(Meta).filter(
        Meta.loja_slug == usuario.loja_slug,
        Meta.escopo == "loja",
        Meta.ativa.is_(True),
    ).all():
        if meta.tipo not in realizado_por_tipo or not (meta.periodo_inicio <= d_fim and meta.periodo_fim >= d_inicio):
            continue
        realizado = realizado_por_tipo[meta.tipo]
        indisponivel = meta.tipo == "lucro_bruto" and not lucro_completo
        pct = round(float(realizado / meta.valor_alvo * 100), 1) if meta.valor_alvo and not indisponivel else 0.0
        metas_view.append(
            {
                "tipo": meta.tipo,
                "alvo": meta.valor_alvo,
                "realizado": realizado,
                "pct": pct,
                "pct_barra": min(pct, 100),
                "quantidade": meta.tipo == "quantidade",
                "indisponivel": indisponivel,
            }
        )
    return templates.TemplateResponse(
        "financeiro/dashboard.html",
        contexto(
            request,
            usuario,
            metricas=metricas,
            metas=metas_view,
            tem_dados=bool(confirmadas),
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
        ),
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
