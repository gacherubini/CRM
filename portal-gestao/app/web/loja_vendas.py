"""Rotas Revy Loja — Vendas → Visão geral (Fase 3).

Ativadas somente com REVY_LOJA_SHELL_ENABLED=1. Com a flag off, retornam 404
para não alterar o shell legado em /app.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import (  # noqa: E402
    pode_ver_custo,
    pode_ver_resultados_midia,
    usuario_atual,
)
from app.config import settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.sales_overview import (  # noqa: E402
    PAPEIS_AUTORIZADOS,
    build_sales_overview,
)
from app.main import contexto, get_chatbot_client, redirecionar_login, templates  # noqa: E402
from app.models import Usuario  # noqa: E402


def _shell_desligado() -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def _papel_autorizado(usuario: Usuario) -> bool:
    return (usuario.papel or "").strip().casefold() in PAPEIS_AUTORIZADOS


def _fetch_resultados_api():
    """Callable opcional para a API Revy Tráfego / Control (read-only)."""
    if not settings.revy_trafego_resultados_enabled:
        return None
    from app.clients.revy_trafego import RevyTrafegoClient

    client = RevyTrafegoClient()

    def _fetch(*, loja_slug: str, periodo: str = "mes", modo: str = "last"):
        return client.fetch_resultados(
            loja_slug=loja_slug, periodo=periodo, modo=modo
        )

    return _fetch


def _montar_overview(
    usuario: Usuario,
    db: Session,
    chatbot,
    inicio: str | None,
    fim: str | None,
):
    papel = (usuario.papel or "").strip().casefold()
    fetch = _fetch_resultados_api() if pode_ver_resultados_midia(usuario) else None
    return build_sales_overview(
        db,
        loja_slug=usuario.loja_slug,
        papel=papel,
        vendedor_email=usuario.email if papel == "vendedor" else None,
        inicio=inicio,
        fim=fim,
        chatbot=chatbot,
        fetch_resultados_api=fetch,
        revy_trafego_resultados_enabled=settings.revy_trafego_resultados_enabled
        and pode_ver_resultados_midia(usuario),
        pode_ver_margem=pode_ver_custo(usuario),
    )


@router.get("/app/loja/vendas", response_class=HTMLResponse)
def loja_vendas_visao(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    if not settings.revy_loja_shell_enabled:
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _papel_autorizado(usuario):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    overview = _montar_overview(usuario, db, chatbot, inicio, fim)
    return templates.TemplateResponse(
        "loja/vendas_visao.html",
        contexto(
            request,
            usuario,
            overview=overview,
            periodo={
                "inicio": overview.periodo_inicio.isoformat(),
                "fim": overview.periodo_fim.isoformat(),
            },
            pode_ver_margem=pode_ver_custo(usuario),
            pode_ver_aquisicao=pode_ver_resultados_midia(usuario),
            shell_loja=True,
        ),
    )


@router.get("/app/loja/vendas/dados")
def loja_vendas_dados(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """JSON do mesmo read model — para smoke/integração sem template."""
    if not settings.revy_loja_shell_enabled:
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _papel_autorizado(usuario):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    overview = _montar_overview(usuario, db, chatbot, inicio, fim)
    return overview.to_dict()
