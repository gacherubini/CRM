from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

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
    hash_senha,  # reexportado para app.web.equipe e imports tardios
    iniciar_sessao,
    pode_confirmar_venda,
    pode_gerir_equipe,
    pode_gerir_financeiras,
    pode_ver_equipe,
    pode_gerir_metas,
    pode_gerir_estoque,
    pode_gerir_trafego,
    pode_registrar_venda,
    pode_ver_custo,
    pode_ver_financeiro,
    pode_ver_resultados_midia,
    usuario_atual,
    verifica_senha,  # reexportado / uso legado em módulos que importam de main
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
from app import (
    copiloto_sinais_job,
    copiloto_turnos_job,
    meta_ads_spend_job,
    meta_capi_job,
    revy_trafego_outbox_job,
)
from app.revy_trafego_outbox import (
    enfileirar_venda_atualizada,
    enfileirar_venda_confirmada,
)
from app.campanhas import (
    CANAIS_ROTULO,
    STATUS_ROTULO,
    aplicar_snapshot_venda,
    campanha_por_utm,
    lead_casa_campanha,
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
from app.loja.redirects import resolve_legacy_redirect, should_consider_request
from app.web.loja_shell import check_module_access, router as loja_shell_router
from app.web.owner_invitations import router as owner_invitations_router
from app.web.password_reset import router as password_reset_router
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
from app.password_rules import SenhaInvalida, validar_nova_senha  # reexport / equipe
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


# Fuso de exibição da UI (Brasil). APIs continuam em UTC; só a formatação muda.
_TZ_EXIBICAO = ZoneInfo(os.getenv("PORTAL_TIMEZONE", "America/Sao_Paulo"))


def formatar_horario(iso: str | None) -> str:
    """ISO (UTC ou com offset) → ``dd/mm HH:MM`` em horário de Brasília.

    Sem isso, timestamps com ``+00:00`` apareciam 3h adiantados na UI.
    """
    if not iso:
        return ""
    try:
        bruto = str(iso).strip().replace("Z", "+00:00")
        momento = datetime.fromisoformat(bruto)
    except ValueError:
        return str(iso)
    if momento.tzinfo is None:
        # naive: trata como UTC (contrato das APIs internas).
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(_TZ_EXIBICAO).strftime("%d/%m %H:%M")


def tempo_relativo(iso: str | None, *, agora: datetime | None = None) -> str:
    """Há quanto tempo foi ``iso``: "agora", "12 min", "3 h", "2 d", "5 sem".

    A fila de atendimento não mostrava tempo nenhum: dava para ler a última
    mensagem mas não para saber se o cliente esperou 5 minutos ou 5 dias, que é
    a decisão primária daquela tela.
    """
    if not iso:
        return "—"
    try:
        momento = datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    referencia = agora or datetime.now(timezone.utc)
    segundos = (referencia - momento).total_seconds()
    if segundos < 0:
        return "agora"
    if segundos < 90:
        return "agora"
    minutos = segundos / 60
    if minutos < 60:
        return f"{int(minutos)} min"
    horas = minutos / 60
    if horas < 24:
        return f"{int(horas)} h"
    dias = horas / 24
    if dias < 7:
        return f"{int(dias)} d"
    return f"{int(dias // 7)} sem"


def formatar_data(iso: str | None) -> str:
    """ISO (2026-07-01) -> 01/07/2026. Devolve a entrada se nao for data."""
    if not iso:
        return ""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


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
templates.env.globals["formatar_data"] = formatar_data
templates.env.globals["tempo_relativo"] = tempo_relativo
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
        copiloto_sinais_job.start_worker(SessionLocal)
        copiloto_turnos_job.start_worker(SessionLocal)
    try:
        yield
    finally:
        meta_ads_spend_job.stop_worker()
        meta_capi_job.stop_worker()
        revy_trafego_outbox_job.stop_worker()
        copiloto_sinais_job.stop_worker()
        copiloto_turnos_job.stop_worker()


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
app.include_router(owner_invitations_router)
app.include_router(password_reset_router)


@app.middleware("http")
async def revy_loja_legacy_redirects(request: Request, call_next):
    """F8: redirects graduais legado → shell (flags default OFF)."""
    if should_consider_request(request.method, request.headers.get("accept")):
        destino = resolve_legacy_redirect(request.url.path)
        if destino is not None:
            return RedirectResponse(destino, status_code=303)
    return await call_next(request)


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
        "revy_loja_atendimento_enabled": settings.revy_loja_atendimento_enabled,
        "revy_loja_shell_enabled": settings.revy_loja_shell_enabled,
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


@app.get("/conta/senha", response_class=HTMLResponse)
def conta_senha_pagina(request: Request, db: Session = Depends(get_db)):
    """Compatibilidade: bookmark /conta/senha → área Perfil do shell."""
    usuario = usuario_atual(request, db)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/app/loja/perfil#trocar-senha", status_code=303)


@app.post("/conta/senha", response_class=HTMLResponse)
def conta_senha_salvar(
    request: Request,
    senha_atual: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    senha_confirmacao: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    """Compatibilidade do form legado; lógica canônica em /app/loja/perfil/senha."""
    from app.web.loja_perfil import aplicar_troca_senha, _render_perfil

    usuario = usuario_atual(request, db)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    if not csrf_valido(request, csrf):
        return _render_perfil(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página.",
            status_code=400,
        )
    erro = aplicar_troca_senha(
        usuario,
        senha_atual=senha_atual,
        senha=senha,
        senha_confirmacao=senha_confirmacao,
    )
    if erro:
        return _render_perfil(request, usuario, db, erro=erro, status_code=400)
    db.commit()
    return _render_perfil(
        request, usuario, db, mensagem="Senha alterada com sucesso."
    )


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
    except (ConflitoEstoque, EstoqueIndisponivel, VeiculoNaoEncontrado, ValueError) as exc:
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
    """Distribuição/reatribuição de atendimento permanece no Revy Loja (F5).

    Contas e cargos estruturais migram para o Revy Control; assumir/devolver
    e ``AtendimentoAtribuicao`` continuam operacionais aqui (não são cadastro
    de equipe nem números WhatsApp/tokens). Grava trilha formal em
    ``loja_operacao_auditoria`` (telefone só como HMAC).
    """
    from app.loja_operacao_auditoria import registrar_auditoria_atendimento

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

    de_email: str | None = None
    if ativas:
        # Preferência: responsável distinto do ator (reatribuição).
        outros = [a.vendedor_email for a in ativas if a.vendedor_email != usuario.email]
        de_email = outros[0] if outros else ativas[0].vendedor_email

    for atribuicao in ativas:
        atribuicao.ativa = False
        atribuicao.encerrada_em = instante

    origem = "handoff_portal"
    if assumir:
        acao_audit = "reatribuir" if de_email and de_email != usuario.email else "assumir"
        para_email = usuario.email
        db.add(
            AtendimentoAtribuicao(
                loja_slug=usuario.loja_slug,
                telefone_hmac=telefone_hmac,
                vendedor_email=usuario.email,
                origem=origem,
                iniciada_em=instante,
                ativa=True,
            )
        )
    else:
        acao_audit = "devolver"
        para_email = None

    registrar_auditoria_atendimento(
        db,
        loja_slug=usuario.loja_slug,
        acao=acao_audit,
        ator_email=usuario.email,
        telefone_hmac=telefone_hmac,
        de_email=de_email,
        para_email=para_email,
        origem=origem,
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


CATEGORIAS_CUSTO = ["documentacao", "frete", "comissao", "outros"]
STATUS_VENDA = ["registrada", "confirmada", "cancelada"]
TIPOS_META = {
    "quantidade": "Quantidade de vendas",
    "faturamento": "Faturamento",
    "lucro_bruto": "Lucro bruto",
}


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


def _destino_vendas(request: Request) -> str:
    """Para onde voltar depois de registrar/agir sobre uma venda.

    Com ``?origem=loja`` a pessoa veio do shell Revy Loja e tem que voltar para
    ele — cair na lista legada era jogá-la para fora do menu (ver L1 na triagem).
    """
    if (request.query_params.get("origem") or "").strip() == "loja":
        return "/app/loja/vendas/lista"
    return "/app/vendas"


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
            destino_vendas=_destino_vendas(request),
            pode_confirmar=pode_confirmar_venda(usuario),
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
    lead_ref: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_registrar_venda(usuario):
        return RedirectResponse("/app/vendas", status_code=303)
    valores = {"lead_ref": lead_ref.strip()} if lead_ref and lead_ref.strip() else None
    return _render_venda_form(request, usuario, chatbot, estoque, valores=valores)


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
    return RedirectResponse(
        f"{_destino_vendas(request)}?ok=registrada{sufixo}", status_code=303
    )


def executar_confirmacao_venda(
    db: Session,
    usuario: Usuario,
    venda_id: str,
    chatbot: ChatbotClient,
    estoque: EstoqueClient,
) -> str:
    """Confirma a venda e dispara a cascata; devolve o código do resultado.

    Compartilhada pela rota legada e pelo shell Revy Loja — a confirmação é o
    gatilho de estoque, funil, Revy Tráfego e Meta, e não pode divergir entre as
    duas entradas. Chamador cuida de permissão, CSRF e do redirect.
    """
    if not provisioning.allows_processing(db, usuario.loja_slug):
        return "erro=loja-nao-operacional"
    venda = db.query(Venda).filter(Venda.id == venda_id, Venda.loja_slug == usuario.loja_slug).first()
    if not venda or venda.status == "cancelada":
        return "erro=acao"
    if venda.status == "confirmada":
        return "ok=ja-confirmada"
    lead = None
    if venda.lead_ref:
        try:
            lead = chatbot.obter_lead(venda.lead_ref)
        except LeadNaoEncontrado:
            return "erro=lead"
        except ChatbotIndisponivel:
            return "erro=chatbot-indisponivel"
    estoque_baixado = False
    if venda.veiculo_ref:
        try:
            veiculo = estoque.obter(venda.veiculo_ref)
            if veiculo.get("status") not in {"disponivel", "reservado"}:
                return "erro=conflito-estoque"
            estoque.acao(venda.veiculo_ref, "vender")
            estoque_baixado = True
        except VeiculoNaoEncontrado:
            return "erro=veiculo"
        except ConflitoEstoque:
            return "erro=conflito-estoque"
        except EstoqueIndisponivel:
            return "erro=estoque-indisponivel"
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
        return "erro=reconciliacao" if estoque_baixado else "erro=acao"
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
    return "ok=confirmada"


def executar_cancelamento_venda(
    db: Session,
    usuario: Usuario,
    venda_id: str,
    motivo: str,
) -> str:
    """Cancela o registro comercial; devolve o código do resultado.

    Compartilhada pela rota legada e pelo shell Revy Loja.
    """
    venda = db.query(Venda).filter(Venda.id == venda_id, Venda.loja_slug == usuario.loja_slug).first()
    motivo = (motivo or "").strip()
    if not venda:
        return "erro=acao"
    if not motivo:
        return "erro=motivo"
    venda.status = "cancelada"
    venda.motivo_cancelamento = motivo
    venda.atualizada_em = agora()
    if settings.revy_trafego_venda_events_enabled:
        enfileirar_venda_atualizada(db, venda)
    db.commit()
    # Regra segura: cancelar o registro comercial nunca reabre estoque vendido.
    if venda.confirmada_em and venda.veiculo_ref:
        return "ok=cancelada-estoque-mantido"
    return "ok=cancelada"


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
    resultado = executar_confirmacao_venda(db, usuario, venda_id, chatbot, estoque)
    return RedirectResponse(f"/app/vendas?{resultado}", status_code=303)


@app.post("/app/vendas/{venda_id}/cancelar")
async def vendas_cancelar(request: Request, venda_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_confirmar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/vendas", status_code=303)
    resultado = executar_cancelamento_venda(db, usuario, venda_id, form.get("motivo"))
    return RedirectResponse(f"/app/vendas?{resultado}", status_code=303)


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

    from app.loja_operacao_auditoria import registrar_auditoria_financeira

    if not motor.configurado:
        try:
            registrar_auditoria_financeira(
                db,
                loja_slug=usuario.loja_slug,
                acao="upsert",
                ator_email=usuario.email,
                provedor=nome,
                success=False,
                error_code="motor_nao_configurado",
                commit=True,
            )
        except Exception:
            db.rollback()
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    try:
        # Senha só no BFF → Motor; não logar form/body nem gravar na auditoria.
        motor.upsert_credencial(
            nome=nome,
            usuario=usuario_banco,
            senha=senha_banco,
            ator=usuario.email,
            campos=campos or None,
        )
    except MotorIndisponivel:
        try:
            registrar_auditoria_financeira(
                db,
                loja_slug=usuario.loja_slug,
                acao="upsert",
                ator_email=usuario.email,
                provedor=nome,
                success=False,
                error_code="motor_indisponivel",
                commit=True,
            )
        except Exception:
            db.rollback()
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    try:
        registrar_auditoria_financeira(
            db,
            loja_slug=usuario.loja_slug,
            acao="upsert",
            ator_email=usuario.email,
            provedor=nome,
            success=True,
            commit=True,
        )
    except Exception:
        db.rollback()
        logger.exception("falha ao auditar upsert financeira provedor=%s", nome)

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

    from app.loja_operacao_auditoria import registrar_auditoria_financeira

    if not motor.configurado:
        try:
            registrar_auditoria_financeira(
                db,
                loja_slug=usuario.loja_slug,
                acao="testar",
                ator_email=usuario.email,
                provedor=nome,
                success=False,
                error_code="motor_nao_configurado",
                commit=True,
            )
        except Exception:
            db.rollback()
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    try:
        resultado = motor.testar_login(nome, ator=usuario.email)
    except CredencialNaoEncontrada:
        try:
            registrar_auditoria_financeira(
                db,
                loja_slug=usuario.loja_slug,
                acao="testar",
                ator_email=usuario.email,
                provedor=nome,
                success=False,
                error_code="sem_credencial",
                commit=True,
            )
        except Exception:
            db.rollback()
        return RedirectResponse(
            f"/app/financeiras?erro=sem_credencial&provedor={nome}", status_code=303
        )
    except MotorIndisponivel:
        try:
            registrar_auditoria_financeira(
                db,
                loja_slug=usuario.loja_slug,
                acao="testar",
                ator_email=usuario.email,
                provedor=nome,
                success=False,
                error_code="motor_indisponivel",
                commit=True,
            )
        except Exception:
            db.rollback()
        return RedirectResponse("/app/financeiras?erro=motor", status_code=303)

    status_teste = resultado.get("status") or "ok"
    sucesso = status_teste in {"ok", "sucesso", "success", "placeholder"}
    try:
        registrar_auditoria_financeira(
            db,
            loja_slug=usuario.loja_slug,
            acao="testar",
            ator_email=usuario.email,
            provedor=nome,
            success=sucesso,
            error_code=None if sucesso else str(status_teste)[:80],
            commit=True,
        )
    except Exception:
        db.rollback()
        logger.exception("falha ao auditar teste financeira provedor=%s", nome)

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


# Import tardio (fim do arquivo): app.relatorios reaproveita helpers definidos
# acima (usuario_atual, contexto, templates, get_chatbot_client etc.) — importar
# aqui evita ciclo de import, já que app.main é o módulo carregado primeiro.
from app import relatorios  # noqa: E402
from app.web import equipe as equipe_routes  # noqa: E402
from app.web import metas as metas_routes  # noqa: E402
from app.web import simulacoes as simulacoes_routes  # noqa: E402
from app.web import trafego as trafego_routes  # noqa: E402
from app.web import loja_copiloto  # noqa: E402
from app.web import loja_estoque  # noqa: E402
from app.web import loja_vendas  # noqa: E402
from app.web import loja_whatsapp  # noqa: E402
from app.web import loja_catalogo  # noqa: E402
from app.web import loja_integracoes  # noqa: E402
from app.web import loja_perfil  # noqa: E402
from app.loja import routes as loja_routes  # noqa: E402

app.include_router(relatorios.router)
app.include_router(equipe_routes.router)
app.include_router(metas_routes.router)
app.include_router(simulacoes_routes.router)
app.include_router(trafego_routes.router)
# Revy Loja modules (flags default off).
app.include_router(loja_copiloto.router)
app.include_router(loja_estoque.router)
app.include_router(loja_vendas.router)
app.include_router(loja_whatsapp.router)
app.include_router(loja_catalogo.router)
app.include_router(loja_integracoes.router)
app.include_router(loja_perfil.router)
app.include_router(loja_routes.router)
