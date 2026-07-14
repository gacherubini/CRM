import calendar
import hashlib
import hmac
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
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
    pode_gerir_financeiras,
    pode_gerir_metas,
    pode_gerir_estoque,
    pode_gerir_trafego,
    pode_registrar_venda,
    pode_ver_custo,
    pode_ver_financeiro,
    usuario_atual,
)
from app.cripto import cifrar
from app.meta_capi import enfileirar_purchase_venda
from app.models import (
    AtendimentoAtribuicao,
    Meta,
    MetaPixelConfig,
    Usuario,
    Venda,
    VendaCustoDireto,
    agora,
)
from app.clients.chatbot import (
    ChatbotClient,
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    LeadNaoEncontrado,
    SimulacaoIndisponivel,
)
from app.clients.estoque import EstoqueClient, EstoqueIndisponivel
from app.clients.motor import CredencialNaoEncontrada, MotorClient, MotorIndisponivel
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


def identidade_telefone(telefone: str | None) -> str | None:
    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    if not digitos:
        return None
    mensagem = f"portal-handoff:v1:{digitos}".encode()
    return hmac.new(settings.identity_hmac_secret.encode(), mensagem, hashlib.sha256).hexdigest()


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


def get_motor_client() -> MotorClient:
    return MotorClient(settings.motor_url, settings.motor_token, settings.request_timeout)


# Aviso de senha antiga: portais lojistas costumam rotacionar a cada ~2 semanas.
DIAS_ALERTA_SENHA_ANTIGA = 14


def _parse_iso_dt(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _modo_provedor(meta: dict | None) -> str:
    """Modo do provedor quando o Motor expõe; senão mock/api a partir de ``real``."""
    if not meta:
        return "—"
    if meta.get("modo"):
        return str(meta["modo"])
    if "real" in meta:
        return "api" if meta.get("real") else "mock"
    return "—"


def enriquecer_credenciais(
    credenciais: list[dict], provedores: list[dict] | None = None
) -> list[dict]:
    """Junta máscara do Motor com metadados de provedor (modo) e flags de UI."""
    metas = {p.get("nome"): p for p in (provedores or []) if p.get("nome")}
    agora_utc = datetime.now()
    itens = []
    for raw in credenciais:
        item = dict(raw)
        # Defesa em profundidade: nunca repassar chave de senha em claro à UI.
        item.pop("senha", None)
        nome = item.get("provedor") or ""
        meta = metas.get(nome)
        item["modo"] = _modo_provedor(meta)
        atualizado = _parse_iso_dt(item.get("atualizado_em"))
        item["senha_antiga"] = False
        if atualizado is not None:
            # naive/aware: compara só o delta em dias
            ref = atualizado.replace(tzinfo=None) if atualizado.tzinfo else atualizado
            item["senha_antiga"] = (agora_utc - ref).days >= DIAS_ALERTA_SENHA_ANTIGA
        itens.append(item)
    return itens


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
        "placa": form.get("placa", "").strip() or None,
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


def registrar_handoff_local(db: Session, usuario: Usuario, telefone: str, assumir: bool) -> None:
    telefone_hmac = identidade_telefone(telefone)
    if not telefone_hmac:
        raise ValueError("telefone inválido")
    instante = agora()
    ativas = db.query(AtendimentoAtribuicao).filter(
        AtendimentoAtribuicao.loja_slug == usuario.loja_slug,
        AtendimentoAtribuicao.telefone_hmac == telefone_hmac,
        AtendimentoAtribuicao.ativa.is_(True),
    ).all()
    if assumir and len(ativas) == 1 and ativas[0].vendedor_email == usuario.email:
        return
    for atribuicao in ativas:
        atribuicao.ativa = False
        atribuicao.encerrada_em = instante
    if assumir:
        db.add(
            AtendimentoAtribuicao(
                loja_slug=usuario.loja_slug,
                telefone_hmac=telefone_hmac,
                vendedor_email=usuario.email,
                origem="handoff_portal",
                iniciada_em=instante,
                ativa=True,
            )
        )
    db.commit()


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
    registro_indisponivel = False
    try:
        registrar_handoff_local(db, usuario, telefone, assumir=acao == "assumir")
    except (SQLAlchemyError, ValueError):
        db.rollback()
        registro_indisponivel = True
    sufixo = "&registro=indisponivel" if registro_indisponivel else ""
    return RedirectResponse(f"{destino}?ok={acao}{sufixo}", status_code=303)


def pode_simular(usuario) -> bool:
    return usuario.papel in {"dono", "gerente", "vendedor", "admin_plataforma"}


# Campos que o vendedor pode ver na simulação. Whitelist é o padrão seguro:
# qualquer campo novo que um driver real devolva (custo, lucro, margem,
# spread, comissão, tokens do Motor, métricas financeiras) fica de fora por
# omissão, sem depender de manter uma lista de campos proibidos atualizada.
_SIMULACAO_CAMPOS_PUBLICOS = {"id", "status", "criada_em", "resultados", "mensagem"}
_SIMULACAO_RESULTADO_CAMPOS_PUBLICOS = {
    "provedor",
    "status",
    "valor_parcela",
    "taxa_am",
    "prazo_meses",
    "valor_financiado",
    "entrada",
    "codigo_erro",
}


def simulacao_sem_dados_sensiveis(resultado: dict) -> dict:
    """Remove dados sensíveis da simulação para papéis sem acesso financeiro.

    Devolve uma cópia contendo apenas os campos públicos (parcelas, taxa,
    prazo, valor financiado). Não muta o dicionário original — dono/gerente
    continuam recebendo a resposta completa.
    """
    if not isinstance(resultado, dict):
        return resultado
    limpo = {k: v for k, v in resultado.items() if k in _SIMULACAO_CAMPOS_PUBLICOS}
    resultados = limpo.get("resultados")
    if isinstance(resultados, list):
        limpo["resultados"] = [
            {k: v for k, v in item.items() if k in _SIMULACAO_RESULTADO_CAMPOS_PUBLICOS}
            if isinstance(item, dict)
            else item
            for item in resultados
        ]
    return limpo


UFS_BR = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


def _valores_form_simulacao(form) -> dict:
    return {
        "modo": form.get("modo") or "mock",
        "cpf": form.get("cpf") or "",
        "nascimento": form.get("nascimento", ""),
        "cnh": form.get("cnh") or "sim",
        "valor": form.get("valor", ""),
        "prazo_meses": form.get("prazo_meses", ""),
        "prazos_meses": form.get("prazos_meses", ""),
        "entrada": form.get("entrada", ""),
        "renda": form.get("renda", ""),
        "categoria": form.get("categoria", "moto"),
        "placa": (form.get("placa") or "").strip().upper(),
        "uf_licenciamento": form.get("uf_licenciamento") or "SP",
        "finalidade": form.get("finalidade") or "comum",
    }


def dados_simulacao(form) -> dict:
    """Payload legado para Chatbot mock (valor + prazo único)."""
    payload = {
        "cpf": "".join(c for c in (form.get("cpf") or "") if c.isdigit()),
        "nascimento": form.get("nascimento", "").strip(),
        "valor": float(str(form.get("valor")).replace(",", ".")),
        "prazo_meses": int(form.get("prazo_meses") or 48),
        "entrada": float(str(form.get("entrada") or 0).replace(",", ".")),
        "categoria": form.get("categoria") or "moto",
    }
    if form.get("renda"):
        payload["renda"] = float(str(form.get("renda")).replace(",", "."))
    return payload


def dados_simulacao_motor(form) -> dict:
    """Payload SolicitacaoSimulacao para o Motor (Santander real)."""
    cpf = "".join(c for c in (form.get("cpf") or "") if c.isdigit())
    nascimento = form.get("nascimento", "").strip()
    entrada = float(str(form.get("entrada") or 0).replace(",", "."))
    placa = (form.get("placa") or "").replace("-", "").strip().upper() or None
    valor_raw = (form.get("valor") or "").strip()
    valor = float(valor_raw.replace(",", ".")) if valor_raw else None
    if valor is None and not placa:
        raise ValueError("informe placa ou valor")
    prazos_txt = (form.get("prazos_meses") or "").strip()
    if prazos_txt:
        prazos = [int(p.strip()) for p in prazos_txt.split(",") if p.strip()]
    else:
        prazos = [int(form.get("prazo_meses") or 48)]
    cnh = (form.get("cnh") or "sim").lower() != "nao"
    return {
        "pessoa": {
            "cpf": cpf,
            "nascimento": nascimento,
            "cnh": cnh,
        },
        "veiculo": {
            "categoria": form.get("categoria") or "moto",
            "valor": valor,
            "placa": placa,
            "uf_licenciamento": form.get("uf_licenciamento") or "SP",
            "finalidade": form.get("finalidade") or "comum",
        },
        "condicoes": {"entrada": entrada, "prazos_meses": prazos},
        # Nome alinhado à lista do Motor / Acessos bancos ("Santander").
        "provedores": ["Santander"],
    }


@app.get("/app/simulacoes", response_class=HTMLResponse)
def simulacoes_pagina(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "simulacoes/form.html",
        contexto(request, usuario, valores={}, ufs=UFS_BR),
    )


@app.post("/app/simulacoes", response_class=HTMLResponse)
async def simulacoes_simular(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/simulacoes", status_code=303)
    valores = _valores_form_simulacao(form)
    modo = (form.get("modo") or "mock").strip().lower()

    # --- Santander real: cria job no Motor e mostra progresso ---
    if modo == "santander":
        try:
            payload_motor = dados_simulacao_motor(form)
        except (TypeError, ValueError):
            return templates.TemplateResponse(
                "simulacoes/form.html",
                contexto(
                    request,
                    usuario,
                    valores=valores,
                    ufs=UFS_BR,
                    erro="Confira CPF, nascimento, placa/valor, entrada e prazos.",
                ),
                status_code=422,
            )
        try:
            criada = motor.criar_simulacao(
                payload_motor, ator=usuario.email, idempotency_key=str(uuid.uuid4())
            )
        except MotorIndisponivel as exc:
            return templates.TemplateResponse(
                "simulacoes/form.html",
                contexto(
                    request,
                    usuario,
                    valores=valores,
                    ufs=UFS_BR,
                    erro=str(exc),
                ),
                status_code=503,
            )
        sim_id = criada.get("id")
        if not sim_id:
            return templates.TemplateResponse(
                "simulacoes/form.html",
                contexto(
                    request,
                    usuario,
                    valores=valores,
                    ufs=UFS_BR,
                    erro="Motor não devolveu id da simulação.",
                ),
                status_code=503,
            )
        # Guarda parâmetros na sessão para a tela de progresso/resultado
        jobs = request.session.get("sim_jobs") or {}
        jobs[sim_id] = {
            "valores": valores,
            "cpf": payload_motor["pessoa"]["cpf"],
            "criada_em": criada.get("criada_em") or "",
        }
        request.session["sim_jobs"] = jobs
        return RedirectResponse(f"/app/simulacoes/job/{sim_id}", status_code=303)

    # --- Mock legado: Portal → Chatbot ---
    try:
        payload = dados_simulacao(form)
    except (TypeError, ValueError):
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(
                request,
                usuario,
                valores=valores,
                ufs=UFS_BR,
                erro="Confira os valores informados e tente novamente.",
            ),
            status_code=422,
        )
    try:
        resultado = chatbot.simular(payload)
    except SimulacaoIndisponivel:
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(
                request,
                usuario,
                valores=valores,
                ufs=UFS_BR,
                erro="Simulação não habilitada nesta instalação.",
            ),
            status_code=409,
        )
    except ChatbotIndisponivel as exc:
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(request, usuario, valores=valores, ufs=UFS_BR, erro=str(exc)),
            status_code=503,
        )
    if not pode_ver_custo(usuario):
        resultado = simulacao_sem_dados_sensiveis(resultado)
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


# Estados do job no Motor (worker Playwright).
_SIM_STATUS_TERMINAIS = frozenset(
    {"concluida", "parcial", "falhou", "aguardando_intervencao", "cancelada"}
)

_SIM_STATUS_LABELS = {
    "recebida": "Na fila",
    "processando": "Processando no Santander",
    "concluida": "Concluída",
    "parcial": "Parcial (alguns prazos)",
    "falhou": "Falhou",
    "aguardando_intervencao": "Aguardando intervenção",
    "cancelada": "Cancelada",
}


def _passos_progresso_simulacao(status: str) -> list[dict]:
    """Etapas visíveis na tela de progresso (Santander real)."""
    ordem = ["recebida", "processando", "terminal"]
    terminal_ok = status in ("concluida", "parcial")
    terminal_fail = status in ("falhou", "cancelada", "aguardando_intervencao")
    idx = {
        "recebida": 0,
        "processando": 1,
    }.get(status, 2 if status in _SIM_STATUS_TERMINAIS else 0)

    def estado(passo_i: int) -> str:
        if passo_i < idx:
            return "done"
        if passo_i == idx:
            if passo_i == 2 and terminal_fail:
                return "fail"
            if passo_i == 2 and terminal_ok:
                return "done"
            return "active"
        return "pending"

    titulo_final = _SIM_STATUS_LABELS.get(status, "Finalizando")
    if status not in _SIM_STATUS_TERMINAIS:
        titulo_final = "Aguardando resultado"
    detalhe_final = {
        "concluida": "Parcelas lidas com sucesso no portal do Santander.",
        "parcial": "Parte dos prazos retornou; confira a tabela.",
        "falhou": "O Motor não conseguiu concluir. Veja o código de erro abaixo ou em Acessos bancos.",
        "aguardando_intervencao": "O portal pediu ação manual (captcha, 2FA, senha).",
        "cancelada": "Job cancelado.",
    }.get(status, "Quando o worker terminar, as parcelas aparecem automaticamente.")

    return [
        {
            "num": "01",
            "titulo": "Simulação enfileirada",
            "detalhe": "Pedido aceito pelo Motor e colocado na fila do worker.",
            "estado": estado(0),
        },
        {
            "num": "02",
            "titulo": "Consultando portal Santander",
            "detalhe": "Abrindo o portal lojista e lendo as parcelas (costuma levar 30–90s).",
            "estado": estado(1),
        },
        {
            "num": "03",
            "titulo": titulo_final,
            "detalhe": detalhe_final,
            "estado": estado(2),
        },
    ]


@app.get("/app/simulacoes/job/{sim_id}", response_class=HTMLResponse)
def simulacoes_job(
    sim_id: str,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    """Tela de progresso: mostra o status do job no Motor e atualiza sozinha."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)

    jobs = request.session.get("sim_jobs") or {}
    meta = jobs.get(sim_id) or {}
    valores = meta.get("valores") or {"modo": "santander"}
    cpf = meta.get("cpf") or ""

    try:
        resultado = motor.obter_simulacao(sim_id, ator=usuario.email)
    except MotorIndisponivel as exc:
        return templates.TemplateResponse(
            "simulacoes/progresso.html",
            contexto(
                request,
                usuario,
                sim_id=sim_id,
                status="erro_motor",
                status_label="Motor indisponível",
                passos=_passos_progresso_simulacao("recebida"),
                valores=valores,
                cpf_mascarado=mascarar_cpf(cpf),
                auto_refresh=True,
                refresh_segundos=5,
                erro=str(exc),
                resultados_parciais=[],
            ),
            status_code=503,
        )

    status = (resultado.get("status") or "recebida").lower()
    status_label = _SIM_STATUS_LABELS.get(status, status.replace("_", " "))

    if status in _SIM_STATUS_TERMINAIS:
        if not pode_ver_custo(usuario):
            resultado = simulacao_sem_dados_sensiveis(resultado)
        return templates.TemplateResponse(
            "simulacoes/resultado.html",
            contexto(
                request,
                usuario,
                valores=valores,
                resultado=resultado,
                cpf_mascarado=mascarar_cpf(cpf),
            ),
        )

    resultados = resultado.get("resultados") or []
    return templates.TemplateResponse(
        "simulacoes/progresso.html",
        contexto(
            request,
            usuario,
            sim_id=sim_id,
            status=status,
            status_label=status_label,
            passos=_passos_progresso_simulacao(status),
            valores=valores,
            cpf_mascarado=mascarar_cpf(cpf),
            auto_refresh=True,
            refresh_segundos=3,
            erro=None,
            resultados_parciais=resultados,
        ),
    )


@app.get("/app/simulacoes/historico", response_class=HTMLResponse)
def simulacoes_historico(
    request: Request,
    status: str | None = None,
    escopo: str | None = None,
    limite: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    """Histórico das simulações do usuário logado (ator/email).

    Escopo padrão = "minhas" (filtra por solicitado_por = email do usuário).
    Dono/gerente podem alternar para "toda a loja" (mesmo cliente Motor/tenant).
    A listagem não traz valores financeiros (o Motor projeta só campos não
    sensíveis), então não há o que esconder do vendedor aqui.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)

    pode_ver_loja = pode_ver_financeiro(usuario)
    ver_loja = escopo == "loja" and pode_ver_loja
    solicitado_por = None if ver_loja else usuario.email

    limite = max(1, min(int(limite or 20), 100))
    offset = max(0, int(offset or 0))
    status_filtro = status if status in _SIM_STATUS_LABELS else None

    itens, total, erro = [], 0, None
    try:
        dados = motor.listar_simulacoes(
            ator=usuario.email,
            status=status_filtro,
            solicitado_por=solicitado_por,
            limite=limite,
            offset=offset,
        )
        itens = dados.get("itens") or []
        total = dados.get("total") or 0
    except MotorIndisponivel as exc:
        erro = str(exc)

    return templates.TemplateResponse(
        "simulacoes/historico.html",
        contexto(
            request,
            usuario,
            itens=itens,
            total=total,
            limite=limite,
            offset=offset,
            escopo="loja" if ver_loja else "minhas",
            pode_ver_loja=pode_ver_loja,
            status_filtro=status_filtro or "",
            status_labels=_SIM_STATUS_LABELS,
            integracao_erro=erro,
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


def data_api(valor) -> date | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def origem_lead(lead: dict) -> str | None:
    origem = lead.get("origem")
    return str(origem).strip() if origem and str(origem).strip() else None


def lead_corresponde_origem(lead: dict, origem: str | None) -> bool:
    if not origem:
        return True
    atual = origem_lead(lead)
    if origem == "__sem_origem__":
        return atual is None
    return bool(atual and atual.casefold() == origem.casefold())


def atribuicoes_no_periodo(
    db: Session,
    loja_slug: str,
    inicio: date,
    fim: date,
    vendedor_email: str | None = None,
) -> list[AtendimentoAtribuicao]:
    consulta = db.query(AtendimentoAtribuicao).filter(
        AtendimentoAtribuicao.loja_slug == loja_slug
    )
    if vendedor_email:
        consulta = consulta.filter(AtendimentoAtribuicao.vendedor_email == vendedor_email)
    return [
        atribuicao
        for atribuicao in consulta.all()
        if inicio <= _data(atribuicao.iniciada_em) <= fim
    ]


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
    # E10: Purchase via CAPI — best-effort; falha não desfaz a venda.
    enfileirar_purchase_venda(db, venda)
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


@app.get("/app/vendedor", response_class=HTMLResponse)
def vendedor_dashboard(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel != "vendedor":
        destino = "/app/financeiro" if pode_ver_financeiro(usuario) else "/app"
        return RedirectResponse(destino, status_code=303)
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    vendas = [
        venda
        for venda in db.query(Venda).filter(
            Venda.loja_slug == usuario.loja_slug,
            Venda.vendedor_email == usuario.email,
        ).order_by(Venda.criada_em.desc()).all()
        if d_inicio <= _data(venda.criada_em) <= d_fim
    ]
    confirmadas = [venda for venda in vendas if venda.status == "confirmada"]
    faturamento = sum((venda.preco_venda for venda in confirmadas), Decimal("0"))
    realizado_por_tipo = {
        "quantidade": Decimal(len(confirmadas)),
        "faturamento": faturamento,
    }
    metas_view = []
    metas = db.query(Meta).filter(
        Meta.loja_slug == usuario.loja_slug,
        Meta.escopo == "vendedor",
        Meta.vendedor_email == usuario.email,
        Meta.ativa.is_(True),
    ).all()
    for meta in metas:
        if meta.tipo not in realizado_por_tipo or not (
            meta.periodo_inicio <= d_fim and meta.periodo_fim >= d_inicio
        ):
            continue
        realizado = realizado_por_tipo[meta.tipo]
        pct = round(float(realizado / meta.valor_alvo * 100), 1) if meta.valor_alvo else 0.0
        metas_view.append(
            {
                "tipo": meta.tipo,
                "alvo": meta.valor_alvo,
                "realizado": realizado,
                "pct": pct,
                "pct_barra": min(pct, 100),
                "quantidade": meta.tipo == "quantidade",
            }
        )

    atribuicoes = db.query(AtendimentoAtribuicao).filter(
        AtendimentoAtribuicao.loja_slug == usuario.loja_slug,
        AtendimentoAtribuicao.vendedor_email == usuario.email,
        AtendimentoAtribuicao.ativa.is_(True),
    ).all()
    hashes_atribuidos = {atribuicao.telefone_hmac for atribuicao in atribuicoes}
    leads_atribuidos, conversas_atribuidas = [], []
    erros_integracao = []
    try:
        leads = chatbot.listar_leads()
        leads_atribuidos = [
            lead
            for lead in leads
            if identidade_telefone(lead.get("telefone")) in hashes_atribuidos
        ]
    except ChatbotIndisponivel as exc:
        erros_integracao.append(str(exc))
    try:
        conversas = chatbot.listar_conversas(limit=200)
        conversas_atribuidas = [
            conversa
            for conversa in conversas
            if identidade_telefone(conversa.get("telefone")) in hashes_atribuidos
        ]
    except ChatbotIndisponivel as exc:
        erros_integracao.append(str(exc))

    return templates.TemplateResponse(
        "vendedor/dashboard.html",
        contexto(
            request,
            usuario,
            metricas={"quantidade": len(confirmadas), "faturamento": faturamento},
            metas=metas_view,
            vendas=vendas[:8],
            leads=leads_atribuidos,
            conversas=conversas_atribuidas,
            atribuicoes_registradas=len(atribuicoes),
            integracao_erro="; ".join(dict.fromkeys(erros_integracao)) or None,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
        ),
    )


@app.get("/app/financeiro", response_class=HTMLResponse)
def financeiro_dashboard(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    vendedor: str | None = None,
    origem: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
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

    vendedores = db.query(Usuario).filter(
        Usuario.loja_slug == usuario.loja_slug,
        Usuario.ativo.is_(True),
        Usuario.papel.in_(["dono", "gerente", "vendedor"]),
    ).order_by(Usuario.nome).all()
    vendedores_por_email = {item.email: item for item in vendedores}
    vendedor_filtro = vendedor if vendedor in vendedores_por_email else None
    origens = []
    funil = {
        "disponivel": False,
        "elegiveis": None,
        "atendidos": None,
        "vendas_vinculadas": None,
        "erro": None,
    }
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel as exc:
        funil["erro"] = str(exc)
    else:
        origens = sorted({valor for lead in leads if (valor := origem_lead(lead))}, key=str.casefold)
        candidatos = [lead for lead in leads if lead_corresponde_origem(lead, origem)]
        leads_sem_data = [lead for lead in candidatos if data_api(lead.get("criada_em")) is None]
        if leads_sem_data:
            funil["erro"] = (
                f"{len(leads_sem_data)} lead(s) sem data de criação confiável; "
                "as contagens do período estão indisponíveis."
            )
        else:
            elegiveis = [
                lead
                for lead in candidatos
                if d_inicio <= data_api(lead.get("criada_em")) <= d_fim
            ]
            atribuicoes_periodo = atribuicoes_no_periodo(
                db,
                usuario.loja_slug,
                d_inicio,
                d_fim,
                vendedor_email=vendedor_filtro,
            )
            hashes_atendidos = {item.telefone_hmac for item in atribuicoes_periodo}
            if vendedor_filtro:
                elegiveis = [
                    lead
                    for lead in elegiveis
                    if identidade_telefone(lead.get("telefone")) in hashes_atendidos
                ]
            ids_elegiveis = {str(lead.get("id")) for lead in elegiveis if lead.get("id")}
            atendidos = {
                str(lead.get("id"))
                for lead in elegiveis
                if lead.get("id") and identidade_telefone(lead.get("telefone")) in hashes_atendidos
            }
            vendas_vinculadas = [
                venda
                for venda in confirmadas
                if venda.lead_ref and venda.lead_ref in ids_elegiveis
                and (not vendedor_filtro or venda.vendedor_email == vendedor_filtro)
            ]
            funil.update(
                {
                    "disponivel": True,
                    "elegiveis": len(elegiveis),
                    "atendidos": len(atendidos),
                    "vendas_vinculadas": len(vendas_vinculadas),
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
            funil=funil,
            vendedores=vendedores,
            origens=origens,
            filtros_funil={"vendedor": vendedor_filtro or "", "origem": origem or ""},
        ),
    )


@app.get("/app/financeiras", response_class=HTMLResponse)
def financeiras_lista(
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_financeiras(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(
                request,
                usuario,
                erro="Você não tem permissão para gerenciar acessos das financeiras.",
            ),
            status_code=403,
        )

    credenciais: list[dict] = []
    integracao_erro = None
    motor_configurado = motor.configurado
    if not motor_configurado:
        integracao_erro = (
            "Integração com o Motor de Simulação desligada. "
            "Configure MOTOR_URL e MOTOR_TOKEN no servidor do Portal para "
            "gerenciar acessos dos portais bancários. Nenhuma senha é "
            "armazenada neste portal."
        )
    else:
        try:
            raw = motor.listar_credenciais(ator=usuario.email)
            try:
                provedores = motor.listar_provedores(ator=usuario.email)
            except MotorIndisponivel:
                provedores = []
            credenciais = enriquecer_credenciais(raw, provedores)
        except MotorIndisponivel as exc:
            integracao_erro = str(exc)

    return templates.TemplateResponse(
        "financeiras/lista.html",
        contexto(
            request,
            usuario,
            credenciais=credenciais,
            integracao_erro=integracao_erro,
            motor_configurado=motor_configurado,
            ok=request.query_params.get("ok"),
            teste=request.query_params.get("teste"),
            provedor_ok=request.query_params.get("provedor"),
            erro_query=request.query_params.get("erro"),
        ),
    )


@app.post("/app/financeiras/{nome}")
async def financeiras_upsert(
    nome: str,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_financeiras(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(
                request,
                usuario,
                erro="Você não tem permissão para gerenciar acessos das financeiras.",
            ),
            status_code=403,
        )

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/financeiras?erro=csrf", status_code=303)

    usuario_banco = (form.get("usuario") or "").strip()
    senha_banco = form.get("senha") or ""
    if not usuario_banco or not senha_banco:
        return RedirectResponse(
            f"/app/financeiras?erro=campos&provedor={nome}", status_code=303
        )

    if not motor.configurado:
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    try:
        # Senha só no BFF → Motor; não logar form/body.
        motor.upsert_credencial(
            nome=nome,
            usuario=usuario_banco,
            senha=senha_banco,
            ator=usuario.email,
        )
    except MotorIndisponivel:
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    return RedirectResponse(
        f"/app/financeiras?ok=salvo&provedor={nome}", status_code=303
    )


@app.post("/app/financeiras/{nome}/testar")
async def financeiras_testar(
    nome: str,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_financeiras(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(
                request,
                usuario,
                erro="Você não tem permissão para gerenciar acessos das financeiras.",
            ),
            status_code=403,
        )

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/financeiras?erro=csrf", status_code=303)

    if not motor.configurado:
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    try:
        resultado = motor.testar_login(nome, ator=usuario.email)
    except CredencialNaoEncontrada:
        return RedirectResponse(
            f"/app/financeiras?erro=sem_credencial&provedor={nome}", status_code=303
        )
    except MotorIndisponivel:
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    status_teste = resultado.get("status") or "ok"
    return RedirectResponse(
        f"/app/financeiras?teste={status_teste}&provedor={nome}", status_code=303
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


def _trafego_contexto(request: Request, usuario, config: MetaPixelConfig | None, *, ok=None, erro=None):
    token_configurado = bool(config and config.token_ciphertext)
    return contexto(
        request,
        usuario,
        config=config,
        token_configurado=token_configurado,
        pixel_id=(config.pixel_id if config else "") or "",
        test_event_code=(config.test_event_code if config else "") or "",
        enviar_page_view=bool(config.enviar_page_view) if config else True,
        enviar_lead=bool(config.enviar_lead) if config else True,
        enviar_purchase=bool(config.enviar_purchase) if config else True,
        atualizada_em=config.atualizada_em if config else None,
        ok=ok,
        erro=erro,
    )


@app.get("/app/trafego", response_class=HTMLResponse)
def trafego_pagina(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    ok = request.query_params.get("ok")
    return templates.TemplateResponse(
        "trafego/form.html",
        _trafego_contexto(request, usuario, config, ok=ok),
    )


@app.post("/app/trafego")
async def trafego_salvar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)

    pixel_id = (form.get("pixel_id") or "").strip()
    token_novo = (form.get("capi_token") or "").strip()
    test_event_code = (form.get("test_event_code") or "").strip() or None
    enviar_page_view = form.get("enviar_page_view") == "on"
    enviar_lead = form.get("enviar_lead") == "on"
    enviar_purchase = form.get("enviar_purchase") == "on"

    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    if not pixel_id:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                erro="Informe o Pixel ID da Meta.",
            ),
            status_code=422,
        )
    if not token_novo and not (config and config.token_ciphertext):
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                erro="Informe o token de acesso da Conversions API (CAPI).",
            ),
            status_code=422,
        )

    if config is None:
        config = MetaPixelConfig(loja_slug=usuario.loja_slug, pixel_id=pixel_id)
        db.add(config)

    config.pixel_id = pixel_id
    config.test_event_code = test_event_code
    config.enviar_page_view = enviar_page_view
    config.enviar_lead = enviar_lead
    config.enviar_purchase = enviar_purchase
    config.atualizada_em = agora()
    if token_novo:
        config.token_ciphertext = cifrar(token_novo)
    db.commit()
    return RedirectResponse("/app/trafego?ok=salvo", status_code=303)
