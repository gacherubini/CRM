"""Rotas HTML do módulo Estoque no shell Revy Loja (Fase 2).

- ``GET /app/loja/estoque`` — visão geral (read model determinístico).
- ``GET /app/loja/estoque/veiculos`` — entrada para a lista/CRUD legado.
- ``GET/POST /app/loja/estoque/vitrine`` — ordem manual na vitrine pública.

Gated por ``REVY_LOJA_SHELL_ENABLED`` (default off). Rotas legadas
``/app/estoque*`` permanecem intactas: CRUD, fotos, publicar/despublicar,
reservar e vender continuam nelas até o cutover completo do shell.

Custo/margem: a visão geral não exibe esses campos; se no futuro forem
adicionados, reutilizar ``pode_ver_custo`` (vendedor não vê).
"""
from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import csrf_valido, pode_gerir_estoque, pode_ver_custo, usuario_atual
from app.clients.estoque import EstoqueClient, EstoqueIndisponivel, VeiculoNaoEncontrado
from app.config import revy_loja_shell_enabled
from app.db import get_db
from app.loja.estoque_overview import montar_estoque_overview

router = APIRouter()

# Import tardio de helpers do main (mesmo padrão de app.relatorios) — evita ciclo.
from app.main import (  # noqa: E402
    contexto,
    get_estoque_client,
    redirecionar_login,
    templates,
)

# Mesmo default do catálogo público (CATALOGO_PAGE_SIZE=12 → 3 colunas × 4 linhas).
_VITRINE_PAGE_SIZE = 12


def _shell_ativo() -> bool:
    return revy_loja_shell_enabled()


def _ordenar_vitrine(veiculos: list[dict]) -> list[dict]:
    return sorted(
        veiculos,
        key=lambda v: (
            int(v.get("ordem_vitrine") or 0),
            str(v.get("criado_em") or ""),
            str(v.get("id") or ""),
        ),
    )


def _pagination_window(
    current_page: int, total_pages: int, *, radius: int = 2
) -> list[int | None]:
    """Mesma janela do catálogo público; ``None`` = reticências."""
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


def _vitrine_page_url(offset: int, limit: int) -> str:
    qs = urlencode({"limit": limit, "offset": max(0, offset)})
    return f"/app/loja/estoque/vitrine?{qs}"


@router.get("/app/loja/estoque", response_class=HTMLResponse)
def loja_estoque_visao(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    """Visão geral consolidada do estoque (indicadores determinísticos)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _shell_ativo():
        # Flag off: não expõe shell novo; aponta para o estoque legado.
        return RedirectResponse("/app/estoque", status_code=303)

    veiculos: list[dict] | None = None
    erro: str | None = None
    try:
        veiculos = estoque.listar()
    except EstoqueIndisponivel as exc:
        erro = str(exc)
        veiculos = None

    overview = montar_estoque_overview(
        veiculos,
        erro=erro,
        pode_ver_custo=pode_ver_custo(usuario),
    )

    return templates.TemplateResponse(
        "loja/estoque_visao.html",
        contexto(
            request,
            usuario,
            overview=overview,
            pode_gerir=pode_gerir_estoque(usuario),
            # Documenta na UI que CRUD/publicação ficam no caminho legado.
            caminho_veiculos="/app/estoque",
            caminho_novo="/app/estoque/novo",
        ),
    )


@router.get("/app/loja/estoque/veiculos", response_class=HTMLResponse)
def loja_estoque_veiculos(
    request: Request,
    db: Session = Depends(get_db),
):
    """Entrada de Veículos: reutiliza a lista/CRUD legada até cutover completo.

    Publicar, despublicar, reservar, vender e edição de custo permanecem em
    ``/app/estoque*`` (Estoque API como fonte de verdade).
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _shell_ativo():
        return RedirectResponse("/app/estoque", status_code=303)

    # Preserva query string (filtros) ao redirecionar para o legado.
    qs = request.url.query
    destino = "/app/estoque"
    if qs:
        destino = f"{destino}?{qs}"
    return RedirectResponse(destino, status_code=303)


@router.get("/app/loja/estoque/vitrine", response_class=HTMLResponse)
def loja_estoque_vitrine(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
    limit: int = Query(default=_VITRINE_PAGE_SIZE, ge=1, le=48),
    offset: int = Query(default=0, ge=0),
):
    """Edição da ordem dos veículos publicados no catálogo público.

    Paginação alinhada ao catálogo (default 12 = 3 colunas × 4 linhas).
    A ordem salva é sempre a lista global; a página só mostra um recorte.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _shell_ativo():
        return RedirectResponse("/app/estoque", status_code=303)
    if not pode_gerir_estoque(usuario):
        return RedirectResponse("/app/loja/estoque", status_code=303)

    todos: list[dict] = []
    erro: str | None = request.session.pop("vitrine_erro", None)
    mensagem: str | None = request.session.pop("vitrine_mensagem", None)
    try:
        brutos = estoque.listar(publicado=True, status="disponivel")
        todos = _ordenar_vitrine(brutos)
    except EstoqueIndisponivel as exc:
        erro = str(exc)

    total = len(todos)
    if total and offset >= total:
        offset = max(0, ((total - 1) // limit) * limit)

    veiculos = todos[offset : offset + limit]
    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    current_page = (offset // limit) + 1 if limit else 1
    if total and current_page > total_pages:
        current_page = total_pages

    previous_url = _vitrine_page_url(offset - limit, limit) if offset else None
    has_next = (offset + len(veiculos)) < total
    next_url = _vitrine_page_url(offset + limit, limit) if has_next else None

    page_links: list[dict] = []
    for item in _pagination_window(current_page, total_pages if total else 1):
        if item is None:
            page_links.append({"kind": "ellipsis"})
        else:
            page_links.append(
                {
                    "kind": "page",
                    "number": item,
                    "url": _vitrine_page_url((item - 1) * limit, limit),
                    "current": item == current_page,
                }
            )

    showing_from = offset + 1 if veiculos else 0
    showing_to = offset + len(veiculos)
    all_ids = [str(v.get("id") or "") for v in todos if v.get("id")]

    return templates.TemplateResponse(
        "loja/vitrine_ordem.html",
        contexto(
            request,
            usuario,
            veiculos=veiculos,
            all_ids=all_ids,
            total_items=total,
            limit=limit,
            offset=offset,
            previous_url=previous_url,
            next_url=next_url,
            page_links=page_links,
            showing_from=showing_from,
            showing_to=showing_to,
            erro=erro,
            mensagem=mensagem,
            pode_gerir=True,
        ),
    )


@router.post("/app/loja/estoque/vitrine", response_class=HTMLResponse)
def loja_estoque_vitrine_salvar(
    request: Request,
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
    csrf: Annotated[str, Form()] = "",
    ordem_ids: Annotated[str, Form()] = "",
    limit: Annotated[int, Form()] = _VITRINE_PAGE_SIZE,
    offset: Annotated[int, Form()] = 0,
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if (
        not _shell_ativo()
        or not pode_gerir_estoque(usuario)
        or not csrf_valido(request, csrf)
    ):
        return RedirectResponse("/app/loja/estoque", status_code=303)

    try:
        limit_i = max(1, min(48, int(limit)))
    except (TypeError, ValueError):
        limit_i = _VITRINE_PAGE_SIZE
    try:
        offset_i = max(0, int(offset))
    except (TypeError, ValueError):
        offset_i = 0

    destino = _vitrine_page_url(offset_i, limit_i)
    ids = [parte.strip() for parte in (ordem_ids or "").split(",") if parte.strip()]
    if not ids:
        request.session["vitrine_erro"] = "Nenhuma ordem enviada."
        return RedirectResponse(destino, status_code=303)

    # Ordem global: posições 0..N-1 na lista completa.
    itens = [{"id": vid, "ordem_vitrine": indice} for indice, vid in enumerate(ids)]
    try:
        estoque.reordenar_vitrine(itens)
        request.session["vitrine_mensagem"] = "Ordem da vitrine salva."
    except VeiculoNaoEncontrado:
        request.session["vitrine_erro"] = "Algum veículo não foi encontrado no estoque."
    except EstoqueIndisponivel as exc:
        request.session["vitrine_erro"] = str(exc)

    return RedirectResponse(destino, status_code=303)
