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

from fastapi import APIRouter, Depends, Form, Request
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
):
    """Edição da ordem dos veículos publicados no catálogo público."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _shell_ativo():
        return RedirectResponse("/app/estoque", status_code=303)
    if not pode_gerir_estoque(usuario):
        return RedirectResponse("/app/loja/estoque", status_code=303)

    veiculos: list[dict] = []
    erro: str | None = request.session.pop("vitrine_erro", None)
    mensagem: str | None = request.session.pop("vitrine_mensagem", None)
    try:
        brutos = estoque.listar(publicado=True, status="disponivel")
        veiculos = _ordenar_vitrine(brutos)
    except EstoqueIndisponivel as exc:
        erro = str(exc)

    return templates.TemplateResponse(
        "loja/vitrine_ordem.html",
        contexto(
            request,
            usuario,
            veiculos=veiculos,
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

    ids = [parte.strip() for parte in (ordem_ids or "").split(",") if parte.strip()]
    if not ids:
        request.session["vitrine_erro"] = "Nenhuma ordem enviada."
        return RedirectResponse("/app/loja/estoque/vitrine", status_code=303)

    itens = [{"id": vid, "ordem_vitrine": indice} for indice, vid in enumerate(ids)]
    try:
        estoque.reordenar_vitrine(itens)
        request.session["vitrine_mensagem"] = "Ordem da vitrine salva."
    except VeiculoNaoEncontrado:
        request.session["vitrine_erro"] = "Algum veículo não foi encontrado no estoque."
    except EstoqueIndisponivel as exc:
        request.session["vitrine_erro"] = str(exc)

    return RedirectResponse("/app/loja/estoque/vitrine", status_code=303)
