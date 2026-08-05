"""Revy Tráfego — app multi-loja da equipe Revy (Fase 1)."""
from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import meta_ads_spend_job, meta_capi_job
from app.audit import registrar_audit
from app.auth import (
    autenticar,
    bootstrap_gestor_se_vazio,
    csrf_token,
    csrf_valido,
    definir_loja,
    encerrar_sessao,
    gestor_atual,
    iniciar_sessao,
    loja_atual,
    sessao_gestor,
)
from app.campanhas import (
    CANAIS_ROTULO,
    STATUS_ROTULO,
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
from app.clients.chatbot import (
    ChatbotClient,
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    LeadNaoEncontrado,
)
from urllib.parse import quote
from app.config import settings
from app.control.session import current_store, select_store, visible_stores
from app.control.types import StoreNotFound
from app.cripto import cifrar
from app.db import SessionLocal, get_db
from app.financeiro_calc import calcular_metricas_vendas, hoje_portal, periodo_padrao
from app.lojas import listar_loja_slugs
from app.meta_ads_spend import normalizar_ad_account_id, sincronizar_gastos_meta
from app.meta_capi import processar_outbox_pendentes
from app.meta_pixel import normalizar_pixel_id
from app.models import (
    Campanha,
    CampanhaGasto,
    MetaAdsConfig,
    MetaCapiOutbox,
    MetaPixelConfig,
    agora,
    novo_id,
)
from app.roi_calc import calcular_roi_loja, gerar_insights_roi, totais_roi, venda_casa_campanha
from app.api_v1 import router as api_v1_router
from app.web.control import router as control_router
from app.web.control_ui import router as control_ui_router

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if os.getenv("REVY_TRAFEGO_SKIP_INIT") != "1":
        # Workers opt-in. No bundle Fly o env é o mesmo do portal: se o portal
        # tem PORTAL_*_ENABLED=0 no machine env, setdefault NÃO reativa o worker.
        # Por isso forçamos "1" só neste processo quando o cutover está ligado.
        if settings.meta_spend_sync_enabled:
            os.environ["PORTAL_META_SPEND_SYNC_ENABLED"] = "1"
            meta_ads_spend_job.start_worker(SessionLocal)
            logger.info("revy-trafego: meta_spend worker ON")
        if settings.run_capi_worker:
            os.environ["PORTAL_CAPI_RETRY_ENABLED"] = "1"
            meta_capi_job.start_worker(SessionLocal)
            logger.info("revy-trafego: capi retry worker ON")
        # Atribuição CTWA: resolve ad_id→campaign via Graph (sempre ligado no runtime).
        # Em testes, REVY_TRAFEGO_SKIP_INIT=1 impede o lifespan de subir workers.
        from app import meta_ad_resolver_job

        meta_ad_resolver_job.start_worker(
            SessionLocal,
            chatbot_factory=get_chatbot_client,
        )
        logger.info("revy-trafego: meta ad_resolver worker ON")
        if settings.revy_control_provisioning_delivery_enabled:
            from app.control import provisioning_job

            provisioning_job.start_worker(SessionLocal)
            logger.info("revy-trafego: provisioning delivery worker ON")
        if settings.google_conversions_enabled:
            from app.control import google_ads_conversions_job

            google_ads_conversions_job.start_worker(SessionLocal)
            logger.info("revy-trafego: google conversions outbox worker ON")
        if (
            settings.google_ads_sync_enabled
            or settings.google_ads_metrics_worker_enabled
        ):
            # Força o flag do worker (default off) quando SYNC ou worker explicit on.
            os.environ["GOOGLE_ADS_METRICS_WORKER_ENABLED"] = "1"
            from app.control import google_ads_metrics_job

            google_ads_metrics_job.start_worker(SessionLocal)
            logger.info("revy-trafego: google ads metrics worker ON")
        db = SessionLocal()
        try:
            bootstrap_gestor_se_vazio(
                db,
                email=settings.bootstrap_email,
                senha=settings.bootstrap_senha,
                nome=settings.bootstrap_nome,
            )
        finally:
            db.close()
    try:
        yield
    finally:
        meta_ads_spend_job.stop_worker()
        meta_capi_job.stop_worker()
        from app import meta_ad_resolver_job
        from app.control import provisioning_job
        from app.control import google_ads_conversions_job
        from app.control import google_ads_metrics_job

        meta_ad_resolver_job.stop_worker()
        provisioning_job.stop_worker()
        google_ads_conversions_job.stop_worker()
        google_ads_metrics_job.stop_worker()


app = FastAPI(
    title="Revy Tráfego",
    docs_url=None,
    redoc_url=None,
    lifespan=_lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="revy_trafego_session",
    https_only=settings.secure_cookie,
    same_site="lax",
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(api_v1_router)
app.include_router(control_router)
app.include_router(control_ui_router)


def public_path(path: str) -> str:
    """Path absoluto com REVY_TRAFEGO_URL_PREFIX (ex.: /trafego/app)."""
    if path is None:
        path = "/"
    path = str(path)
    if not path.startswith("/"):
        path = "/" + path
    prefix = settings.url_prefix
    return f"{prefix}{path}" if prefix else path


def redirect(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(public_path(path), status_code=status_code)


def url_telefone(telefone: str | None) -> str:
    """Telefone seguro para path (evita quebrar com + / espaços)."""
    return quote((telefone or "").strip(), safe="")


def mascarar_telefone(telefone: str | None) -> str:
    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    if len(digitos) < 4:
        return "•••"
    return f"•••• {digitos[-4:]}"


def formatar_horario(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        from datetime import datetime

        momento = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return momento.strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return str(iso)[:16]


def formatar_brl(valor) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    texto = f"{numero:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


templates.env.globals["mascarar_telefone"] = mascarar_telefone
templates.env.globals["formatar_horario"] = formatar_horario
templates.env.globals["formatar_brl"] = formatar_brl
templates.env.globals["url_prefix"] = settings.url_prefix
templates.env.globals["public_path"] = public_path
templates.env.globals["url_telefone"] = url_telefone


def get_chatbot_client(loja_slug: str) -> ChatbotClient:
    return ChatbotClient(
        settings.chatbot_url,
        settings.chatbot_token_para(loja_slug),
        settings.request_timeout,
    )


def contexto(request: Request, usuario=None, db: Session | None = None, **extra):
    lojas = extra.pop("lojas", None)
    if lojas is None:
        if settings.revy_control_rbac_enabled and usuario is not None:
            lojas = visible_stores(SessionLocal, usuario)
        elif db is not None:
            lojas = listar_loja_slugs(db)
        else:
            # Dropdown de loja em todas as telas autenticadas.
            sess = SessionLocal()
            try:
                lojas = listar_loja_slugs(sess)
            finally:
                sess.close()
    return {
        "request": request,
        "usuario": usuario,
        "csrf": csrf_token(request) if usuario else "",
        "lojas": lojas or [],
        "control_enabled": settings.revy_control_enabled,
        "control_rbac_enabled": settings.revy_control_rbac_enabled,
        "control_dashboard_enabled": (
            settings.revy_control_enabled
            and settings.revy_control_dashboard_enabled
        ),
        **extra,
    }


def redirecionar_login():
    return redirect("/login")


def exigir_loja(request: Request, db: Session):
    """Retorna (gestor_sessao, redirect) — redirect se faltar auth ou loja."""
    gestor = gestor_atual(request, db)
    if not gestor:
        return None, redirecionar_login()
    if settings.revy_control_rbac_enabled:
        try:
            authorized = current_store(request, SessionLocal, gestor)
        except StoreNotFound:
            return None, Response(status_code=404)
        if authorized is None:
            return None, redirect("/app?erro=loja")
    usuario = sessao_gestor(request, db)
    assert usuario is not None
    if not usuario.loja_slug:
        return None, redirect("/app?erro=loja")
    return usuario, None


@app.get("/health/live")
def health_live():
    return {"status": "ok", "service": "revy-trafego", "version": settings.version}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1 FROM vendas_projetadas LIMIT 1"))
    return {"status": "ready", "service": "revy-trafego"}


@app.get("/public/v1/lojas/{loja_slug}/pixel")
def public_pixel_da_loja(loja_slug: str, db: Session = Depends(get_db)):
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
    config = db.query(MetaPixelConfig).filter(MetaPixelConfig.loja_slug == slug).first()
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
    return redirect("/app", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, db: Session = Depends(get_db)):
    if gestor_atual(request, db):
        return redirect("/app", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "erro": None, "csrf": csrf_token(request)},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    gestor = autenticar(db, form.get("email") or "", form.get("senha") or "")
    if not gestor:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "erro": "E-mail ou senha inválidos.",
                "csrf": csrf_token(request),
            },
            status_code=401,
        )
    iniciar_sessao(request, gestor)
    return redirect("/app", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    form = await request.form()
    if csrf_valido(request, form.get("csrf")):
        encerrar_sessao(request)
    return redirect("/login", status_code=303)


@app.get("/app", response_class=HTMLResponse)
def app_home(request: Request, db: Session = Depends(get_db)):
    gestor = gestor_atual(request, db)
    if not gestor:
        return redirecionar_login()
    usuario = sessao_gestor(request, db)
    assert usuario is not None
    lojas = (
        visible_stores(SessionLocal, gestor)
        if settings.revy_control_rbac_enabled
        else listar_loja_slugs(db)
    )
    # Se só há uma loja e nenhuma selecionada, pré-seleciona no dropdown.
    if settings.revy_control_rbac_enabled:
        loja_sel = usuario.loja_slug or (
            lojas[0].store.slug if len(lojas) == 1 else None
        )
    else:
        loja_sel = usuario.loja_slug or (lojas[0] if len(lojas) == 1 else None)
    return templates.TemplateResponse(
        "home.html",
        contexto(
            request,
            usuario,
            lojas=lojas,
            loja_selecionada=loja_sel,
            erro=request.query_params.get("erro"),
        ),
    )


@app.post("/app/loja")
async def app_selecionar_loja(request: Request, db: Session = Depends(get_db)):
    gestor = gestor_atual(request, db)
    if not gestor:
        return redirecionar_login()
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    if settings.revy_control_rbac_enabled:
        store_id = (form.get("loja_id") or "").strip()
        if not store_id:
            return redirect("/app?erro=loja", status_code=303)
        try:
            select_store(request, SessionLocal, gestor, store_id)
        except StoreNotFound:
            return Response(status_code=404)
        next_path = (form.get("next") or "").strip()
        if next_path.startswith("/app"):
            return redirect(next_path, status_code=303)
        return redirect("/app/trafego", status_code=303)
    slug = (form.get("loja_slug") or form.get("loja_slug_manual") or "").strip()
    if slug == "__manual__":
        slug = (form.get("loja_slug_manual") or "").strip()
    # Permite digitar loja nova (ainda sem campanhas) para bootstrap.
    if not slug or slug == "__manual__" or len(slug) > 120:
        return redirect("/app?erro=loja", status_code=303)
    definir_loja(request, slug)
    next_path = (form.get("next") or "").strip()
    if next_path.startswith("/app"):
        return redirect(next_path, status_code=303)
    return redirect("/app/trafego", status_code=303)


# ---------- Tráfego / Pixel / Ads ----------


def _trafego_contexto(request, usuario, config, *, ads_config=None, ultimo_outbox=None, pendentes=0, ok=None, erro=None, sync_resumo=None):
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


@app.get("/app/trafego", response_class=HTMLResponse)
def trafego_pagina(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    config = db.query(MetaPixelConfig).filter(MetaPixelConfig.loja_slug == usuario.loja_slug).first()
    ads_config = db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == usuario.loja_slug).first()
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
            ok=request.query_params.get("ok"),
        ),
    )


@app.post("/app/trafego")
async def trafego_salvar(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    pixel_id = normalizar_pixel_id((form.get("pixel_id") or "").strip())
    token_novo = (form.get("capi_token") or "").strip()
    test_event_code = (form.get("test_event_code") or "").strip() or None
    enviar_page_view = form.get("enviar_page_view") == "on"
    enviar_lead = form.get("enviar_lead") == "on"
    enviar_purchase = form.get("enviar_purchase") == "on"
    config = db.query(MetaPixelConfig).filter(MetaPixelConfig.loja_slug == usuario.loja_slug).first()
    ads_config = db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == usuario.loja_slug).first()
    if not pixel_id:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request, usuario, config, ads_config=ads_config,
                erro="Informe um Pixel ID válido, contendo somente números.",
            ),
            status_code=422,
        )
    if not token_novo and not (config and config.token_ciphertext):
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request, usuario, config, ads_config=ads_config,
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
    return redirect("/app/trafego?ok=salvo", status_code=303)


@app.post("/app/trafego/ads/salvar")
async def trafego_ads_salvar(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    ads_config = db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == usuario.loja_slug).first()
    config = db.query(MetaPixelConfig).filter(MetaPixelConfig.loja_slug == usuario.loja_slug).first()
    account = normalizar_ad_account_id(form.get("ad_account_id"))
    token_novo = (form.get("ads_token") or "").strip()
    sync_enabled = form.get("ads_sync_enabled") == "on"
    if not account:
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request, usuario, config, ads_config=ads_config,
                erro="Informe o ID da conta de anúncios Meta (act_… ou só números).",
            ),
            status_code=422,
        )
    if not token_novo and not (ads_config and ads_config.token_ciphertext):
        return templates.TemplateResponse(
            "trafego/form.html",
            _trafego_contexto(
                request, usuario, config, ads_config=ads_config,
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
    return redirect("/app/trafego?ok=ads-salvo", status_code=303)


@app.post("/app/trafego/ads/sincronizar")
async def trafego_ads_sincronizar(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    result = sincronizar_gastos_meta(db, usuario.loja_slug, janela_dias=7)
    if result.status == "erro":
        return redirect("/app/trafego?ok=sync-erro", status_code=303)
    return redirect("/app/trafego?ok=sync-ok", status_code=303)


@app.post("/app/trafego/capi/retentar")
async def trafego_capi_retentar(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    resultado = processar_outbox_pendentes(db, usuario.loja_slug)
    return redirect(
        f"/app/trafego?ok=retry-{resultado['entregues']}-{resultado['falharam']}",
    )


@app.get("/app/trafego/pixel-auditoria", response_class=HTMLResponse)
def trafego_pixel_auditoria(request: Request, db: Session = Depends(get_db), origem: str | None = None):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    from app.pixel_capi_auditoria import listar_auditoria_pixel

    origem_filtro = (origem or "").strip() or None
    itens = listar_auditoria_pixel(db, usuario.loja_slug, limit=100, origem=origem_filtro)
    return templates.TemplateResponse(
        "trafego/pixel_auditoria.html",
        contexto(request, usuario, itens=itens, origem_filtro=origem_filtro or ""),
    )


@app.get("/app/trafego/ctwa-auditoria", response_class=HTMLResponse)
def trafego_ctwa_auditoria(
    request: Request,
    db: Session = Depends(get_db),
    so_com_clid: str | None = None,
):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    chatbot = get_chatbot_client(usuario.loja_slug)
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


@app.get("/app/trafego/roi", response_class=HTMLResponse)
def trafego_roi(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    touch: str | None = None,
    db: Session = Depends(get_db),
):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    d_inicio, d_fim = periodo_padrao(inicio, fim)
    modo = touch if touch in ("first", "last") else "last"
    campanhas = db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
    gastos = db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all()
    metricas = calcular_metricas_vendas(db, usuario.loja_slug, d_inicio, d_fim)
    chatbot_erro = None
    leads: list[dict] = []
    try:
        leads = get_chatbot_client(usuario.loja_slug).listar_leads()
    except ChatbotIndisponivel:
        chatbot_erro = "indisponivel"
    from app.meta_ad_resolver_job import mapa_ad_campaign_loja

    mapa_ad = mapa_ad_campaign_loja(db, usuario.loja_slug)
    linhas = calcular_roi_loja(
        campanhas=campanhas,
        gastos=gastos,
        leads=leads,
        vendas_confirmadas=metricas["confirmadas"],
        d_inicio=d_inicio,
        d_fim=d_fim,
        modo_atribuicao=modo,
        mapa_ad_campaign=mapa_ad,
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


# ---------- Campanhas ----------


@app.get("/app/campanhas", response_class=HTMLResponse)
def campanhas_lista(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug)
        .order_by(Campanha.criada_em.desc())
        .all()
    )
    gastos_totais: dict[str, Decimal] = {}
    for g in db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == usuario.loja_slug).all():
        gastos_totais[g.campanha_id] = gastos_totais.get(g.campanha_id, Decimal("0")) + g.valor
    # Mensagens = leads CTWA atribuídos (last-touch, mesmo critério do ROI).
    # Custo/msg = gasto total / mensagens.
    mensagens_totais: dict[str, int] = {}
    custo_por_msg: dict[str, Decimal] = {}
    chatbot_erro = None
    try:
        leads = get_chatbot_client(usuario.loja_slug).listar_leads()
    except ChatbotIndisponivel:
        leads = []
        chatbot_erro = "indisponivel"
    for c in campanhas:
        n = sum(1 for l in leads if lead_casa_campanha(l, c, modo="last"))
        mensagens_totais[c.id] = n
        if n > 0:
            custo_por_msg[c.id] = (gastos_totais.get(c.id, Decimal("0")) / n).quantize(
                Decimal("0.01")
            )
    return templates.TemplateResponse(
        "campanhas/lista.html",
        contexto(
            request,
            usuario,
            campanhas=campanhas,
            gastos_totais=gastos_totais,
            mensagens_totais=mensagens_totais,
            custo_por_msg=custo_por_msg,
            chatbot_erro=chatbot_erro,
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
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    return templates.TemplateResponse(
        "campanhas/form.html",
        _campanha_form_ctx(
            request, usuario, titulo="Nova campanha", valores={"canal": "meta", "status": "ativa"}
        ),
    )


@app.post("/app/campanhas/nova")
async def campanhas_nova_post(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
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
    return redirect("/app/campanhas?ok=criada", status_code=303)


@app.get("/app/campanhas/gastos/lote", response_class=HTMLResponse)
def campanhas_gastos_lote_get(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug, Campanha.status == "ativa")
        .order_by(Campanha.nome)
        .all()
    )
    return templates.TemplateResponse(
        "campanhas/gastos_lote.html",
        contexto(
            request,
            usuario,
            campanhas=campanhas,
            hoje=hoje_portal().isoformat(),
            canais=CANAIS_ROTULO,
            erro=None,
            relatorio=None,
        ),
    )


@app.post("/app/campanhas/gastos/lote")
async def campanhas_gastos_lote_post(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    try:
        referencia = date.fromisoformat((form.get("referencia") or "").strip())
    except ValueError:
        referencia = None
    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == usuario.loja_slug, Campanha.status == "ativa")
        .order_by(Campanha.nome)
        .all()
    )
    if referencia is None:
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            contexto(
                request, usuario, campanhas=campanhas, hoje=hoje_portal().isoformat(),
                canais=CANAIS_ROTULO, erro="Informe uma data de referência válida.", relatorio=None,
            ),
            status_code=422,
        )
    nota_global = (form.get("nota_global") or "").strip()[:240] or None
    novos: list = []
    for campanha in campanhas:
        texto_valor = (form.get(f"valor_{campanha.id}") or "").strip()
        if not texto_valor:
            continue
        valor = parse_brl_valor(texto_valor)
        if valor is None or valor <= 0:
            return templates.TemplateResponse(
                "campanhas/gastos_lote.html",
                contexto(
                    request, usuario, campanhas=campanhas, hoje=hoje_portal().isoformat(),
                    canais=CANAIS_ROTULO,
                    erro=f"Informe um valor maior que zero para {campanha.nome}.",
                    relatorio=None,
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
    return redirect(f"/app/campanhas/gastos/lote?ok={len(novos)}")


@app.get("/app/campanhas/gastos/csv/modelo")
def campanhas_gastos_csv_modelo(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    conteudo = "\ufeffutm_campaign;valor;referencia;nota\n"
    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo-gastos-revy.csv"'},
    )


@app.post("/app/campanhas/gastos/csv", response_class=HTMLResponse)
async def campanhas_gastos_csv_post(request: Request, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    arquivo = form.get("arquivo")
    campanhas = db.query(Campanha).filter(Campanha.loja_slug == usuario.loja_slug).all()
    if arquivo is None or not hasattr(arquivo, "read"):
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            contexto(
                request, usuario, campanhas=campanhas, hoje=hoje_portal().isoformat(),
                canais=CANAIS_ROTULO, erro="Selecione um arquivo CSV.", relatorio=None,
            ),
            status_code=422,
        )
    conteudo = await arquivo.read()
    if len(conteudo) > 1024 * 1024:
        return templates.TemplateResponse(
            "campanhas/gastos_lote.html",
            contexto(
                request, usuario, campanhas=campanhas, hoje=hoje_portal().isoformat(),
                canais=CANAIS_ROTULO, erro="O CSV deve ter no máximo 1 MB.", relatorio=None,
            ),
            status_code=413,
        )
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
        contexto(
            request,
            usuario,
            campanhas=campanhas,
            hoje=hoje_portal().isoformat(),
            canais=CANAIS_ROTULO,
            erro=None,
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
):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    chatbot = get_chatbot_client(usuario.loja_slug)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return redirect("/app/campanhas?erro=1", status_code=303)
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
    from app.meta_ad_resolver_job import mapa_ad_campaign_loja

    mapa_ad = mapa_ad_campaign_loja(db, usuario.loja_slug)
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
            mapa_ad_campaign=mapa_ad,
        )
        if linha.campanha_id == campanha.id
    )
    vendas_atribuidas = [
        venda
        for venda in metricas_vendas["confirmadas"]
        if venda_casa_campanha(venda, campanha, modo="last")
    ]
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
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return redirect("/app/campanhas?erro=1", status_code=303)
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
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return redirect("/app/campanhas?erro=1", status_code=303)
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
    return redirect(f"/app/campanhas/{campanha.id}?ok=salvo")


@app.post("/app/campanhas/{campanha_id}/apagar")
async def campanhas_apagar_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return redirect("/app/campanhas?erro=1", status_code=303)
    db.delete(campanha)
    db.commit()
    return redirect("/app/campanhas?ok=apagada", status_code=303)


@app.post("/app/campanhas/{campanha_id}/gastos")
async def campanhas_gasto_post(request: Request, campanha_id: str, db: Session = Depends(get_db)):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return redirect("/app", status_code=303)
    campanha = (
        db.query(Campanha)
        .filter(Campanha.id == campanha_id, Campanha.loja_slug == usuario.loja_slug)
        .first()
    )
    if not campanha:
        return redirect("/app/campanhas?erro=1", status_code=303)
    valor = parse_brl_valor(form.get("valor"))
    try:
        referencia = date.fromisoformat((form.get("referencia") or "").strip())
    except ValueError:
        referencia = None
    if valor is None or referencia is None:
        return redirect(
            f"/app/campanhas/{campanha.id}?erro=Informe+valor+e+data+válidos",
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
    return redirect(f"/app/campanhas/{campanha.id}?ok=gasto")


# ---------- Diagnóstico ----------


@app.get("/app/diagnostico/leads", response_class=HTMLResponse)
def diagnostico_leads(
    request: Request,
    db: Session = Depends(get_db),
    utm: str | None = None,
):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    chatbot = get_chatbot_client(usuario.loja_slug)
    leads: list[dict] = []
    erro = None
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel:
        erro = "Chatbot indisponível."
    filtro = (utm or "").strip().casefold()
    if filtro:
        leads = [
            l
            for l in leads
            if filtro
            in (
                (l.get("utm_campaign") or "")
                + (l.get("utm_campaign_last") or "")
                + (l.get("utm_campaign_first") or "")
            ).casefold()
        ]
    registrar_audit(
        db,
        gestor_email=usuario.email,
        loja_slug=usuario.loja_slug,
        acao="listar_leads",
        recurso_id=filtro or None,
    )
    return templates.TemplateResponse(
        "diagnostico/leads.html",
        contexto(request, usuario, leads=leads[:200], erro=erro, utm=utm or ""),
    )


@app.get("/app/diagnostico/leads/{lead_id}", response_class=HTMLResponse)
def diagnostico_lead_detalhe(
    request: Request,
    lead_id: str,
    db: Session = Depends(get_db),
):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    chatbot = get_chatbot_client(usuario.loja_slug)
    lead = None
    erro = None
    try:
        lead = chatbot.obter_lead(lead_id)
    except LeadNaoEncontrado:
        erro = "Lead não encontrado."
    except ChatbotIndisponivel:
        erro = "Chatbot indisponível."
    registrar_audit(
        db,
        gestor_email=usuario.email,
        loja_slug=usuario.loja_slug,
        acao="ver_lead",
        recurso_id=lead_id,
    )
    return templates.TemplateResponse(
        "diagnostico/lead_detalhe.html",
        contexto(request, usuario, lead=lead, erro=erro),
    )


@app.get("/app/diagnostico/conversas/{telefone}", response_class=HTMLResponse)
def diagnostico_conversa(
    request: Request,
    telefone: str,
    db: Session = Depends(get_db),
):
    usuario, redir = exigir_loja(request, db)
    if redir:
        return redir
    chatbot = get_chatbot_client(usuario.loja_slug)
    mensagens: list[dict] = []
    erro = None
    # Path pode vir URL-encoded (+ → %2B etc.)
    from urllib.parse import unquote

    tel = unquote(telefone or "").strip()
    try:
        mensagens = chatbot.listar_mensagens(tel)
    except ConversaNaoEncontrada:
        erro = "Conversa não encontrada para este telefone."
    except ChatbotIndisponivel:
        erro = "Chatbot indisponível."
    except Exception:
        erro = "Erro ao carregar conversa."
    registrar_audit(
        db,
        gestor_email=usuario.email,
        loja_slug=usuario.loja_slug,
        acao="ver_conversa",
        recurso_id=tel,
    )
    return templates.TemplateResponse(
        "diagnostico/conversa.html",
        contexto(request, usuario, telefone=tel, mensagens=mensagens, erro=erro),
    )


def _authorize_job_token(x_job_token: str) -> JSONResponse | None:
    """Auth compartilhada dos POST /internal/jobs/* (X-Job-Token).

    Retorna JSONResponse de erro ou None se autorizado.
    """
    esperado = settings.job_secret or (
        os.getenv("PORTAL_META_SPEND_JOB_SECRET") or ""
    ).strip()
    if not esperado:
        return JSONResponse(
            {"detail": "job desabilitado (REVY_TRAFEGO_JOB_SECRET vazio)"},
            status_code=503,
        )
    if not secrets.compare_digest(x_job_token or "", esperado):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)
    return None


@app.post("/internal/jobs/meta-spend-sync")
def job_meta_spend_sync(x_job_token: str = Header(default="", alias="X-Job-Token")):
    denied = _authorize_job_token(x_job_token)
    if denied is not None:
        return denied
    worker = meta_ads_spend_job.get_worker()
    if worker is None:
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


@app.post("/internal/jobs/google-conversions-outbox")
def job_google_conversions_outbox(
    x_job_token: str = Header(default="", alias="X-Job-Token"),
):
    denied = _authorize_job_token(x_job_token)
    if denied is not None:
        return denied
    from app.control import google_ads_conversions_job

    worker = google_ads_conversions_job.get_worker()
    if worker is None:
        runner = google_ads_conversions_job.GoogleAdsConversionsWorker(
            db_factory=SessionLocal,
            enabled=True,
            interval_seconds=60,
            initial_delay_seconds=0,
        )
        payload = runner.run_once()
    else:
        payload = worker.run_once()
    return JSONResponse(payload)


@app.post("/internal/jobs/google-ads-metrics-sync")
def job_google_ads_metrics_sync(
    x_job_token: str = Header(default="", alias="X-Job-Token"),
):
    denied = _authorize_job_token(x_job_token)
    if denied is not None:
        return denied
    from app.control import google_ads_metrics_job

    worker = google_ads_metrics_job.get_worker()
    if worker is None:
        window = int(
            os.getenv("GOOGLE_ADS_METRICS_WORKER_TIME_WINDOW_DAYS", "7") or "7"
        )
        runner = google_ads_metrics_job.GoogleAdsMetricsSyncWorker(
            db_factory=SessionLocal,
            enabled=True,
            interval_seconds=86400,
            initial_delay_seconds=0,
            time_window_days=window,
        )
        payload = runner.run_once()
    else:
        payload = worker.run_once()
    return JSONResponse(payload)
