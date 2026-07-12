import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.events import InterestStore
from app.provider import HttpInventoryProvider, InventoryNotFound, InventoryUnavailable


BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def moeda(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


templates.env.filters["moeda"] = moeda


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.interest_store.initialize()
    yield


app = FastAPI(title="Catálogo Público", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.state.catalog_provider = HttpInventoryProvider(
    settings.inventory_url, settings.inventory_token, settings.provider_timeout
)
app.state.interest_store = InterestStore(settings.database_path)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: http: data:; "
        "style-src 'self'; base-uri 'none'; frame-ancestors 'none'",
    )
    return response


def get_provider(request: Request) -> HttpInventoryProvider:
    return request.app.state.catalog_provider


def get_interest_store(request: Request) -> InterestStore:
    return request.app.state.interest_store


def error_page(request: Request, status: int, title: str, message: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"request": request, "status": status, "title": title, "message": message},
        status_code=status,
    )


def clean_tracking(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", "", value).strip()[:120]


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
    return f"/l/{slug}?{urlencode(params)}"


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
        return error_page(request, 404, "Loja não encontrada", "Confira o endereço da vitrine.")
    except InventoryUnavailable:
        return error_page(
            request,
            503,
            "Vitrine temporariamente indisponível",
            "Não foi possível consultar o estoque agora. Tente novamente em instantes.",
        )

    previous_url = page_url(slug, filters, offset - limit, limit) if offset else None
    next_url = (
        page_url(slug, filters, offset + limit, limit)
        if page.paginacao.quantidade >= limit
        else None
    )
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
        },
    )


@app.get("/l/{slug}/veiculos/{vehicle_id}", response_class=HTMLResponse)
def vehicle_detail(
    request: Request,
    slug: str,
    vehicle_id: str,
    provider: HttpInventoryProvider = Depends(get_provider),
):
    try:
        store = provider.get_store(slug)
        vehicle = provider.get_vehicle(slug, vehicle_id)
    except InventoryNotFound:
        return error_page(
            request, 404, "Veículo não encontrado", "Ele pode não estar mais disponível."
        )
    except InventoryUnavailable:
        return error_page(
            request,
            503,
            "Detalhe temporariamente indisponível",
            "Não foi possível consultar o estoque agora. Tente novamente em instantes.",
        )

    tracking = {
        key: clean_tracking(request.query_params.get(key))
        for key in ("utm_source", "utm_medium", "utm_campaign")
    }
    tracking["origem"] = "detalhe_catalogo"
    interest_url = f"/l/{slug}/interesse/{vehicle_id}?{urlencode(tracking)}"
    return templates.TemplateResponse(
        request,
        "vehicle.html",
        {
            "request": request,
            "loja": store,
            "veiculo": vehicle,
            "interest_url": interest_url,
            "whatsapp_disponivel": bool(normalize_whatsapp(store.whatsapp)),
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
    provider: HttpInventoryProvider = Depends(get_provider),
    store: InterestStore = Depends(get_interest_store),
):
    try:
        public_store = provider.get_store(slug)
        vehicle = provider.get_vehicle(slug, vehicle_id)
    except InventoryNotFound:
        return error_page(
            request, 404, "Veículo não encontrado", "Ele pode não estar mais disponível."
        )
    except InventoryUnavailable:
        return error_page(
            request,
            503,
            "Contato temporariamente indisponível",
            "Não foi possível confirmar os dados do veículo agora.",
        )

    phone = normalize_whatsapp(public_store.whatsapp)
    if not phone:
        return error_page(
            request,
            422,
            "WhatsApp indisponível",
            "Esta loja ainda não configurou um número de WhatsApp válido.",
        )

    anonymous_id, is_new = visitor_id(request)
    try:
        store.record(
            loja_slug=public_store.slug,
            veiculo_id=vehicle.id,
            visitante_id=anonymous_id,
            origem=clean_tracking(origem),
            utm_source=clean_tracking(utm_source),
            utm_medium=clean_tracking(utm_medium),
            utm_campaign=clean_tracking(utm_campaign),
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
        f"{vehicle.ano_modelo}. Referência: {vehicle.id}"
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
