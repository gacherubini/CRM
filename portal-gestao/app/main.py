from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models, provisioning  # noqa: F401
from app.auth import (
    autenticar,
    csrf_token,
    csrf_valido,
    encerrar_sessao,
    hash_senha,
    iniciar_sessao,
    pode_confirmar_venda,
    pode_gerir_equipe,
    pode_gerir_financeiras,
    pode_gerir_metas,
    pode_gerir_estoque,
    pode_gerir_trafego,
    pode_registrar_venda,
    pode_ver_custo,
    pode_ver_financeiro,
    pode_ver_resultados_midia,
    usuario_atual,
)
from app.cripto import cifrar
from app.conversions import ConversionKind, PurchaseConversion, publish_conversion
from app.funil_eventos import (
    materializar_eventos_chatbot,
    registrar_evento,
    resumo_funil,
)
from app.meta_capi import processar_outbox_pendentes
from app.meta_pixel import normalizar_pixel_id
from app.models import (
    AtendimentoAtribuicao,
    Campanha,
    CampanhaGasto,
    Meta,
    MetaAdsConfig,
    MetaCapiOutbox,
    MetaPixelConfig,
    Usuario,
    Venda,
    VendaCustoDireto,
    agora,
    novo_id,
)
from app.meta_ads_spend import (
    normalizar_ad_account_id,
    sincronizar_gastos_meta,
)
from app import meta_ads_spend_job, meta_capi_job, revy_trafego_outbox_job
from app.revy_trafego_outbox import (
    enfileirar_venda_atualizada,
    enfileirar_venda_confirmada,
)
from app.campanhas import (
    CANAIS_ROTULO,
    STATUS_ROTULO,
    aplicar_snapshot_venda,
    campanha_por_utm,
    normalizar_utm,
    parse_brl_valor,
    parse_gastos_csv,
    payload_form as campanha_payload_form,
    preencher_campanha,
    salvar_gasto_manual,
    validar_campanha_payload,
)
from app.resultados_dono import (
    alertas_trafego,
    checklist_medicao,
    resumo_from_api,
    resumo_periodo,
)
from app.config import (
    revy_loja_entitlements_enabled,
    revy_loja_shell_enabled,
    settings,
)
from app.web.loja_shell import check_module_access, router as loja_shell_router
from app.web import loja_shell as loja_shell_mod
from app.loja.types import Module
from app.roi_calc import calcular_roi_loja, gerar_insights_roi, totais_roi, venda_casa_campanha
from app.clients.chatbot import (
    ChatbotClient,
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    LeadNaoEncontrado,
    SimulacaoIndisponivel,
)
from app.clients.estoque import (
    ConflitoEstoque,
    EstoqueClient,
    EstoqueIndisponivel,
    VeiculoNaoEncontrado,
)
from app.clients.motor import CredencialNaoEncontrada, MotorClient, MotorIndisponivel
from app.db import SessionLocal, get_db
from app.financeiro_calc import (
    FUSO_PORTAL,
    calcular_metricas_vendas,
    dinheiro,
    funil_periodo,
    identidade_telefone,
    lucro_bruto_venda,
    metas_view_periodo,
    periodo_padrao,
    ultimo_dia_mes,
    _data,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger(__name__)


def registrar_evento_funil_best_effort(
    db: Session,
    *,
    loja_slug: str,
    lead_ref: str | None,
    tipo: str,
    idempotency_key: str,
    ocorrido_em: datetime | None = None,
    ator_email: str | None = None,
    payload: dict | None = None,
) -> None:
    """Persiste telemetria comercial sem quebrar a operação principal."""
    if not lead_ref:
        return
    try:
        registrar_evento(
            db,
            loja_slug=loja_slug,
            lead_ref=lead_ref,
            tipo=tipo,
            idempotency_key=idempotency_key,
            ocorrido_em=ocorrido_em,
            ator_email=ator_email,
            payload=payload,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "funil: falha best-effort loja=%s tipo=%s erro=%s",
            loja_slug,
            tipo,
            type(exc).__name__,
        )


def sincronizar_funil_chatbot_best_effort(
    db: Session,
    *,
    loja_slug: str,
    chatbot: ChatbotClient,
) -> bool:
    """Busca a projeção sanitizada do Chatbot sem tornar o dashboard dependente dela."""
    try:
        tamanho_pagina = 500
        offset = 0
        while True:
            lote = chatbot.listar_eventos_funil(limit=tamanho_pagina, offset=offset)
            materializar_eventos_chatbot(db, loja_slug=loja_slug, eventos=lote)
            if len(lote) < tamanho_pagina:
                break
            # O contrato do Chatbot pagina leads, e cada lead projeta um ou dois
            # eventos. Portanto o cursor avança pelo tamanho solicitado da página,
            # não pela quantidade variável de eventos retornados.
            offset += tamanho_pagina
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning(
            "funil: sincronização Chatbot falhou loja=%s erro=%s",
            loja_slug,
            type(exc).__name__,
        )
        return False


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


def formatar_percentual(valor) -> str:
    if valor is None:
        return "Sem base"
    numero = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    casas = 0 if numero == numero.to_integral() else 2
    return f"{numero:.{casas}f}".replace(".", ",") + "%"


def formatar_duracao(segundos) -> str:
    if segundos is None:
        return "Sem base"
    total = max(0, int(segundos))
    if total < 60:
        return f"{total} s"
    minutos, resto_segundos = divmod(total, 60)
    if minutos < 60:
        return f"{minutos} min" if resto_segundos == 0 else f"{minutos} min {resto_segundos} s"
    horas, resto_minutos = divmod(minutos, 60)
    if horas < 24:
        return f"{horas} h" if resto_minutos == 0 else f"{horas} h {resto_minutos} min"
    dias, resto_horas = divmod(horas, 24)
    return f"{dias} d" if resto_horas == 0 else f"{dias} d {resto_horas} h"


templates.env.globals["mascarar_telefone"] = mascarar_telefone
templates.env.globals["formatar_horario"] = formatar_horario
templates.env.globals["mascarar_cpf"] = mascarar_cpf
templates.env.globals["formatar_brl"] = formatar_brl
templates.env.globals["formatar_percentual"] = formatar_percentual
templates.env.globals["formatar_duracao"] = formatar_duracao

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Em testes (PORTAL_SKIP_INIT / pytest) o job fica off via env no conftest.
    if os.getenv("PORTAL_SKIP_INIT") != "1":
        meta_ads_spend_job.start_worker(SessionLocal)
        meta_capi_job.start_worker(SessionLocal)
        revy_trafego_outbox_job.start_worker(
            SessionLocal,
            enabled=settings.revy_trafego_venda_events_enabled,
        )
    try:
        yield
    finally:
        meta_ads_spend_job.stop_worker()
        meta_capi_job.stop_worker()
        revy_trafego_outbox_job.stop_worker()


app = FastAPI(
    title="Portal de Gestão",
    docs_url=None,
    redoc_url=None,
    lifespan=_lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=settings.secure_cookie,
    same_site="lax",
    max_age=60 * 60 * 10,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(loja_shell_router)

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
    metas = {
        str(p.get("nome")).lower(): p
        for p in (provedores or [])
        if p.get("nome")
    }
    agora_utc = datetime.now()
    itens = []
    for raw in credenciais:
        item = dict(raw)
        # Defesa em profundidade: nunca repassar chave de senha em claro à UI.
        item.pop("senha", None)
        nome = item.get("provedor") or ""
        meta = metas.get(str(nome).lower())
        item["modo"] = _modo_provedor(meta)
        item["rotulo"] = (meta or {}).get("rotulo") or nome
        item["campos_credencial"] = (meta or {}).get("campos_credencial") or []
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


def contexto(request: Request, usuario=None, db: Session | None = None, **extra):
    ctx = {
        "request": request,
        "usuario": usuario,
        "csrf": csrf_token(request),
        "versao": settings.version,
        **extra,
    }
    # Shell Revy Loja (flag off → sem loja_nav; base.html mantém nav legado).
    if (
        revy_loja_shell_enabled()
        and usuario is not None
        and "loja_nav" not in extra
    ):
        session = db
        owned = False
        if session is None and revy_loja_entitlements_enabled():
            session = SessionLocal()
            owned = True
        try:
            if usuario is not None:
                loja_shell_mod.ensure_session_loja(request, usuario)
            ctx.update(loja_shell_mod.template_extras(request, usuario, session))
        finally:
            if owned and session is not None:
                session.close()
    return ctx


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1 FROM revy_trafego_event_outbox LIMIT 1"))
    return {
        "status": "ok",
        "estoque_configurado": bool(settings.estoque_token),
    }


@app.get("/public/v1/lojas/{loja_slug}/pixel")
def public_pixel_da_loja(loja_slug: str, db: Session = Depends(get_db)):
    """Pixel ID público da loja (browser do catálogo).

    Fonte da verdade do Portal → Tráfego. Não expõe token CAPI.
    O catálogo consulta este endpoint por loja (sem auth; ID é público).
    """
    slug = (loja_slug or "").strip()
    if not slug or len(slug) > 120:
        return JSONResponse(
            {
                "loja_slug": slug,
                "pixel_id": "",
                "enabled": False,
                "enviar_page_view": False,
                "enviar_lead": False,
            },
            status_code=404,
        )
    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == slug)
        .first()
    )
    # Nunca devolve conteúdo arbitrário salvo por engano no campo público.
    pixel_id = normalizar_pixel_id(config.pixel_id if config else None)
    return {
        "loja_slug": slug,
        "pixel_id": pixel_id,
        "enabled": bool(pixel_id),
        "enviar_page_view": bool(config.enviar_page_view) if config else True,
        "enviar_lead": bool(config.enviar_lead) if config else True,
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
    resultados: str | None = None,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
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
    resultados_view = None
    alertas_view = []
    onboarding = None
    periodo_resultados = None
    # Resultados de mídia: dono/gerente (leitura). Config técnica: só legacy / Revy Tráfego.
    if pode_ver_resultados_midia(usuario):
        from app.financeiro_calc import hoje_portal
        from app.clients.revy_trafego import RevyTrafegoClient

        hoje = hoje_portal()
        seletor = "mes" if resultados == "mes" else "7d"
        d_inicio = hoje.replace(day=1) if seletor == "mes" else hoje - timedelta(days=6)
        d_fim = hoje
        chatbot_offline = False
        linhas = []
        api_ok = False
        if settings.revy_trafego_resultados_enabled:
            api_payload = RevyTrafegoClient().fetch_resultados(
                loja_slug=usuario.loja_slug,
                periodo=seletor,
                modo="last",
            )
            if api_payload is not None:
                resultados_view = resumo_from_api(api_payload)
                periodo_api = api_payload.get("periodo") or {}
                chatbot_offline = bool(periodo_api.get("chatbot_offline"))
                api_ok = True
                try:
                    d_inicio = date.fromisoformat(periodo_api.get("inicio") or d_inicio.isoformat())
                    d_fim = date.fromisoformat(periodo_api.get("fim") or d_fim.isoformat())
                except ValueError:
                    pass
        if not api_ok:
            campanhas = db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
            gastos = db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all()
            vendas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)["confirmadas"]
            leads: list[dict] = []
            try:
                leads = chatbot.listar_leads()
            except ChatbotIndisponivel:
                chatbot_offline = True
            linhas = calcular_roi_loja(
                campanhas=campanhas,
                gastos=gastos,
                leads=leads,
                vendas_confirmadas=vendas,
                d_inicio=d_inicio,
                d_fim=d_fim,
                modo_atribuicao="last",
            )
            resultados_view = resumo_periodo(linhas)
        config_meta = db.query(MetaPixelConfig).filter(
            MetaPixelConfig.loja_slug == usuario.loja_slug
        ).first()
        outboxes = db.query(MetaCapiOutbox).filter(
            MetaCapiOutbox.loja_slug == usuario.loja_slug
        ).order_by(MetaCapiOutbox.criada_em.desc()).all()
        alertas_view = alertas_trafego(
            linhas=linhas if not api_ok else [],
            config=config_meta,
            ultimo_outbox=outboxes[0] if outboxes else None,
            chatbot_offline=chatbot_offline,
            modo_cliente=not pode_gerir_trafego(usuario),
        )
        # Checklist técnico de medição só na UI legacy (dono configurando no portal).
        if pode_gerir_trafego(usuario):
            campanhas_ob = db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
            gastos_ob = db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all()
            onboarding = checklist_medicao(
                config=config_meta,
                campanhas=campanhas_ob,
                gastos=gastos_ob,
                vendas=db.query(Venda).filter(Venda.loja_slug == usuario.loja_slug).all(),
                outboxes=outboxes,
            )
        periodo_resultados = {
            "inicio": d_inicio,
            "fim": d_fim,
            "seletor": seletor,
            "chatbot_offline": chatbot_offline,
            "api_indisponivel": settings.revy_trafego_resultados_enabled and not api_ok,
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
            pode_gerir_trafego=pode_gerir_trafego(usuario),
            pode_ver_resultados_midia=pode_ver_resultados_midia(usuario),
            resultados_view=resultados_view,
            alertas_trafego=alertas_view,
            onboarding_medicao=onboarding,
            periodo_resultados=periodo_resultados,
            canais=CANAIS_ROTULO,
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
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked
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
            db=db,
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
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked
    if not pode_gerir_estoque(usuario):
        return RedirectResponse("/app/estoque", status_code=303)
    return templates.TemplateResponse(
        "estoque/form.html",
        contexto(
            request,
            usuario,
            db=db,
            veiculo=None,
            titulo="Cadastrar veículo",
            pode_custo=True,
        ),
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


@app.get("/app/operacao/numeros", response_class=HTMLResponse)
def operacao_numeros(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in ("dono", "gerente"):
        return RedirectResponse("/app", status_code=303)
    numeros, erro = [], None
    grupo_config = {"selecionado": None, "grupos": [], "aviso": None}
    try:
        grupo_config = chatbot.obter_grupo_estoque()
        numeros = chatbot.listar_numeros_cadastro()
    except ChatbotIndisponivel as exc:
        erro = str(exc)
    return templates.TemplateResponse(
        "operacao/numeros.html",
        contexto(
            request,
            usuario,
            numeros=numeros,
            grupo_config=grupo_config,
            integracao_erro=erro,
        ),
    )


@app.post("/app/operacao/grupo")
async def operacao_grupo_salvar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if usuario.papel not in ("dono", "gerente") or not csrf_valido(
        request, form.get("csrf")
    ):
        return RedirectResponse("/app/operacao/numeros", status_code=303)
    grupo_jid = (form.get("grupo_jid") or "").strip()
    try:
        if grupo_jid:
            chatbot.definir_grupo_estoque(grupo_jid)
        else:
            chatbot.remover_grupo_estoque()
    except ChatbotIndisponivel:
        pass
    return RedirectResponse("/app/operacao/numeros", status_code=303)


@app.post("/app/operacao/numeros")
async def operacao_numeros_add(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if usuario.papel not in ("dono", "gerente") or not csrf_valido(
        request, form.get("csrf")
    ):
        return RedirectResponse("/app/operacao/numeros", status_code=303)
    telefone = (form.get("telefone") or "").strip()
    nome = (form.get("nome") or "").strip() or None
    if telefone:
        try:
            chatbot.adicionar_numero_cadastro(telefone, nome)
        except ChatbotIndisponivel:
            pass
    return RedirectResponse("/app/operacao/numeros", status_code=303)


@app.post("/app/operacao/numeros/remover")
async def operacao_numeros_remover(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if usuario.papel not in ("dono", "gerente") or not csrf_valido(
        request, form.get("csrf")
    ):
        return RedirectResponse("/app/operacao/numeros", status_code=303)
    telefone = (form.get("telefone") or "").strip()
    if telefone:
        try:
            chatbot.remover_numero_cadastro(telefone)
        except ChatbotIndisponivel:
            pass
    return RedirectResponse("/app/operacao/numeros", status_code=303)


@app.post("/app/estoque/novo")
async def estoque_criar(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked
    form = await request.form()
    if not pode_gerir_estoque(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/estoque", status_code=303)
    try:
        estoque.criar(dados_veiculo(form, pode_ver_custo(usuario)))
    except (EstoqueIndisponivel, ValueError) as exc:
        return templates.TemplateResponse(
            "estoque/form.html",
            contexto(request, usuario, db=db, veiculo=dict(form), titulo="Cadastrar veículo", erro=str(exc), pode_custo=pode_ver_custo(usuario)),
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
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked
    if not pode_gerir_estoque(usuario):
        return RedirectResponse("/app/estoque", status_code=303)
    try:
        veiculo = estoque.obter(veiculo_id)
    except VeiculoNaoEncontrado as exc:
        return templates.TemplateResponse(
            "erro.html", contexto(request, usuario, db=db, erro=str(exc)), status_code=404
        )
    except EstoqueIndisponivel as exc:
        return templates.TemplateResponse(
            "erro.html", contexto(request, usuario, db=db, erro=str(exc)), status_code=503
        )
    return templates.TemplateResponse(
        "estoque/form.html",
        contexto(request, usuario, db=db, veiculo=veiculo, titulo="Editar veículo", pode_custo=pode_ver_custo(usuario)),
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
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked
    form = await request.form()
    if not pode_gerir_estoque(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/estoque", status_code=303)
    try:
        estoque.atualizar(veiculo_id, dados_veiculo(form, pode_ver_custo(usuario)))
    except (EstoqueIndisponivel, ValueError) as exc:
        return templates.TemplateResponse(
            "estoque/form.html",
            contexto(request, usuario, db=db, veiculo={**dict(form), "id": veiculo_id}, titulo="Editar veículo", erro=str(exc), pode_custo=pode_ver_custo(usuario)),
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
    blocked = check_module_access(request, usuario, db, Module.ESTOQUE)
    if blocked is not None:
        return blocked
    form = await request.form()
    if not pode_gerir_estoque(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/estoque", status_code=303)
    if acao not in {"publicar", "despublicar", "reservar", "vender"}:
        return RedirectResponse("/app/estoque?erro=acao", status_code=303)
    try:
        estoque.acao(veiculo_id, acao)
    except (ConflitoEstoque, EstoqueIndisponivel, VeiculoNaoEncontrado, ValueError):
        return RedirectResponse("/app/estoque?erro=acao", status_code=303)
    return RedirectResponse(f"/app/estoque?ok={acao}", status_code=303)


ETAPAS_LEAD = {
    "novo": "Novo",
    "em_atendimento": "Em atendimento",
    "qualificado": "Qualificado",
    "convertido": "Convertido",
    "perdido": "Perdido",
}


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
        contexto(
            request,
            usuario,
            lead=lead,
            etapas=ETAPAS_LEAD,
            pode_atualizar_etapa=usuario.papel
            in {"dono", "gerente", "vendedor", "admin_plataforma"},
        ),
    )


@app.post("/app/leads/{lead_id}/etapa")
async def leads_atualizar_etapa(
    request: Request,
    lead_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if usuario.papel not in {"dono", "gerente", "vendedor", "admin_plataforma"}:
        return RedirectResponse("/app/leads", status_code=303)
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(
            f"/app/leads/{lead_id}?erro=sessao", status_code=303
        )
    etapa = (form.get("etapa") or "").strip()
    if etapa not in ETAPAS_LEAD:
        return RedirectResponse(
            f"/app/leads/{lead_id}?erro=etapa", status_code=303
        )
    try:
        lead_atualizado = chatbot.atualizar_etapa_lead(lead_id, etapa)
    except LeadNaoEncontrado:
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Lead não encontrado."),
            status_code=404,
        )
    except ChatbotIndisponivel:
        return RedirectResponse(
            f"/app/leads/{lead_id}?erro=integracao", status_code=303
        )
    evento_origem = str(lead_atualizado.get("atualizada_em") or uuid.uuid4())
    registrar_evento_funil_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        lead_ref=lead_id,
        tipo="etapa_manual",
        idempotency_key=f"portal:lead:{lead_id}:etapa:{evento_origem}",
        ator_email=usuario.email,
        payload={"etapa_nova": etapa},
    )
    if etapa == "perdido":
        registrar_evento_funil_best_effort(
            db,
            loja_slug=usuario.loja_slug,
            lead_ref=lead_id,
            tipo="perda",
            idempotency_key=f"portal:lead:{lead_id}:perda:{evento_origem}",
            ator_email=usuario.email,
            payload={"status": "perdido"},
        )
    return RedirectResponse(
        f"/app/leads/{lead_id}?ok=etapa-atualizada", status_code=303
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
_SIMULACAO_CAMPOS_PUBLICOS = {
    "id",
    "status",
    "criada_em",
    "resultados",
    "mensagem",
    "provedores",
    "tarefas",
    "placa",
    "prazos_meses",
}
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


# Bancos reais do Motor; "todos" consulta os que tiverem credencial.
_PROVEDORES_REAIS = frozenset({"santander", "pan", "fontecred", "bradesco"})
_ROTULOS_BANCO = {
    "santander": "Santander",
    "pan": "Banco PAN",
    "fontecred": "Fontecred",
    "bradesco": "Bradesco",
}


def _parse_celular_form(raw: str | None) -> tuple[str | None, str | None]:
    """Extrai (ddd, celular) de um campo livre com DDD.

    Aceita 10/11 dígitos (com DDD) ou 12/13 com prefixo 55.
    Devolve celular sem DDD (8–9 dígitos) e ddd com 2 dígitos.
    """
    digitos = "".join(c for c in (raw or "") if c.isdigit())
    if digitos.startswith("55") and len(digitos) >= 12:
        digitos = digitos[2:]
    if len(digitos) in (10, 11):
        return digitos[:2], digitos[2:]
    return None, None


def _lista_form(form, nome: str) -> list[str]:
    """Lê campo multi-valor do form (checkboxes) de forma compatível com testes."""
    if hasattr(form, "getlist"):
        vals = form.getlist(nome)
    else:
        vals = form.get(nome)
    if vals is None:
        return []
    if isinstance(vals, (str, bytes)):
        return [str(vals)]
    return [str(v) for v in vals if v is not None and str(v).strip()]


def _valores_form_simulacao(form) -> dict:
    provedores = [
        p.strip().lower()
        for p in _lista_form(form, "provedores")
        if p and str(p).strip()
    ]
    return {
        "modo": "selecionados" if provedores else "todos",
        "provedores": provedores,
        "cpf": form.get("cpf") or "",
        "nascimento": form.get("nascimento", ""),
        "celular": form.get("celular") or "",
        "cnh": form.get("cnh") or "sim",
        "valor": form.get("valor", ""),
        "prazos_meses": form.get("prazos_meses", ""),
        "entrada": form.get("entrada", ""),
        "categoria": form.get("categoria", "moto"),
        "placa": (form.get("placa") or "").strip().upper(),
        "uf_licenciamento": form.get("uf_licenciamento") or "SP",
        "finalidade": form.get("finalidade") or "comum",
        "zero_km": form.get("zero_km") or "nao",
    }


def _credenciais_prontas_motor(motor: "MotorClient", ator: str | None) -> list[dict]:
    """Bancos com login configurado e habilitado (máscara do Motor)."""
    try:
        raw = motor.listar_credenciais(ator=ator)
        provedores = motor.listar_provedores(ator=ator)
    except MotorIndisponivel:
        return []
    itens = enriquecer_credenciais(raw, provedores)
    return [
        c
        for c in itens
        if c.get("senha_configurada") and c.get("habilitado")
    ]


def _provedores_da_simulacao(
    form, credenciais_prontas: list[dict]
) -> list[str]:
    """Bancos escolhidos no form ∩ credencial pronta.

    Se o form não mandar ``provedores``, mantém o comportamento antigo
    (todos os prontos) para compatibilidade com clientes/testes legados.
    """
    prontos: list[str] = []
    vistos: set[str] = set()
    for c in credenciais_prontas:
        nome = (c.get("provedor") or "").strip().lower()
        if nome and nome not in vistos:
            vistos.add(nome)
            prontos.append(nome)

    escolhidos = {
        p.strip().lower()
        for p in _lista_form(form, "provedores")
        if p and str(p).strip()
    }
    if not escolhidos:
        return prontos
    return [p for p in prontos if p in escolhidos]


def dados_simulacao_motor(
    form, provedores: list[str] | str | None = None
) -> dict:
    """Payload SolicitacaoSimulacao para um ou mais provedores reais do Motor."""
    if isinstance(provedores, str):
        lista = [provedores]
    elif provedores:
        lista = list(provedores)
    else:
        lista = ["santander"]
    lista = [p.strip().lower() for p in lista if p and str(p).strip()]
    if not lista:
        raise ValueError("informe ao menos um provedor")
    cpf = "".join(c for c in (form.get("cpf") or "") if c.isdigit())
    nascimento = form.get("nascimento", "").strip()
    ddd, celular = _parse_celular_form(form.get("celular"))
    if not ddd or not celular:
        raise ValueError("informe celular com DDD (10 ou 11 dígitos)")
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
        prazos = [24, 36, 48]
    cnh = (form.get("cnh") or "sim").lower() != "nao"
    # Portais (Fontecred/Bradesco/PAN) costumam mascarar DDD+número no mesmo campo.
    # APIs (PAN) usam ddd e celular separados — enviamos os dois formatos úteis.
    celular_completo = f"{ddd}{celular}"
    return {
        "pessoa": {
            "cpf": cpf,
            "nascimento": nascimento,
            "cnh": cnh,
            "ddd": ddd,
            "celular": celular_completo,
        },
        "veiculo": {
            "categoria": form.get("categoria") or "moto",
            "valor": valor,
            "placa": placa,
            "uf_licenciamento": form.get("uf_licenciamento") or "SP",
            "finalidade": form.get("finalidade") or "comum",
            "zero_km": (form.get("zero_km") or "nao").lower() == "sim",
        },
        "condicoes": {"entrada": entrada, "prazos_meses": prazos},
        "provedores": lista,
    }


@app.get("/app/simulacoes", response_class=HTMLResponse)
def simulacoes_pagina(
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    bancos_prontos = _credenciais_prontas_motor(motor, usuario.email)
    return templates.TemplateResponse(
        "simulacoes/form.html",
        contexto(
            request,
            usuario,
            valores={"modo": "todos"},
            ufs=UFS_BR,
            bancos_prontos=bancos_prontos,
        ),
    )


@app.post("/app/simulacoes", response_class=HTMLResponse)
async def simulacoes_simular(
    request: Request,
    db: Session = Depends(get_db),
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
    bancos_prontos = _credenciais_prontas_motor(motor, usuario.email)

    def _rerender(erro: str, status: int = 422):
        return templates.TemplateResponse(
            "simulacoes/form.html",
            contexto(
                request,
                usuario,
                valores=valores,
                ufs=UFS_BR,
                bancos_prontos=bancos_prontos,
                erro=erro,
            ),
            status_code=status,
        )

    provedores = _provedores_da_simulacao(form, bancos_prontos)
    if not bancos_prontos:
        return _rerender(
            "Nenhum banco com acesso configurado. Cadastre login em "
            "Acessos dos bancos e tente de novo."
        )
    if not provedores:
        return _rerender(
            "Selecione ao menos um banco com acesso configurado para simular."
        )
    try:
        payload_motor = dados_simulacao_motor(form, provedores)
    except (TypeError, ValueError):
        return _rerender(
            "Confira CPF, nascimento, celular (DDD+número), placa/valor, entrada e prazos."
        )
    try:
        criada = motor.criar_simulacao(
            payload_motor, ator=usuario.email, idempotency_key=str(uuid.uuid4())
        )
    except MotorIndisponivel as exc:
        return _rerender(str(exc), status=503)
    sim_id = criada.get("id")
    if not sim_id:
        return _rerender("Motor não devolveu id da simulação.", status=503)
    valores_job = dict(valores)
    valores_job["modo"] = "selecionados" if len(provedores) == 1 else "multi"
    valores_job["provedores"] = list(provedores)
    jobs = request.session.get("sim_jobs") or {}
    jobs[sim_id] = {
        "valores": valores_job,
        "cpf": payload_motor["pessoa"]["cpf"],
        "criada_em": criada.get("criada_em") or "",
        "provedores": list(provedores),
    }
    request.session["sim_jobs"] = jobs
    return RedirectResponse(f"/app/simulacoes/job/{sim_id}", status_code=303)


# Estados do job no Motor (worker Playwright).
_SIM_STATUS_TERMINAIS = frozenset(
    {"concluida", "parcial", "falhou", "aguardando_intervencao", "cancelada"}
)

_SIM_STATUS_LABELS = {
    "recebida": "Na fila",
    "processando": "Processando no banco",
    "concluida": "Concluída",
    "parcial": "Parcial (alguns prazos)",
    "falhou": "Falhou",
    "aguardando_intervencao": "Aguardando intervenção",
    "cancelada": "Cancelada",
}


def _cards_bancos_progresso(
    provedores: list[str],
    resultados: list[dict] | None,
    tarefas: list[dict] | None,
    status_job: str,
) -> list[dict]:
    """Um card por banco com estado derivado de tarefas e resultados parciais."""
    resultados = resultados or []
    tarefas = tarefas or []
    por_tarefa = {
        (t.get("provedor") or "").lower(): t for t in tarefas if t.get("provedor")
    }
    por_resultado: dict[str, list[dict]] = {}
    for r in resultados:
        chave = (r.get("provedor") or "").lower()
        por_resultado.setdefault(chave, []).append(r)

    cards = []
    for nome in provedores:
        chave = (nome or "").lower()
        rotulo = _ROTULOS_BANCO.get(chave, nome or "Banco")
        tarefa = por_tarefa.get(chave)
        linhas = por_resultado.get(chave) or []
        # Resultados de mock usam nomes capitalizados; se só há um provedor na lista, usa todos.
        if not linhas and len(provedores) == 1:
            linhas = list(resultados)

        if tarefa and tarefa.get("status"):
            st = (tarefa.get("status") or "").lower()
        elif linhas:
            if any(r.get("status") == "concluida" for r in linhas):
                st = "concluida"
            elif any(r.get("codigo_erro") for r in linhas):
                st = "falhou"
            else:
                st = (linhas[0].get("status") or "processando").lower()
        elif status_job in _SIM_STATUS_TERMINAIS:
            st = "falhou"
        elif status_job == "processando":
            st = "processando"
        else:
            st = "recebida"

        ofertas_ok = sum(1 for r in linhas if r.get("status") == "concluida")
        parcela_exemplo = next(
            (
                r.get("valor_parcela")
                for r in linhas
                if r.get("status") == "concluida" and r.get("valor_parcela") is not None
            ),
            None,
        )
        label_status = {
            "recebida": "Na fila",
            "acordando_worker": "Acordando worker",
            "reservada": "Reservada",
            "processando": "Consultando",
            "concluida": "Com oferta" if ofertas_ok else "Concluída",
            "parcial": "Parcial",
            "falhou": "Falhou",
            "rejeitada": "Rejeitada",
            "cancelada": "Cancelada",
        }.get(st, st.replace("_", " "))
        cards.append(
            {
                "provedor": chave,
                "rotulo": rotulo,
                "status": st,
                "status_label": label_status,
                "ofertas": ofertas_ok,
                "parcela_exemplo": parcela_exemplo,
                "codigo_erro": (tarefa or {}).get("codigo_erro")
                or next((r.get("codigo_erro") for r in linhas if r.get("codigo_erro")), None),
            }
        )
    return cards


def _passos_progresso_simulacao(
    status: str, provedor: str = "santander"
) -> list[dict]:
    """Etapas visíveis na tela de progresso de um provedor real."""
    rotulo = _ROTULOS_BANCO.get(provedor, provedor.title() if provedor else "Banco")
    if provedor == "todos":
        rotulo = "bancos configurados"
    modo = "portal lojista"
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
        "concluida": f"Parcelas recebidas com sucesso do {rotulo}.",
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
            "titulo": f"Consultando {rotulo}",
            "detalhe": f"Conectando pela {modo} e aguardando as condições de financiamento.",
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
    valores = meta.get("valores") or {"modo": "todos"}
    provedores = list(
        meta.get("provedores")
        or valores.get("provedores")
        or (
            [valores["modo"]]
            if valores.get("modo") in _PROVEDORES_REAIS
            else []
        )
    )
    provedor_passo = (
        "todos"
        if len(provedores) != 1
        else (provedores[0] if provedores else "santander")
    )
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
                passos=_passos_progresso_simulacao("recebida", provedor_passo),
                valores=valores,
                cpf_mascarado=mascarar_cpf(cpf),
                auto_refresh=True,
                refresh_segundos=5,
                erro=str(exc),
                resultados_parciais=[],
                cards_bancos=_cards_bancos_progresso(
                    provedores, [], [], "erro_motor"
                ),
            ),
            status_code=503,
        )

    status = (resultado.get("status") or "recebida").lower()
    status_label = _SIM_STATUS_LABELS.get(status, status.replace("_", " "))
    if not provedores:
        provedores = list(resultado.get("provedores") or [])

    if status in _SIM_STATUS_TERMINAIS:
        if not pode_ver_custo(usuario):
            resultado = simulacao_sem_dados_sensiveis(resultado)
        # Histórico sem sessão: completa parâmetros a partir do job no Motor.
        if not valores.get("placa") and resultado.get("placa"):
            valores = {**valores, "placa": resultado.get("placa")}
        if not valores.get("prazos_meses") and resultado.get("prazos_meses"):
            valores = {**valores, "prazos_meses": resultado.get("prazos_meses")}
        if not valores.get("provedores") and resultado.get("provedores"):
            valores = {**valores, "provedores": resultado.get("provedores")}
        resultados_lista = resultado.get("resultados") or []
        return templates.TemplateResponse(
            "simulacoes/resultado.html",
            contexto(
                request,
                usuario,
                valores=valores,
                resultado=resultado,
                grupos_resultados=_grupos_resultados_por_banco(resultados_lista),
                cpf_mascarado=mascarar_cpf(cpf),
            ),
        )

    resultados = resultado.get("resultados") or []
    tarefas = resultado.get("tarefas") or []
    return templates.TemplateResponse(
        "simulacoes/progresso.html",
        contexto(
            request,
            usuario,
            sim_id=sim_id,
            status=status,
            status_label=status_label,
            passos=_passos_progresso_simulacao(status, provedor_passo),
            valores=valores,
            cpf_mascarado=mascarar_cpf(cpf),
            auto_refresh=True,
            refresh_segundos=3,
            erro=None,
            resultados_parciais=resultados,
            cards_bancos=_cards_bancos_progresso(
                provedores, resultados, tarefas, status
            ),
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


def _grupos_eventos_por_banco(eventos: list[dict]) -> list[dict]:
    """Agrupa timeline por provedor (fan-out multi-banco). Ordem = primeira aparição."""
    ordem: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for ev in eventos or []:
        chave = (ev.get("provedor") or "").strip().lower() or "geral"
        if chave not in buckets:
            ordem.append(chave)
            buckets[chave] = []
        buckets[chave].append(ev)
    grupos = []
    for chave in ordem:
        rotulo = (
            "Geral"
            if chave == "geral"
            else _ROTULOS_BANCO.get(chave, chave.replace("_", " ").title())
        )
        grupos.append({"provedor": chave, "rotulo": rotulo, "eventos": buckets[chave]})
    return grupos


def _grupos_resultados_por_banco(resultados: list[dict] | None) -> list[dict]:
    """Agrupa ofertas por provedor para a tela de resultado multi-banco."""
    ordem: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for r in resultados or []:
        if not isinstance(r, dict):
            continue
        chave = (r.get("provedor") or "banco").strip().lower() or "banco"
        if chave not in buckets:
            ordem.append(chave)
            buckets[chave] = []
        buckets[chave].append(r)
    grupos = []
    for chave in ordem:
        linhas = buckets[chave]
        ofertas_ok = sum(
            1
            for r in linhas
            if (r.get("status") or "").lower() == "concluida"
            and r.get("valor_parcela") is not None
        )
        codigo_erro = next(
            (r.get("codigo_erro") for r in linhas if r.get("codigo_erro")),
            None,
        )
        grupos.append(
            {
                "provedor": chave,
                "rotulo": _ROTULOS_BANCO.get(chave, chave.replace("_", " ").title()),
                "linhas": linhas,
                "ofertas_ok": ofertas_ok,
                "codigo_erro": codigo_erro,
            }
        )
    return grupos


@app.get("/app/simulacoes/{sim_id}/registros", response_class=HTMLResponse)
def simulacoes_registros(
    sim_id: str,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_simular(usuario):
        return RedirectResponse("/app", status_code=303)
    erro = None
    dados = {"status": "desconhecido", "eventos": []}
    try:
        dados = motor.listar_eventos(sim_id, ator=usuario.email)
    except MotorIndisponivel as exc:
        erro = str(exc)
    status = str(dados.get("status") or "desconhecido").lower()
    eventos = dados.get("eventos") or []
    return templates.TemplateResponse(
        "simulacoes/registros.html",
        contexto(
            request,
            usuario,
            sim_id=sim_id,
            status=status,
            status_label=_SIM_STATUS_LABELS.get(status, status.replace("_", " ")),
            eventos=eventos,
            grupos_eventos=_grupos_eventos_por_banco(eventos),
            pode_ver_print=pode_gerir_financeiras(usuario),
            auto_refresh=status not in _SIM_STATUS_TERMINAIS,
            erro=erro,
        ),
    )


@app.get("/app/simulacoes/{sim_id}/registros/{evento_id}/print")
def simulacoes_registro_print(
    sim_id: str,
    evento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    motor: MotorClient = Depends(get_motor_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    # Prints podem conter CPF/placa: vendedor vê a timeline, mas não a imagem.
    if not pode_gerir_financeiras(usuario):
        return Response(status_code=403)
    try:
        conteudo, tipo = motor.obter_print_evento(sim_id, evento_id, ator=usuario.email)
    except MotorIndisponivel:
        return Response(status_code=404)
    return Response(
        content=conteudo,
        media_type=tipo,
        headers={"Cache-Control": "private, no-store, max-age=0"},
    )


CATEGORIAS_CUSTO = ["documentacao", "frete", "comissao", "outros"]
STATUS_VENDA = ["registrada", "confirmada", "cancelada"]
TIPOS_META = {
    "quantidade": "Quantidade de vendas",
    "faturamento": "Faturamento",
    "lucro_bruto": "Lucro bruto",
}
# dinheiro, _data, ultimo_dia_mes, periodo_padrao, data_api, origem_lead,
# lead_corresponde_origem, atribuicoes_no_periodo, lucro_bruto_venda e CENTAVOS
# vivem em app.financeiro_calc (importados no topo deste arquivo) para serem
# compartilhados com app.relatorios sem duplicar a matemática financeira.


def _carregar_opcoes_venda(
    chatbot: ChatbotClient, estoque: EstoqueClient
) -> tuple[list[dict] | None, list[dict] | None, list[str]]:
    """Carrega cada integração isoladamente para o formulário continuar utilizável."""
    avisos: list[str] = []
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel:
        leads = None
        avisos.append("Leads indisponíveis; a referência manual será validada na confirmação.")
    try:
        veiculos = [
            veiculo
            for veiculo in estoque.listar()
            if veiculo.get("status") in {"disponivel", "reservado"}
        ]
    except EstoqueIndisponivel:
        veiculos = None
        avisos.append("Estoque indisponível; a referência manual será validada na confirmação.")
    return leads, veiculos, avisos


def _render_venda_form(
    request: Request,
    usuario: Usuario,
    chatbot: ChatbotClient,
    estoque: EstoqueClient,
    *,
    valores: dict | None = None,
    erro: str | None = None,
    status_code: int = 200,
):
    leads, veiculos, avisos = _carregar_opcoes_venda(chatbot, estoque)
    return templates.TemplateResponse(
        "vendas/form.html",
        contexto(
            request,
            usuario,
            valores=valores or {},
            categorias=CATEGORIAS_CUSTO,
            pode_financeiro=pode_ver_financeiro(usuario),
            leads=leads,
            veiculos=veiculos,
            integracoes_avisos=avisos,
            erro=erro,
        ),
        status_code=status_code,
    )


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
def vendas_nova(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_registrar_venda(usuario):
        return RedirectResponse("/app/vendas", status_code=303)
    return _render_venda_form(request, usuario, chatbot, estoque)


@app.post("/app/vendas/nova")
async def vendas_criar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_registrar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/vendas", status_code=303)
    if not provisioning.allows_processing(db, usuario.loja_slug):
        return RedirectResponse(
            "/app/vendas?erro=loja-nao-operacional", status_code=303
        )
    # Com entitlements on, módulo Vendas suspenso também bloqueia novo registro.
    blocked = check_module_access(request, usuario, db, Module.VENDAS)
    if blocked is not None:
        return blocked
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
        return _render_venda_form(
            request,
            usuario,
            chatbot,
            estoque,
            valores=valores,
            erro="Informe descrição e preço de venda válidos.",
            status_code=422,
        )
    lead_ref = (form.get("lead_ref") or "").strip() or None
    veiculo_ref = (form.get("veiculo_ref") or "").strip() or None
    referencias_pendentes = False
    if lead_ref:
        try:
            chatbot.obter_lead(lead_ref)
        except LeadNaoEncontrado:
            return _render_venda_form(
                request,
                usuario,
                chatbot,
                estoque,
                valores=valores,
                erro="O lead selecionado não existe nesta loja.",
                status_code=422,
            )
        except ChatbotIndisponivel:
            referencias_pendentes = True
    if veiculo_ref:
        try:
            veiculo = estoque.obter(veiculo_ref)
            if veiculo.get("status") not in {"disponivel", "reservado"}:
                return _render_venda_form(
                    request,
                    usuario,
                    chatbot,
                    estoque,
                    valores=valores,
                    erro="O veículo selecionado não está disponível para venda.",
                    status_code=422,
                )
        except VeiculoNaoEncontrado:
            return _render_venda_form(
                request,
                usuario,
                chatbot,
                estoque,
                valores=valores,
                erro="O veículo selecionado não existe nesta loja.",
                status_code=422,
            )
        except EstoqueIndisponivel:
            referencias_pendentes = True
    venda = Venda(
        loja_slug=usuario.loja_slug,
        vendedor_email=usuario.email,
        descricao=descricao,
        preco_venda=preco,
        lead_ref=lead_ref,
        veiculo_ref=veiculo_ref,
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
    registrar_evento_funil_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        lead_ref=venda.lead_ref,
        tipo="venda_registrada",
        idempotency_key=f"portal:venda:{venda.id}:registrada",
        ocorrido_em=venda.criada_em,
        ator_email=usuario.email,
        payload={"venda_id": venda.id, "status": "registrada"},
    )
    sufixo = "&aviso=referencias-pendentes" if referencias_pendentes else ""
    return RedirectResponse(f"/app/vendas?ok=registrada{sufixo}", status_code=303)


@app.post("/app/vendas/{venda_id}/confirmar")
async def vendas_confirmar(
    request: Request,
    venda_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_confirmar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/vendas", status_code=303)
    if not provisioning.allows_processing(db, usuario.loja_slug):
        return RedirectResponse(
            "/app/vendas?erro=loja-nao-operacional", status_code=303
        )
    venda = db.query(Venda).filter(Venda.id == venda_id, Venda.loja_slug == usuario.loja_slug).first()
    if not venda or venda.status == "cancelada":
        return RedirectResponse("/app/vendas?erro=acao", status_code=303)
    if venda.status == "confirmada":
        return RedirectResponse("/app/vendas?ok=ja-confirmada", status_code=303)
    lead = None
    if venda.lead_ref:
        try:
            lead = chatbot.obter_lead(venda.lead_ref)
        except LeadNaoEncontrado:
            return RedirectResponse("/app/vendas?erro=lead", status_code=303)
        except ChatbotIndisponivel:
            return RedirectResponse(
                "/app/vendas?erro=chatbot-indisponivel", status_code=303
            )
    estoque_baixado = False
    if venda.veiculo_ref:
        try:
            veiculo = estoque.obter(venda.veiculo_ref)
            if veiculo.get("status") not in {"disponivel", "reservado"}:
                return RedirectResponse(
                    "/app/vendas?erro=conflito-estoque", status_code=303
                )
            estoque.acao(venda.veiculo_ref, "vender")
            estoque_baixado = True
        except VeiculoNaoEncontrado:
            return RedirectResponse("/app/vendas?erro=veiculo", status_code=303)
        except ConflitoEstoque:
            return RedirectResponse(
                "/app/vendas?erro=conflito-estoque", status_code=303
            )
        except EstoqueIndisponivel:
            return RedirectResponse(
                "/app/vendas?erro=estoque-indisponivel", status_code=303
            )
    venda.status = "confirmada"
    venda.confirmada_por = usuario.email
    venda.confirmada_em = agora()
    venda.atualizada_em = agora()
    if lead:
        aplicar_snapshot_venda(venda, lead, db, usuario.loja_slug)
    purchase = PurchaseConversion.from_sale(venda, lead)
    if settings.revy_trafego_venda_events_enabled:
        enfileirar_venda_confirmada(db, venda, purchase)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        erro = "reconciliacao" if estoque_baixado else "acao"
        return RedirectResponse(f"/app/vendas?erro={erro}", status_code=303)
    registrar_evento_funil_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        lead_ref=venda.lead_ref,
        tipo="venda_confirmada",
        idempotency_key=f"portal:venda:{venda.id}:confirmada",
        ocorrido_em=venda.confirmada_em,
        ator_email=usuario.email,
        payload={"venda_id": venda.id, "status": "confirmada"},
    )
    # Durante o cutover o Revy e o unico dono da CAPI. Com a flag off, o
    # comportamento legado local permanece intacto.
    if not settings.revy_trafego_venda_events_enabled:
        publish_conversion(
            ConversionKind.PURCHASE,
            purchase,
            db,
        )
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
    if settings.revy_trafego_venda_events_enabled:
        enfileirar_venda_atualizada(db, venda)
    db.commit()
    # Regra segura: cancelar o registro comercial nunca reabre estoque vendido.
    if venda.confirmada_em and venda.veiculo_ref:
        return RedirectResponse(
            "/app/vendas?ok=cancelada-estoque-mantido", status_code=303
        )
    return RedirectResponse("/app/vendas?ok=cancelada", status_code=303)


def valores_meta_form(form) -> dict[str, str]:
    return {
        campo: (form.get(campo) or "")
        for campo in ("escopo", "vendedor_email", "tipo", "periodo_inicio", "periodo_fim", "valor_alvo")
    }


def vendedores_da_loja(db: Session, loja_slug: str) -> list[Usuario]:
    return (
        db.query(Usuario)
        .filter(Usuario.loja_slug == loja_slug, Usuario.papel == "vendedor", Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
        .all()
    )


def validar_meta_form(form, db: Session, loja_slug: str) -> tuple[str, str | None, str, date, date, Decimal]:
    escopo = (form.get("escopo") or "loja").strip()
    if escopo not in ("loja", "vendedor"):
        raise ValueError("Selecione um escopo de meta válido.")
    vendedor_email = None
    if escopo == "vendedor":
        vendedor_email = (form.get("vendedor_email") or "").strip().lower()
        if not vendedor_email:
            raise ValueError("Selecione o vendedor para a meta individual.")
        vendedor = db.query(Usuario).filter(
            Usuario.email == vendedor_email,
            Usuario.loja_slug == loja_slug,
            Usuario.papel == "vendedor",
            Usuario.ativo.is_(True),
        ).first()
        if not vendedor:
            raise ValueError("Selecione um vendedor ativo desta loja.")
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
    return escopo, vendedor_email, tipo, inicio, fim, alvo


def meta_sobreposta(
    db: Session,
    loja_slug: str,
    escopo: str,
    vendedor_email: str | None,
    tipo: str,
    inicio: date,
    fim: date,
    ignorar_id: str | None = None,
) -> bool:
    consulta = db.query(Meta).filter(
        Meta.loja_slug == loja_slug,
        Meta.escopo == escopo,
        Meta.tipo == tipo,
        Meta.ativa.is_(True),
        Meta.periodo_inicio <= fim,
        Meta.periodo_fim >= inicio,
    )
    if escopo == "vendedor":
        consulta = consulta.filter(Meta.vendedor_email == vendedor_email)
    if ignorar_id:
        consulta = consulta.filter(Meta.id != ignorar_id)
    return consulta.first() is not None


def render_meta_form(
    request: Request,
    usuario,
    valores,
    titulo: str,
    db: Session,
    erro: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "metas/form.html",
        contexto(
            request,
            usuario,
            valores=valores,
            titulo=titulo,
            tipos=TIPOS_META,
            vendedores=vendedores_da_loja(db, usuario.loja_slug),
            erro=erro,
        ),
        status_code=status_code,
    )


@app.get("/app/metas", response_class=HTMLResponse)
def metas_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    pode_gerir = pode_gerir_metas(usuario)
    consulta = db.query(Meta).filter(Meta.loja_slug == usuario.loja_slug)
    # Metas por vendedor expõem escopo individual: só dono/gerente veem a lista completa.
    # Vendedores continuam vendo somente as metas da loja aqui (o atingimento individual
    # deles é exibido no próprio painel, em /app/vendedor).
    if pode_gerir:
        consulta = consulta.filter(Meta.escopo.in_(["loja", "vendedor"]))
    else:
        consulta = consulta.filter(Meta.escopo == "loja")
    metas = consulta.order_by(Meta.ativa.desc(), Meta.periodo_inicio.desc()).all()
    vendedores_por_email = {
        vendedor.email: vendedor
        for vendedor in db.query(Usuario).filter(Usuario.loja_slug == usuario.loja_slug).all()
    }
    return templates.TemplateResponse(
        "metas/lista.html",
        contexto(
            request,
            usuario,
            metas=metas,
            tipos=TIPOS_META,
            pode_gerir=pode_gerir,
            vendedores_por_email=vendedores_por_email,
        ),
    )


@app.get("/app/metas/nova", response_class=HTMLResponse)
def metas_nova(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_metas(usuario):
        return RedirectResponse("/app/metas", status_code=303)
    return render_meta_form(request, usuario, {}, "Cadastrar meta", db)


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
        escopo, vendedor_email, tipo, inicio, fim, alvo = validar_meta_form(form, db, usuario.loja_slug)
    except ValueError as exc:
        return render_meta_form(request, usuario, valores, "Cadastrar meta", db, str(exc), 422)
    if meta_sobreposta(db, usuario.loja_slug, escopo, vendedor_email, tipo, inicio, fim):
        return render_meta_form(
            request,
            usuario,
            valores,
            "Cadastrar meta",
            db,
            "Já existe uma meta ativa desse tipo sobrepondo o período informado.",
            422,
        )
    db.add(
        Meta(
            loja_slug=usuario.loja_slug,
            escopo=escopo,
            vendedor_email=vendedor_email,
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
        "escopo": meta.escopo,
        "vendedor_email": meta.vendedor_email or "",
        "tipo": meta.tipo,
        "periodo_inicio": meta.periodo_inicio.isoformat(),
        "periodo_fim": meta.periodo_fim.isoformat(),
        "valor_alvo": str(meta.valor_alvo),
    }
    return render_meta_form(request, usuario, valores, "Editar meta", db)


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
        escopo, vendedor_email, tipo, inicio, fim, alvo = validar_meta_form(form, db, usuario.loja_slug)
    except ValueError as exc:
        return render_meta_form(request, usuario, valores, "Editar meta", db, str(exc), 422)
    if meta_sobreposta(db, usuario.loja_slug, escopo, vendedor_email, tipo, inicio, fim, ignorar_id=meta.id):
        return render_meta_form(
            request,
            usuario,
            valores,
            "Editar meta",
            db,
            "Já existe uma meta ativa desse tipo sobrepondo o período informado.",
            422,
        )
    meta.escopo = escopo
    meta.vendedor_email = vendedor_email
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
    lucros_conhecidos = [valor for venda in confirmadas if (valor := lucro_bruto_venda(venda)) is not None]
    lucro = sum(lucros_conhecidos, Decimal("0"))
    lucro_completo = len(lucros_conhecidos) == len(confirmadas)
    realizado_por_tipo = {
        "quantidade": Decimal(len(confirmadas)),
        "faturamento": faturamento,
        "lucro_bruto": lucro,
    }
    metas_view = []
    metas = db.query(Meta).filter(
        Meta.loja_slug == usuario.loja_slug,
        Meta.escopo == "vendedor",
        Meta.vendedor_email == usuario.email,
        Meta.ativa.is_(True),
    ).all()
    for meta in metas:
        # Metas de lucro bruto expõem custo/margem. O vendedor nunca vê esse dado (só
        # dono/gerente/admin, via pode_ver_custo); mantido explícito aqui — mesmo o
        # vendedor não acessando esta checagem hoje — para não vazar dado financeiro
        # sensível caso este painel um dia sirva outro papel.
        if meta.tipo == "lucro_bruto" and not pode_ver_custo(usuario):
            continue
        if meta.tipo not in realizado_por_tipo or not (
            meta.periodo_inicio <= d_fim and meta.periodo_fim >= d_inicio
        ):
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


@app.get("/app/funil", response_class=HTMLResponse)
def funil_dashboard(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in {"dono", "gerente"}:
        return RedirectResponse("/app", status_code=303)

    sincronizacao_ok = sincronizar_funil_chatbot_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        chatbot=chatbot,
    )
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    periodo_invalido = d_inicio > d_fim
    if periodo_invalido:
        d_inicio, d_fim = d_fim, d_inicio
    inicio_dt = datetime.combine(d_inicio, datetime.min.time(), tzinfo=FUSO_PORTAL)
    fim_dt = datetime.combine(
        d_fim + timedelta(days=1),
        datetime.min.time(),
        tzinfo=FUSO_PORTAL,
    ) - timedelta(microseconds=1)
    funil = resumo_funil(
        db,
        loja_slug=usuario.loja_slug,
        inicio=inicio_dt,
        fim=fim_dt,
    )
    total = funil["total_leads"]
    etapas = []
    for tipo, rotulo, detalhe in (
        ("lead_criado", "Leads criados", "coorte criada no período"),
        ("primeira_resposta", "Primeira resposta", "leads que receberam uma resposta"),
        ("etapa_manual", "Movimentação manual", "leads atualizados pela equipe"),
        ("venda_registrada", "Venda registrada", "leads vinculados a uma venda"),
        ("venda_confirmada", "Venda confirmada", "leads com venda confirmada"),
        ("perda", "Perda registrada", "leads marcados como perdidos"),
    ):
        quantidade = funil["etapas"].get(tipo, 0)
        percentual = (
            Decimal(quantidade) * Decimal("100") / Decimal(total)
            if total
            else None
        )
        etapas.append(
            {
                "tipo": tipo,
                "rotulo": rotulo,
                "detalhe": detalhe,
                "quantidade": quantidade,
                "percentual": percentual,
                "barra_pct": min(float(percentual or 0), 100),
            }
        )

    return templates.TemplateResponse(
        "funil/index.html",
        contexto(
            request,
            usuario,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            periodo_invalido=periodo_invalido,
            sincronizacao_ok=sincronizacao_ok,
            funil=funil,
            etapas=etapas,
        ),
    )


@app.get("/app/funil/dados")
def funil_dados(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Backend do funil temporal; a UI pode consumir sem recalcular métricas."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in {"dono", "gerente"}:
        return RedirectResponse("/app", status_code=303)
    sincronizar_funil_chatbot_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        chatbot=chatbot,
    )
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    inicio_dt = datetime.combine(d_inicio, datetime.min.time(), tzinfo=FUSO_PORTAL)
    fim_dt = datetime.combine(
        d_fim + timedelta(days=1),
        datetime.min.time(),
        tzinfo=FUSO_PORTAL,
    ) - timedelta(microseconds=1)
    return {
        "periodo": {"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
        "funil": resumo_funil(
            db,
            loja_slug=usuario.loja_slug,
            inicio=inicio_dt,
            fim=fim_dt,
        ),
    }


@app.get("/app/financeiro", response_class=HTMLResponse)
def financeiro_dashboard(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    vendedor: str | None = None,
    origem: str | None = None,
    utm_campaign: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_ver_financeiro(usuario):
        return RedirectResponse("/app", status_code=303)
    sincronizar_funil_chatbot_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        chatbot=chatbot,
    )
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    resultado_vendas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    confirmadas = resultado_vendas["confirmadas"]
    faturamento = resultado_vendas["faturamento"]
    lucro = resultado_vendas["lucro_bruto"]
    lucro_completo = resultado_vendas["lucro_completo"]
    metricas = {
        "quantidade": resultado_vendas["quantidade"],
        "faturamento": faturamento,
        "lucro_bruto": lucro,
        "lucro_completo": lucro_completo,
        "vendas_lucro_incompleto": resultado_vendas["vendas_lucro_incompleto"],
    }
    realizado_por_tipo = {"quantidade": Decimal(len(confirmadas)), "faturamento": faturamento, "lucro_bruto": lucro}
    metas_view = metas_view_periodo(db, usuario.loja_slug, d_inicio, d_fim, realizado_por_tipo, lucro_completo)

    vendedores = db.query(Usuario).filter(
        Usuario.loja_slug == usuario.loja_slug,
        Usuario.ativo.is_(True),
        Usuario.papel.in_(["dono", "gerente", "vendedor"]),
    ).order_by(Usuario.nome).all()
    vendedores_por_email = {item.email: item for item in vendedores}
    vendedor_filtro = vendedor if vendedor in vendedores_por_email else None
    funil, origens, campanhas_utm = funil_periodo(
        chatbot,
        db,
        usuario.loja_slug,
        d_inicio,
        d_fim,
        vendedor_filtro,
        origem,
        confirmadas,
        utm_campaign=utm_campaign,
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
            campanhas_utm=campanhas_utm,
            filtros_funil={
                "vendedor": vendedor_filtro or "",
                "origem": origem or "",
                "utm_campaign": utm_campaign or "",
            },
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

    campos = {
        str(chave)[7:]: str(valor).strip()
        for chave, valor in form.multi_items()
        if str(chave).startswith("campo__") and str(valor).strip()
    }
    usuario_banco = (campos.get("usuario") or form.get("usuario") or "").strip()
    senha_banco = campos.get("senha") or form.get("senha") or ""
    if campos and (not usuario_banco or not senha_banco):
        return RedirectResponse(
            f"/app/financeiras?erro=campos&provedor={nome}", status_code=303
        )
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
            campos=campos or None,
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


PAPEIS_EQUIPE = {"gerente": "Gerente", "vendedor": "Vendedor"}
PAPEIS_EQUIPE_ROTULO = {
    "dono": "Dono",
    "admin_plataforma": "Administrador da plataforma",
    **PAPEIS_EQUIPE,
}
PAPEIS_IMUTAVEIS = {"dono", "admin_plataforma"}
EMAIL_EQUIPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_EQUIPE_MINIMA = 10


def _membro_da_loja(db: Session, usuario: Usuario, membro_id: str) -> Usuario | None:
    """Busca por id e loja na mesma consulta para impedir acesso entre tenants."""
    return (
        db.query(Usuario)
        .filter(Usuario.id == membro_id, Usuario.loja_slug == usuario.loja_slug)
        .first()
    )


def _membros_da_loja(db: Session, loja_slug: str) -> list[Usuario]:
    return (
        db.query(Usuario)
        .filter(Usuario.loja_slug == loja_slug)
        .order_by(Usuario.ativo.desc(), Usuario.nome, Usuario.email)
        .all()
    )


def _pode_editar_membro(usuario: Usuario, membro: Usuario) -> bool:
    """Contas protegidas só podem alterar os próprios dados e senha."""
    return membro.id == usuario.id or membro.papel in PAPEIS_EQUIPE


def _normalizar_nome(valor: str | None) -> str:
    nome = " ".join((valor or "").split())
    if len(nome) < 2:
        raise ValueError("Informe o nome completo do membro.")
    if len(nome) > 160:
        raise ValueError("O nome deve ter no máximo 160 caracteres.")
    return nome


def _normalizar_email(valor: str | None) -> str:
    email = (valor or "").strip().lower()
    if not email or len(email) > 320 or not EMAIL_EQUIPE_RE.fullmatch(email):
        raise ValueError("Informe um e-mail válido.")
    return email


def _validar_papel_equipe(valor: str | None) -> str:
    papel = (valor or "").strip()
    if papel not in PAPEIS_EQUIPE:
        raise ValueError("Selecione o papel gerente ou vendedor.")
    return papel


def _validar_nova_senha(senha: str | None, confirmacao: str | None) -> str:
    senha = senha or ""
    if len(senha) < SENHA_EQUIPE_MINIMA:
        raise ValueError(f"A senha deve ter pelo menos {SENHA_EQUIPE_MINIMA} caracteres.")
    if len(senha) > 256:
        raise ValueError("A senha deve ter no máximo 256 caracteres.")
    if senha != (confirmacao or ""):
        raise ValueError("A confirmação da senha não confere.")
    return senha


def _valores_membro_form(form) -> dict[str, str]:
    return {
        "nome": form.get("nome") or "",
        "email": form.get("email") or "",
        "papel": form.get("papel") or "vendedor",
    }


def _render_equipe_lista(
    request: Request,
    usuario: Usuario,
    db: Session,
    *,
    erro: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "equipe/lista.html",
        contexto(
            request,
            usuario,
            membros=_membros_da_loja(db, usuario.loja_slug),
            papeis_rotulo=PAPEIS_EQUIPE_ROTULO,
            erro=erro,
        ),
        status_code=status_code,
    )


def _render_membro_form(
    request: Request,
    usuario: Usuario,
    valores: dict[str, str],
    *,
    titulo: str,
    membro: Usuario | None = None,
    erro: str | None = None,
    status_code: int = 200,
):
    papel_bloqueado = bool(
        membro and (membro.papel in PAPEIS_IMUTAVEIS or membro.id == usuario.id)
    )
    return templates.TemplateResponse(
        "equipe/form.html",
        contexto(
            request,
            usuario,
            valores=valores,
            titulo=titulo,
            membro=membro,
            papeis=PAPEIS_EQUIPE,
            papeis_rotulo=PAPEIS_EQUIPE_ROTULO,
            papel_bloqueado=papel_bloqueado,
            erro=erro,
        ),
        status_code=status_code,
    )


@app.get("/app/equipe", response_class=HTMLResponse)
def equipe_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    return _render_equipe_lista(request, usuario, db)


@app.get("/app/equipe/novo", response_class=HTMLResponse)
def equipe_novo(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    return _render_membro_form(
        request,
        usuario,
        {"nome": "", "email": "", "papel": "vendedor"},
        titulo="Adicionar membro",
    )


@app.post("/app/equipe/novo")
async def equipe_criar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    valores = _valores_membro_form(form)
    try:
        nome = _normalizar_nome(form.get("nome"))
        email = _normalizar_email(form.get("email"))
        papel = _validar_papel_equipe(form.get("papel"))
        senha = _validar_nova_senha(
            form.get("senha"), form.get("senha_confirmacao")
        )
    except ValueError as exc:
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Adicionar membro",
            erro=str(exc),
            status_code=422,
        )
    if db.query(Usuario.id).filter(Usuario.email == email).first():
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Adicionar membro",
            erro="Este e-mail não está disponível para cadastro.",
            status_code=422,
        )
    db.add(
        Usuario(
            email=email,
            nome=nome,
            senha_hash=hash_senha(senha),
            papel=papel,
            loja_slug=usuario.loja_slug,
            ativo=True,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Adicionar membro",
            erro="Este e-mail não está disponível para cadastro.",
            status_code=422,
        )
    return RedirectResponse("/app/equipe?ok=criado", status_code=303)


@app.get("/app/equipe/{membro_id}/editar", response_class=HTMLResponse)
def equipe_editar_pagina(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    valores = {"nome": membro.nome, "email": membro.email, "papel": membro.papel}
    return _render_membro_form(
        request,
        usuario,
        valores,
        titulo="Editar membro",
        membro=membro,
    )


@app.post("/app/equipe/{membro_id}/editar")
async def equipe_editar(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    valores = {
        "nome": form.get("nome") or "",
        "email": membro.email,
        "papel": form.get("papel") or membro.papel,
    }
    try:
        nome = _normalizar_nome(form.get("nome"))
        if membro.papel in PAPEIS_IMUTAVEIS or membro.id == usuario.id:
            papel = (form.get("papel") or membro.papel).strip()
            if papel != membro.papel:
                raise ValueError("O papel desta conta protegida não pode ser alterado.")
        else:
            papel = _validar_papel_equipe(form.get("papel"))
    except ValueError as exc:
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Editar membro",
            membro=membro,
            erro=str(exc),
            status_code=422,
        )
    membro.nome = nome
    membro.papel = papel
    db.commit()
    return RedirectResponse("/app/equipe?ok=editado", status_code=303)


@app.get("/app/equipe/{membro_id}/senha", response_class=HTMLResponse)
def equipe_senha_pagina(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    return templates.TemplateResponse(
        "equipe/senha.html",
        contexto(
            request,
            usuario,
            membro=membro,
            erro=None,
            senha_minima=SENHA_EQUIPE_MINIMA,
        ),
    )


@app.post("/app/equipe/{membro_id}/senha")
async def equipe_redefinir_senha(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    try:
        senha = _validar_nova_senha(
            form.get("senha"), form.get("senha_confirmacao")
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "equipe/senha.html",
            contexto(
                request,
                usuario,
                membro=membro,
                erro=str(exc),
                senha_minima=SENHA_EQUIPE_MINIMA,
            ),
            status_code=422,
        )
    membro.senha_hash = hash_senha(senha)
    db.commit()
    return RedirectResponse("/app/equipe?ok=senha", status_code=303)


@app.post("/app/equipe/{membro_id}/{acao}")
async def equipe_alterar_acesso(
    request: Request,
    membro_id: str,
    acao: str,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if acao not in {"ativar", "desativar"}:
        return RedirectResponse("/app/equipe?erro=acao", status_code=303)
    if acao == "desativar" and membro.id == usuario.id:
        return RedirectResponse("/app/equipe?erro=auto-desativacao", status_code=303)
    if membro.papel not in PAPEIS_EQUIPE:
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    membro.ativo = acao == "ativar"
    db.commit()
    return RedirectResponse(f"/app/equipe?ok={acao}", status_code=303)


@app.get("/app/configuracoes", response_class=HTMLResponse)
def configuracoes(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if usuario.papel not in {"dono", "admin_plataforma"}:
        return RedirectResponse("/app", status_code=303)

    meta_config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    integracoes = [
        {
            "nome": "Estoque",
            "descricao": "Veículos e disponibilidade da loja.",
            "configurada": bool(settings.estoque_url and settings.estoque_token),
        },
        {
            "nome": "Chatbot",
            "descricao": "Leads e conversas do atendimento.",
            "configurada": bool(settings.chatbot_url and settings.chatbot_token),
        },
        {
            "nome": "Motor",
            "descricao": "Integração server-side com as financeiras.",
            "configurada": bool(settings.motor_url and settings.motor_token),
        },
        {
            "nome": "Meta / CAPI",
            "descricao": "Conversões da loja enviadas pelo servidor.",
            "configurada": bool(
                meta_config
                and normalizar_pixel_id(meta_config.pixel_id)
                and meta_config.token_ciphertext
            ),
        },
    ]
    return templates.TemplateResponse(
        "configuracoes/index.html",
        contexto(
            request,
            usuario,
            integracoes=integracoes,
            papel_rotulo=PAPEIS_EQUIPE_ROTULO.get(usuario.papel, usuario.papel),
            pode_equipe=pode_gerir_equipe(usuario),
            pode_trafego=pode_gerir_trafego(usuario),
            pode_financeiras=pode_gerir_financeiras(usuario),
        ),
    )


def _trafego_contexto(
    request: Request,
    usuario,
    config: MetaPixelConfig | None,
    *,
    ads_config: MetaAdsConfig | None = None,
    ultimo_outbox: MetaCapiOutbox | None = None,
    pendentes: int = 0,
    ok=None,
    erro=None,
    sync_resumo=None,
):
    token_configurado = bool(config and config.token_ciphertext)
    ads_token_configurado = bool(ads_config and ads_config.token_ciphertext)
    ultimo_erro_exibicao = None
    if ultimo_outbox is not None and ultimo_outbox.status == "failed":
        ultimo_erro_exibicao = (
            f"Meta respondeu HTTP {ultimo_outbox.last_http_status}."
            if ultimo_outbox.last_http_status
            else "O último envio falhou. Retente para processar novamente."
        )
    return contexto(
        request,
        usuario,
        config=config,
        ads_config=ads_config,
        token_configurado=token_configurado,
        ads_token_configurado=ads_token_configurado,
        pixel_id=normalizar_pixel_id(config.pixel_id if config else None),
        test_event_code=(config.test_event_code if config else "") or "",
        enviar_page_view=bool(config.enviar_page_view) if config else True,
        enviar_lead=bool(config.enviar_lead) if config else True,
        enviar_purchase=bool(config.enviar_purchase) if config else True,
        atualizada_em=config.atualizada_em if config else None,
        ad_account_id=(ads_config.ad_account_id if ads_config else "") or "",
        ads_sync_enabled=bool(ads_config.sync_enabled) if ads_config else True,
        ads_ultima_sync_em=ads_config.ultima_sync_em if ads_config else None,
        ads_ultima_sync_status=(ads_config.ultima_sync_status if ads_config else None),
        ads_ultima_sync_erro=(ads_config.ultima_sync_erro if ads_config else None),
        ads_ultima_sync_resumo=(ads_config.ultima_sync_resumo if ads_config else None),
        ultimo_outbox=ultimo_outbox,
        ultimo_erro_exibicao=ultimo_erro_exibicao,
        outbox_pendentes=pendentes,
        ok=ok,
        erro=erro,
        sync_resumo=sync_resumo,
    )


@app.get("/app/campanhas", response_class=HTMLResponse)
def campanhas_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug)
        .order_by(Campanha.criada_em.desc())
        .all()
    )
    gastos_totais: dict[str, Decimal] = {}
    for g in db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all():
        gastos_totais[g.campanha_id] = gastos_totais.get(g.campanha_id, Decimal("0")) + g.valor
    return templates.TemplateResponse(
        "campanhas/lista.html",
        contexto(
            request,
            usuario,
            campanhas=campanhas,
            gastos_totais=gastos_totais,
            canais=CANAIS_ROTULO,
            status_rotulo=STATUS_ROTULO,
        ),
    )


def _campanha_form_ctx(request, usuario, *, titulo, valores, erro=None):
    return contexto(
        request,
        usuario,
        titulo=titulo,
        valores=valores,
        erro=erro,
        canais=CANAIS_ROTULO,
        status_rotulo=STATUS_ROTULO,
    )


@app.get("/app/campanhas/nova", response_class=HTMLResponse)
def campanhas_nova_get(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "campanhas/form.html",
        _campanha_form_ctx(
            request,
            usuario,
            titulo="Nova campanha",
            valores={"canal": "meta", "status": "ativa"},
        ),
    )


@app.post("/app/campanhas/nova")
async def campanhas_nova_post(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    dados = campanha_payload_form(form)
    erros = validar_campanha_payload(dados)
    if erros:
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request, usuario, titulo="Nova campanha", valores=dados, erro="; ".join(erros)
            ),
            status_code=422,
        )
    norm = normalizar_utm(dados["utm_campaign"])
    if campanha_por_utm(db, usuario.loja_slug, norm):
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request,
                usuario,
                titulo="Nova campanha",
                valores=dados,
                erro="Já existe uma campanha com este utm_campaign nesta loja.",
            ),
            status_code=422,
        )
    c = Campanha(
        id=novo_id(),
        loja_slug=usuario.loja_slug,
        utm_campaign=dados["utm_campaign"].strip(),
        utm_campaign_norm=norm or "",
        criada_por_email=usuario.email,
    )
    preencher_campanha(c, dados, email=usuario.email)
    db.add(c)
    db.commit()
    return RedirectResponse("/app/campanhas?ok=criada", status_code=303)


def _gastos_lote_contexto(
    request: Request,
    usuario,
    db: Session,
    *,
    erro: str | None = None,
    relatorio: dict | None = None,
):
    from app.financeiro_calc import hoje_portal

    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug, Campanha.status == "ativa")
        .order_by(Campanha.nome)
        .all()
    )
    return contexto(
        request,
        usuario,
        campanhas=campanhas,
        hoje=hoje_portal().isoformat(),
        canais=CANAIS_ROTULO,
        erro=erro,
        relatorio=relatorio,
    )


@app.get("/app/campanhas/gastos/lote", response_class=HTMLResponse)
def campanhas_gastos_lote_get(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        "campanhas/gastos_lote.html",
        _gastos_lote_contexto(request, usuario, db),
    )


@app.post("/app/campanhas/gastos/lote")
async def campanhas_gastos_lote_post(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    try:
        referencia = date.fromisoformat((form.get("referencia") or "").strip())
    except ValueError:
        referencia = None
    if referencia is None:
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            _gastos_lote_contexto(request, usuario, db, erro="Informe uma data de referência válida."),
            status_code=422,
        )
    campanhas = db.query(Campanha).filter(
        Campanha.loja_slug == usuario.loja_slug,
        Campanha.status == "ativa",
    ).all()
    nota_global = (form.get("nota_global") or "").strip()[:240] or None
    novos: list[tuple[Campanha, Decimal, str | None]] = []
    for campanha in campanhas:
        texto_valor = (form.get(f"valor_{campanha.id}") or "").strip()
        if not texto_valor:
            continue
        valor = parse_brl_valor(texto_valor)
        if valor is None or valor <= 0:
            return templates.TemplateResponse(
                "campanhas/gastos_lote.html",
                _gastos_lote_contexto(
                    request,
                    usuario,
                    db,
                    erro=f"Informe um valor maior que zero para {campanha.nome}.",
                ),
                status_code=422,
            )
        nota = (form.get(f"nota_{campanha.id}") or "").strip()[:240] or nota_global
        novos.append((campanha, valor, nota))
    for campanha, valor, nota in novos:
        salvar_gasto_manual(
            db,
            campanha=campanha,
            loja_slug=usuario.loja_slug,
            valor=valor,
            referencia=referencia,
            nota=nota,
            criada_por=usuario.email,
        )
    db.commit()
    return RedirectResponse(f"/app/campanhas/gastos/lote?ok={len(novos)}", status_code=303)


@app.get("/app/campanhas/gastos/csv/modelo")
def campanhas_gastos_csv_modelo(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    conteudo = "\ufeffutm_campaign;valor;referencia;nota\n"
    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo-gastos-revy.csv"'},
    )


@app.post("/app/campanhas/gastos/csv", response_class=HTMLResponse)
async def campanhas_gastos_csv_post(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    arquivo = form.get("arquivo")
    if arquivo is None or not hasattr(arquivo, "read"):
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            _gastos_lote_contexto(request, usuario, db, erro="Selecione um arquivo CSV."),
            status_code=422,
        )
    conteudo = await arquivo.read()
    if len(conteudo) > 1024 * 1024:
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            _gastos_lote_contexto(request, usuario, db, erro="O CSV deve ter no máximo 1 MB."),
            status_code=413,
        )
    campanhas = db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
    linhas, erros = parse_gastos_csv(conteudo, campanhas)
    for linha in linhas:
        salvar_gasto_manual(
            db,
            campanha=linha.campanha,
            loja_slug=usuario.loja_slug,
            valor=linha.valor,
            referencia=linha.referencia,
            nota=linha.nota,
            criada_por=usuario.email,
        )
    db.commit()
    return templates.TemplateResponse(
        "campanhas/gastos_lote.html",
        _gastos_lote_contexto(
            request,
            usuario,
            db,
            relatorio={"importados": len(linhas), "erros": erros},
        ),
    )


@app.get("/app/campanhas/{campanha_id}", response_class=HTMLResponse)
def campanhas_detalhe(
    request: Request,
    campanha_id: str,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    gastos = (
        db.query(CampanhaGasto)
        .filter(
            CampanhaGasto.campanha_id == campanha.id,
            CampanhaGasto.loja_slug == usuario.loja_slug,
        )
        .order_by(CampanhaGasto.referencia.desc(), CampanhaGasto.criada_em.desc())
        .all()
    )
    gasto_total = sum((g.valor for g in gastos), Decimal("0"))
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    metricas_vendas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    leads: list[dict] = []
    chatbot_erro = False
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel:
        chatbot_erro = True
    linha_roi = next(
        linha
        for linha in calcular_roi_loja(
            campanhas=[campanha],
            gastos=gastos,
            leads=leads,
            vendas_confirmadas=metricas_vendas["confirmadas"],
            d_inicio=d_inicio,
            d_fim=d_fim,
            modo_atribuicao="last",
        )
        if linha.campanha_id == campanha.id
    )
    vendas_atribuidas = [
        venda
        for venda in metricas_vendas["confirmadas"]
        if venda_casa_campanha(venda, campanha, modo="last")
    ]
    from app.financeiro_calc import hoje_portal

    return templates.TemplateResponse(
        "campanhas/detalhe.html",
        contexto(
            request,
            usuario,
            campanha=campanha,
            gastos=gastos,
            gasto_total=gasto_total,
            canais=CANAIS_ROTULO,
            status_rotulo=STATUS_ROTULO,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            linha_roi=linha_roi,
            vendas_atribuidas=sorted(
                vendas_atribuidas,
                key=lambda venda: venda.confirmada_em or venda.criada_em,
                reverse=True,
            )[:10],
            chatbot_erro=chatbot_erro,
            hoje=hoje_portal().isoformat(),
            erro=request.query_params.get("erro"),
        ),
    )


@app.get("/app/campanhas/{campanha_id}/editar", response_class=HTMLResponse)
def campanhas_editar_get(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    valores = {
        "nome": campanha.nome,
        "canal": campanha.canal,
        "status": campanha.status,
        "utm_source": campanha.utm_source or "",
        "utm_medium": campanha.utm_medium or "",
        "utm_campaign": campanha.utm_campaign,
        "utm_content": campanha.utm_content or "",
        "utm_term": campanha.utm_term or "",
        "meta_campaign_id": campanha.meta_campaign_id or "",
        "codigo_ctwa": campanha.codigo_ctwa or "",
        "periodo_inicio": campanha.periodo_inicio.isoformat() if campanha.periodo_inicio else "",
        "periodo_fim": campanha.periodo_fim.isoformat() if campanha.periodo_fim else "",
        "notas": campanha.notas or "",
    }
    return templates.TemplateResponse(
        "campanhas/form.html",
        _campanha_form_ctx(request, usuario, titulo="Editar campanha", valores=valores),
    )


@app.post("/app/campanhas/{campanha_id}/editar")
async def campanhas_editar_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    dados = campanha_payload_form(form)
    erros = validar_campanha_payload(dados)
    if erros:
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request, usuario, titulo="Editar campanha", valores=dados, erro="; ".join(erros)
            ),
            status_code=422,
        )
    norm = normalizar_utm(dados["utm_campaign"])
    outra = campanha_por_utm(db, usuario.loja_slug, norm)
    if outra and outra.id != campanha.id:
        return templates.TemplateResponse(
            "campanhas/form.html",
            _campanha_form_ctx(
                request,
                usuario,
                titulo="Editar campanha",
                valores=dados,
                erro="Já existe uma campanha com este utm_campaign nesta loja.",
            ),
            status_code=422,
        )
    preencher_campanha(campanha, dados)
    db.commit()
    return RedirectResponse(f"/app/campanhas/{campanha.id}?ok=salvo", status_code=303)


@app.post("/app/campanhas/{campanha_id}/apagar")
async def campanhas_apagar_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    db.delete(campanha)
    db.commit()
    return RedirectResponse("/app/campanhas?ok=apagada", status_code=303)


@app.post("/app/campanhas/{campanha_id}/gastos")
async def campanhas_gasto_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return RedirectResponse("/app/campanhas?erro=1", status_code=303)
    valor = parse_brl_valor(form.get("valor"))
    try:
        referencia = date.fromisoformat((form.get("referencia") or "").strip())
    except ValueError:
        referencia = None
    if valor is None or referencia is None:
        return RedirectResponse(
            f"/app/campanhas/{campanha.id}?erro=Informe+valor+e+data+válidos",
            status_code=303,
        )
    salvar_gasto_manual(
        db,
        campanha=campanha,
        loja_slug=usuario.loja_slug,
        valor=valor,
        referencia=referencia,
        nota=(form.get("nota") or "").strip() or None,
        criada_por=usuario.email,
    )
    db.commit()
    return RedirectResponse(f"/app/campanhas/{campanha.id}?ok=gasto", status_code=303)


@app.get("/app/trafego/roi", response_class=HTMLResponse)
def trafego_roi(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    touch: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    modo = touch if touch in ("first", "last") else "last"
    campanhas = (
        db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
    )
    gastos = (
        db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all()
    )
    metricas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    chatbot_erro = None
    leads: list[dict] = []
    try:
        leads = get_chatbot_client().listar_leads()
    except ChatbotIndisponivel:
        chatbot_erro = "indisponivel"
    linhas = calcular_roi_loja(
        campanhas=campanhas,
        gastos=gastos,
        leads=leads,
        vendas_confirmadas=metricas["confirmadas"],
        d_inicio=d_inicio,
        d_fim=d_fim,
        modo_atribuicao=modo,
    )
    totais = totais_roi(linhas)
    return templates.TemplateResponse(
        "trafego/roi.html",
        contexto(
            request,
            usuario,
            periodo={"inicio": d_inicio.isoformat(), "fim": d_fim.isoformat()},
            touch=modo,
            linhas=linhas,
            totais=totais,
            insights=gerar_insights_roi(linhas, totais),
            canais=CANAIS_ROTULO,
            chatbot_erro=chatbot_erro,
            totais_roas_barra=(
                min(100.0, float(totais["roas"]) / 5.0 * 100.0) if totais.get("roas") else 0.0
            ),
        ),
    )


@app.get("/app/trafego/pixel-auditoria", response_class=HTMLResponse)
def trafego_pixel_auditoria(
    request: Request,
    db: Session = Depends(get_db),
    origem: str | None = None,
):
    """Auditoria de chaves Pixel/CAPI (Event Match Quality flags)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    from app.pixel_capi_auditoria import listar_auditoria_pixel

    origem_filtro = (origem or "").strip() or None
    itens = listar_auditoria_pixel(
        db, usuario.loja_slug, limit=100, origem=origem_filtro
    )
    return templates.TemplateResponse(
        "trafego/pixel_auditoria.html",
        contexto(
            request,
            usuario,
            itens=itens,
            origem_filtro=origem_filtro or "",
        ),
    )


@app.get("/app/trafego/ctwa-auditoria", response_class=HTMLResponse)
def trafego_ctwa_auditoria(
    request: Request,
    db: Session = Depends(get_db),
    so_com_clid: str | None = None,
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Auditoria de sinais CTWA recebidos no webhook (via Chatbot API)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_trafego(usuario):
        return RedirectResponse("/app", status_code=303)
    filtro_clid = (so_com_clid or "").strip() in {"1", "true", "on", "sim"}
    itens: list = []
    erro_chatbot = None
    try:
        dados = chatbot.listar_auditoria_ctwa(limit=80, so_com_clid=filtro_clid)
        itens = dados.get("itens") or []
    except ChatbotIndisponivel:
        erro_chatbot = "Chatbot indisponível — não foi possível carregar a auditoria CTWA."
    return templates.TemplateResponse(
        "trafego/ctwa_auditoria.html",
        contexto(
            request,
            usuario,
            itens=itens,
            so_com_clid=filtro_clid,
            erro_chatbot=erro_chatbot,
        ),
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
    ads_config = (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    ok = request.query_params.get("ok")
    outboxes = (
        db.query(MetaCapiOutbox)
        .filter(MetaCapiOutbox.loja_slug == usuario.loja_slug)
        .order_by(MetaCapiOutbox.criada_em.desc())
        .all()
    )
    return templates.TemplateResponse(
        "trafego/form.html",
        _trafego_contexto(
            request,
            usuario,
            config,
            ads_config=ads_config,
            ultimo_outbox=outboxes[0] if outboxes else None,
            pendentes=sum(o.status in {"pending", "failed"} for o in outboxes),
            ok=ok,
            sync_resumo=request.query_params.get("sync"),
        ),
    )


@app.post("/app/trafego/capi/retentar")
async def trafego_capi_retentar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    resultado = processar_outbox_pendentes(db, usuario.loja_slug)
    return RedirectResponse(
        f"/app/trafego?ok=retry-{resultado['entregues']}-{resultado['falharam']}",
        status_code=303,
    )


@app.post("/app/trafego/onboarding/dispensar")
async def trafego_onboarding_dispensar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    config = db.query(MetaPixelConfig).filter(
        MetaPixelConfig.loja_slug == usuario.loja_slug
    ).first()
    if config is None:
        config = MetaPixelConfig(loja_slug=usuario.loja_slug, pixel_id="")
        db.add(config)
    config.medicao_onboarding_dismiss_em = agora()
    db.commit()
    return RedirectResponse("/app?ok=onboarding-dispensado", status_code=303)


@app.post("/app/trafego/ads/salvar")
async def trafego_ads_salvar(request: Request, db: Session = Depends(get_db)):
    """Salva conta de anúncios Meta (Marketing API / spend) — separado do CAPI."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)

    ads_config = (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    config = (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    account = normalizar_ad_account_id(form.get("ad_account_id"))
    token_novo = (form.get("ads_token") or "").strip()
    sync_enabled = form.get("ads_sync_enabled") == "on"

    if not account:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe o ID da conta de anúncios Meta (act_… ou só números).",
            ),
            status_code=422,
        )
    if not token_novo and not (ads_config and ads_config.token_ciphertext):
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe o token com permissão ads_read (Marketing API).",
            ),
            status_code=422,
        )

    if ads_config is None:
        ads_config = MetaAdsConfig(loja_slug=usuario.loja_slug, ad_account_id=account)
        db.add(ads_config)
    ads_config.ad_account_id = account
    ads_config.sync_enabled = sync_enabled
    if token_novo:
        ads_config.token_ciphertext = cifrar(token_novo)
    ads_config.atualizada_em = agora()
    db.commit()
    return RedirectResponse("/app/trafego?ok=ads-salvo", status_code=303)


@app.post("/app/trafego/ads/sincronizar")
async def trafego_ads_sincronizar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)
    result = sincronizar_gastos_meta(db, usuario.loja_slug, janela_dias=7)
    if result.status == "erro":
        return RedirectResponse("/app/trafego?ok=sync-erro", status_code=303)
    return RedirectResponse("/app/trafego?ok=sync-ok", status_code=303)


@app.post("/internal/v1/provisioning/state")
def receber_estado_provisionamento(
    payload: dict,
    db: Session = Depends(get_db),
    x_service_token: str = Header(default="", alias="X-Service-Token"),
):
    """Recebe snapshot operacional do Control e aplica projeção monotônica local.

    Autentica com ``X-Service-Token`` vs ``PORTAL_SERVICE_TOKEN`` (ou
    ``PORTAL_PROVISIONING_TOKEN``). Token vazio → 503; incorreto → 401.
    Multi-tenant por ``loja_slug`` no body (sem sessão de usuário).
    """
    esperado = (
        os.getenv("PORTAL_SERVICE_TOKEN")
        or os.getenv("PORTAL_PROVISIONING_TOKEN")
        or ""
    ).strip()
    if not esperado:
        return JSONResponse(
            {
                "detail": (
                    "provisioning desabilitado "
                    "(PORTAL_SERVICE_TOKEN / PORTAL_PROVISIONING_TOKEN vazio)"
                )
            },
            status_code=503,
        )
    if not secrets.compare_digest(x_service_token or "", esperado):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)

    loja_slug = str(payload.get("loja_slug") or "").strip()
    if not loja_slug:
        return JSONResponse({"detail": "loja_slug obrigatório"}, status_code=422)

    reasons = provisioning.apply_payload(db, loja_slug, payload)
    db.commit()
    return {
        "ok": True,
        "reasons": reasons,
        "allows_processing": provisioning.allows_processing(db, loja_slug),
    }


@app.post("/internal/jobs/meta-spend-sync")
def job_meta_spend_sync(
    x_job_token: str = Header(default="", alias="X-Job-Token"),
):
    """Dispara sync de todas as lojas (cron externo ou health-ops).

    Autentica com ``PORTAL_META_SPEND_JOB_SECRET``. Se o segredo estiver vazio,
    o endpoint responde 503 (desligado de propósito).
    """
    esperado = (os.getenv("PORTAL_META_SPEND_JOB_SECRET") or "").strip()
    if not esperado:
        return JSONResponse(
            {"detail": "job desabilitado (PORTAL_META_SPEND_JOB_SECRET vazio)"},
            status_code=503,
        )
    if not secrets.compare_digest(x_job_token or "", esperado):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)

    worker = meta_ads_spend_job.get_worker()
    if worker is None:
        # Processo sem lifespan worker (ex.: testes) — executa uma vez direto.
        janela = int(os.getenv("PORTAL_META_SPEND_SYNC_JANELA_DIAS", "3") or "3")
        runner = meta_ads_spend_job.MetaSpendSyncWorker(
            db_factory=SessionLocal,
            enabled=True,
            interval_seconds=86400,
            initial_delay_seconds=0,
            janela_dias=janela,
        )
        payload = runner.run_once()
    else:
        payload = worker.run_once()
    return JSONResponse(payload)


@app.post("/app/trafego")
async def trafego_salvar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_trafego(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app", status_code=303)

    pixel_id_informado = (form.get("pixel_id") or "").strip()
    pixel_id = normalizar_pixel_id(pixel_id_informado)
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
    ads_config = (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == usuario.loja_slug)
        .first()
    )
    if not pixel_id:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request,
                usuario,
                config,
                ads_config=ads_config,
                erro="Informe um Pixel ID válido, contendo somente números.",
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
                ads_config=ads_config,
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
    try:
        from app.pixel_capi_auditoria import registrar_auditoria_pixel

        registrar_auditoria_pixel(
            db,
            loja_slug=usuario.loja_slug,
            origem="config_salva",
            pixel_id=pixel_id,
            modo="config",
            tem_test_event_code=bool(test_event_code),
            enviar_page_view=enviar_page_view,
            enviar_lead=enviar_lead,
            enviar_purchase=enviar_purchase,
            status="ok",
            detalhe="token_atualizado" if token_novo else "token_mantido",
        )
    except Exception:
        pass
    db.commit()
    return RedirectResponse("/app/trafego?ok=salvo", status_code=303)


# Import tardio (fim do arquivo): app.relatorios reaproveita helpers definidos
# acima (usuario_atual, contexto, templates, get_chatbot_client etc.) — importar
# aqui evita ciclo de import, já que app.main é o módulo carregado primeiro.
from app import relatorios  # noqa: E402
from app.web import loja_estoque  # noqa: E402

app.include_router(relatorios.router)
# Revy Loja Fase 2: visão geral de estoque + entrada de veículos (flag off por padrão).
app.include_router(loja_estoque.router)
