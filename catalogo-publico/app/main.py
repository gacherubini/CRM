import os
import re
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.events import InterestStore
from app.pixel import PixelResolver
from app.provider import HttpInventoryProvider, InventoryNotFound, InventoryUnavailable
from app.outbox import OutboxWorker
from app.provisioning import ProvisioningStore


BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def moeda(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def public_path(path: str) -> str:
    """Monta path absoluto com CATALOGO_URL_PREFIX (ex.: /loja/static/...)."""
    if not path.startswith("/"):
        path = "/" + path
    prefix = settings.url_prefix
    return f"{prefix}{path}" if prefix else path


templates.env.filters["moeda"] = moeda
templates.env.globals["url_prefix"] = settings.url_prefix
templates.env.globals["public_path"] = public_path


def _build_pixel_resolver() -> PixelResolver:
    return PixelResolver(
        settings.portal_public_url,
        timeout=settings.portal_pixel_timeout,
        cache_ttl=settings.portal_pixel_cache_ttl,
        fallback_pixel_id=settings.meta_pixel_id,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.interest_store.initialize()
    app.state.provisioning_store.initialize()
    app.state.pixel_resolver = _build_pixel_resolver()
    worker = OutboxWorker(
        app.state.interest_store,
        url=settings.events_url,
        token=settings.events_token,
        timeout=settings.events_timeout,
        max_attempts=settings.events_max_attempts,
        interval=settings.events_worker_interval,
    )
    worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="Catálogo Público", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.state.catalog_provider = HttpInventoryProvider(
    settings.inventory_url, settings.inventory_token, settings.provider_timeout
)
app.state.interest_store = InterestStore(settings.database_path)
app.state.provisioning_store = ProvisioningStore(settings.provisioning_db)
app.state.pixel_resolver = _build_pixel_resolver()


def _content_security_policy() -> str:
    # Google Fonts (Inter) + Meta Pixel opcional (Portal por loja ou env).
    style = "style-src 'self' https://fonts.googleapis.com; "
    font = "font-src 'self' https://fonts.gstatic.com data:; "
    if settings.meta_pixel_csp_needed:
        return (
            "default-src 'self'; "
            "img-src 'self' https: http: data:; "
            f"{style}{font}"
            "script-src 'self' 'unsafe-inline' https://connect.facebook.net; "
            "connect-src 'self' https://www.facebook.com https://connect.facebook.net; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
    return (
        "default-src 'self'; img-src 'self' https: http: data:; "
        f"{style}{font}"
        "base-uri 'none'; frame-ancestors 'none'"
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", _content_security_policy())
    return response


def get_pixel_resolver(request: Request) -> PixelResolver:
    resolver = getattr(request.app.state, "pixel_resolver", None)
    if resolver is None:
        resolver = _build_pixel_resolver()
        request.app.state.pixel_resolver = resolver
    return resolver


def pixel_context(loja_slug: Optional[str] = None, request: Optional[Request] = None) -> dict:
    """Pixel por loja: Portal (pull) com fallback META_PIXEL_ID."""
    if settings.meta_pixel_disabled:
        return {
            "meta_pixel_enabled": False,
            "meta_pixel_id": "",
            "meta_pixel_page_view_enabled": False,
            "meta_pixel_lead_enabled": False,
        }
    config = None
    resolver_slug = settings.portal_store_slug or loja_slug
    if request is not None and loja_slug:
        config = get_pixel_resolver(request).resolve_config(resolver_slug)
    elif loja_slug and getattr(app.state, "pixel_resolver", None):
        config = app.state.pixel_resolver.resolve_config(resolver_slug)
    else:
        config = _build_pixel_resolver().resolve_config("")
    pixel_id = (config.pixel_id or "").strip()
    enabled = bool(pixel_id) and config.enabled
    return {
        "meta_pixel_enabled": enabled,
        "meta_pixel_id": pixel_id if enabled else "",
        "meta_pixel_page_view_enabled": enabled and config.enviar_page_view,
        "meta_pixel_lead_enabled": enabled and config.enviar_lead,
    }


def get_provider(request: Request) -> HttpInventoryProvider:
    return request.app.state.catalog_provider


def get_interest_store(request: Request) -> InterestStore:
    return request.app.state.interest_store


def get_provisioning_store(request: Request) -> ProvisioningStore:
    return request.app.state.provisioning_store


def storefront_hidden(
    request: Request,
    slug: str,
    store: Optional[ProvisioningStore] = None,
) -> bool:
    """True quando a projeção do Control manda ocultar a vitrine (404/HIDE).

    Fail-open se não houver projeção — ver ``ProvisioningStore.allows_processing``.
    """
    prov = store or get_provisioning_store(request)
    return not prov.allows_processing(slug, module="estoque")


def hidden_store_page(request: Request, slug: str):
    """404 genérico: não revela suspensão/encerramento (ADR respostas estáveis)."""
    return error_page(
        request,
        404,
        "Loja não encontrada",
        "Confira o endereço da vitrine.",
        loja_slug=slug,
    )


def error_page(
    request: Request,
    status: int,
    title: str,
    message: str,
    loja_slug: Optional[str] = None,
):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "status": status,
            "title": title,
            "message": message,
            **pixel_context(loja_slug, request),
        },
        status_code=status,
    )


def clean_tracking(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", "", value).strip()[:120]


def clean_click_id(value: Optional[str]) -> str:
    """Click IDs Google (gclid/gbraid/wbraid): opacos, case-sensitive, sem normalizar.

    Apenas remove caracteres de controle e limita ao tamanho do contrato (255).
    """
    if not value:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", "", value).strip()[:255]


def normalize_whatsapp(value: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) in {10, 11}:
        digits = f"55{digits}"
    if not 10 <= len(digits) <= 15:
        return None
    return digits


def visitor_id(request: Request) -> tuple[str, bool]:
    current = request.cookies.get("catalog_visitor", "")
    try:
        return str(uuid.UUID(current)), False
    except (ValueError, TypeError):
        return str(uuid.uuid4()), True


def page_url(slug: str, filters: dict, offset: int, limit: int) -> str:
    params = {
        key: value
        for key, value in {**filters, "limit": limit, "offset": max(offset, 0)}.items()
        if value not in (None, "")
    }
    return public_path(f"/l/{slug}?{urlencode(params)}")


def pagination_window(
    current_page: int, total_pages: int, *, radius: int = 2
) -> list[int | None]:
    """Lista de páginas para a UI; ``None`` representa reticências.

    Ex.: página 5 de 12 com radius 1 → [1, None, 4, 5, 6, None, 12]
    """
    if total_pages <= 0:
        return []
    current_page = max(1, min(current_page, total_pages))
    if total_pages <= 1 + 2 * radius + 2:
        return list(range(1, total_pages + 1))

    pages: set[int] = {1, total_pages}
    for n in range(current_page - radius, current_page + radius + 1):
        if 1 <= n <= total_pages:
            pages.add(n)
    ordered = sorted(pages)
    result: list[int | None] = []
    prev = 0
    for n in ordered:
        if prev and n - prev > 1:
            result.append(None)
        result.append(n)
        prev = n
    return result


@app.get("/", include_in_schema=False)
def root_catalog():
    return RedirectResponse(
        public_path(f"/l/{settings.default_store_slug}"), status_code=307
    )


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(request: Request):
    store = get_interest_store(request)
    if not settings.inventory_url_valid or not store.ready():
        return JSONResponse({"status": "indisponivel"}, status_code=503)
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"versao": settings.version, "contrato_estoque": "public/v1"}


@app.post("/internal/v1/provisioning/state")
def receber_estado_provisionamento(
    request: Request,
    payload: dict,
    x_service_token: str = Header(default="", alias="X-Service-Token"),
):
    """Recebe snapshot operacional do Control e aplica projeção monotônica local.

    Autentica com ``X-Service-Token`` vs ``CATALOGO_SERVICE_TOKEN`` (ou
    ``CATALOGO_PROVISIONING_TOKEN``). Token vazio → 503; incorreto → 401.
    Multi-tenant por ``loja_slug`` no body.
    """
    esperado = (
        os.getenv("CATALOGO_SERVICE_TOKEN")
        or os.getenv("CATALOGO_PROVISIONING_TOKEN")
        or settings.service_token
        or ""
    ).strip()
    if not esperado:
        return JSONResponse(
            {
                "detail": (
                    "provisioning desabilitado "
                    "(CATALOGO_SERVICE_TOKEN / CATALOGO_PROVISIONING_TOKEN vazio)"
                )
            },
            status_code=503,
        )
    if not secrets.compare_digest(x_service_token or "", esperado):
        return JSONResponse({"detail": "não autorizado"}, status_code=401)

    loja_slug = str(payload.get("loja_slug") or "").strip()
    if not loja_slug:
        return JSONResponse({"detail": "loja_slug obrigatório"}, status_code=422)

    store = get_provisioning_store(request)
    reasons = store.apply_payload(loja_slug, payload)
    return {
        "ok": True,
        "reasons": reasons,
        "allows_processing": store.allows_processing(
            loja_slug, module="estoque"
        ),
    }


@app.get("/l/{slug}", response_class=HTMLResponse)
def storefront(
    request: Request,
    slug: str,
    tipo: Optional[str] = Query(default=None, max_length=20),
    marca: Optional[str] = Query(default=None, max_length=80),
    preco_min: Optional[float] = Query(default=None, ge=0),
    preco_max: Optional[float] = Query(default=None, ge=0),
    limit: int = Query(default=settings.page_size, ge=1, le=48),
    offset: int = Query(default=0, ge=0),
    provider: HttpInventoryProvider = Depends(get_provider),
):
    if storefront_hidden(request, slug):
        return hidden_store_page(request, slug)

    filters = {
        "tipo": tipo or "",
        "marca": marca or "",
        "preco_min": preco_min,
        "preco_max": preco_max,
    }
    try:
        page = provider.list_vehicles(
            slug,
            tipo=tipo,
            marca=marca,
            preco_min=preco_min,
            preco_max=preco_max,
            limit=limit,
            offset=offset,
        )
    except InventoryNotFound:
        return error_page(
            request,
            404,
            "Loja não encontrada",
            "Confira o endereço da vitrine.",
            loja_slug=slug,
        )
    except InventoryUnavailable:
        return error_page(
            request,
            503,
            "Vitrine temporariamente indisponível",
            "Não foi possível consultar o estoque agora. Tente novamente em instantes.",
            loja_slug=slug,
        )

    total = int(page.paginacao.total or 0)
    # Fallback se o estoque ainda não enviar total: estima pelo offset + página.
    if total <= 0 and page.veiculos:
        total = offset + page.paginacao.quantidade
        if page.paginacao.quantidade >= limit:
            # Há possivelmente mais itens; não inventa total fechado.
            total = max(total, offset + limit + 1)
    elif total <= 0:
        total = 0

    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    current_page = (offset // limit) + 1 if limit else 1
    if total and current_page > total_pages:
        current_page = total_pages

    previous_url = page_url(slug, filters, offset - limit, limit) if offset else None
    has_next = (
        (offset + page.paginacao.quantidade) < total
        if total
        else page.paginacao.quantidade >= limit
    )
    next_url = (
        page_url(slug, filters, offset + limit, limit) if has_next else None
    )
    page_links = []
    for item in pagination_window(current_page, total_pages if total else current_page):
        if item is None:
            page_links.append({"kind": "ellipsis"})
        else:
            page_links.append(
                {
                    "kind": "page",
                    "number": item,
                    "url": page_url(slug, filters, (item - 1) * limit, limit),
                    "current": item == current_page,
                }
            )

    showing_from = offset + 1 if page.veiculos else 0
    showing_to = offset + len(page.veiculos)

    return templates.TemplateResponse(
        request,
        "storefront.html",
        {
            "request": request,
            "loja": page.loja,
            "veiculos": page.veiculos,
            "filters": filters,
            "limit": limit,
            "offset": offset,
            "previous_url": previous_url,
            "next_url": next_url,
            "page_links": page_links,
            "current_page": current_page,
            "total_pages": total_pages if total else (current_page if has_next else 1),
            "total_items": total,
            "showing_from": showing_from,
            "showing_to": showing_to,
            **pixel_context(slug, request),
        },
    )


@app.get("/l/{slug}/veiculos/{vehicle_id}", response_class=HTMLResponse)
def vehicle_detail(
    request: Request,
    slug: str,
    vehicle_id: str,
    provider: HttpInventoryProvider = Depends(get_provider),
):
    if storefront_hidden(request, slug):
        return hidden_store_page(request, slug)

    try:
        store = provider.get_store(slug)
        vehicle = provider.get_vehicle(slug, vehicle_id)
    except InventoryNotFound:
        return error_page(
            request,
            404,
            "Veículo não encontrado",
            "Ele pode não estar mais disponível.",
            loja_slug=slug,
        )
    except InventoryUnavailable:
        return error_page(
            request,
            503,
            "Detalhe temporariamente indisponível",
            "Não foi possível consultar o estoque agora. Tente novamente em instantes.",
            loja_slug=slug,
        )

    tracking = {
        key: clean_tracking(request.query_params.get(key))
        for key in (
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "fbclid",
        )
    }
    for key in ("gclid", "gbraid", "wbraid"):
        tracking[key] = clean_click_id(request.query_params.get(key))
    tracking["origem"] = "detalhe_catalogo"
    # event_id compartilhado browser Lead ↔ registro de interesse (dedupe Meta).
    lead_event_id = str(uuid.uuid4())
    tracking["event_id"] = lead_event_id
    interest_url = public_path(
        f"/l/{slug}/interesse/{vehicle_id}?{urlencode(tracking)}"
    )
    return templates.TemplateResponse(
        request,
        "vehicle.html",
        {
            "request": request,
            "loja": store,
            "veiculo": vehicle,
            "interest_url": interest_url,
            "whatsapp_disponivel": bool(normalize_whatsapp(store.whatsapp)),
            "lead_event_id": lead_event_id,
            **pixel_context(slug, request),
        },
    )


@app.get("/l/{slug}/interesse/{vehicle_id}")
def register_interest(
    request: Request,
    slug: str,
    vehicle_id: str,
    origem: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_term: Optional[str] = None,
    fbclid: Optional[str] = None,
    gclid: Optional[str] = None,
    gbraid: Optional[str] = None,
    wbraid: Optional[str] = None,
    event_id: Optional[str] = None,
    provider: HttpInventoryProvider = Depends(get_provider),
    store: InterestStore = Depends(get_interest_store),
):
    if storefront_hidden(request, slug):
        return hidden_store_page(request, slug)

    try:
        public_store = provider.get_store(slug)
        vehicle = provider.get_vehicle(slug, vehicle_id)
    except InventoryNotFound:
        return error_page(
            request,
            404,
            "Veículo não encontrado",
            "Ele pode não estar mais disponível.",
            loja_slug=slug,
        )
    except InventoryUnavailable:
        return error_page(
            request,
            503,
            "Contato temporariamente indisponível",
            "Não foi possível confirmar os dados do veículo agora.",
            loja_slug=slug,
        )

    phone = normalize_whatsapp(public_store.whatsapp)
    if not phone:
        return error_page(
            request,
            422,
            "WhatsApp indisponível",
            "Esta loja ainda não configurou um número de WhatsApp válido.",
            loja_slug=slug,
        )

    anonymous_id, is_new = visitor_id(request)
    shared_event_id = clean_tracking(event_id)
    try:
        uuid.UUID(shared_event_id)
    except (ValueError, TypeError):
        shared_event_id = ""
    try:
        interest = store.record(
            loja_slug=public_store.slug,
            veiculo_id=vehicle.id,
            visitante_id=anonymous_id,
            origem=clean_tracking(origem),
            utm_source=clean_tracking(utm_source),
            utm_medium=clean_tracking(utm_medium),
            utm_campaign=clean_tracking(utm_campaign),
            utm_content=clean_tracking(utm_content),
            utm_term=clean_tracking(utm_term),
            fbclid=clean_tracking(fbclid),
            gclid=clean_click_id(gclid),
            gbraid=clean_click_id(gbraid),
            wbraid=clean_click_id(wbraid),
            event_id=shared_event_id or None,
        )
    except sqlite3.Error:
        return error_page(
            request,
            503,
            "Contato temporariamente indisponível",
            "Não foi possível registrar seu interesse agora.",
        )

    message = (
        f"Olá! Tenho interesse no {vehicle.marca} {vehicle.modelo} "
        f"{vehicle.ano_modelo}. Código do interesse: {interest.public_ref}. "
        f"Referência do veículo: {vehicle.id}"
    )
    response = RedirectResponse(
        f"https://wa.me/{phone}?{urlencode({'text': message})}", status_code=302
    )
    if is_new:
        response.set_cookie(
            "catalog_visitor",
            anonymous_id,
            max_age=60 * 60 * 24 * 180,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="lax",
        )
    return response
