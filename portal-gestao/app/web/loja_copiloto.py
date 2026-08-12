"""Rotas da seção Copiloto de Vendas (Revy Loja).

Gate quádruplo: shell + flag do Copiloto + entitlement do módulo + papel de
gestão. Com qualquer um faltando a seção NÃO EXISTE (404) — não redireciona.

Menu oculto não substitui checagem (app/loja/permissions.py:1): o entitlement
por loja (Module.COPILOTO) é resolvido e checado aqui, no servidor, com o
mesmo mecanismo que Estoque/Vendas usam (check_module_access) — não basta
esconder o item do nav quando a loja não contratou o módulo.

Nesta fase não há LLM nenhum: resumo determinístico + alertas de regra.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import usuario_atual  # noqa: E402
from app.config import revy_loja_copiloto_enabled, revy_loja_shell_enabled  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.copiloto.resumo import montar_resumo_hoje  # noqa: E402
from app.loja.copiloto.sinais_store import (  # noqa: E402
    contar_sinais_novos,
    dispensar,
    listar_sinais_abertos,
    marcar_visto,
)
from app.loja.copiloto.tipos import PAPEIS_GESTAO_COPILOTO, CopilotoContexto  # noqa: E402
from app.loja.types import Module  # noqa: E402
from app.main import (  # noqa: E402
    contexto,
    csrf_valido,
    get_chatbot_client,
    get_estoque_client,
    redirecionar_login,
    templates,
)
from app.models import Usuario  # noqa: E402
from app.web.loja_shell import check_module_access  # noqa: E402

_PAGINA = "/app/loja/copiloto"


def _secao_ativa() -> bool:
    # Lê env em runtime (evita snapshot de Settings poluído entre testes).
    return revy_loja_shell_enabled() and revy_loja_copiloto_enabled()


def _nao_existe() -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def _sem_permissao(request: Request, usuario: Usuario):
    return templates.TemplateResponse(
        "erro.html",
        contexto(request, usuario, erro="O Copiloto é do dono e do gerente da loja."),
        status_code=403,
    )


def _pode(usuario: Usuario) -> bool:
    return (usuario.papel or "").strip().casefold() in PAPEIS_GESTAO_COPILOTO


def _ctx(usuario: Usuario) -> CopilotoContexto:
    """loja_slug e papel SEMPRE da sessão — nunca de parâmetro de rota."""
    return CopilotoContexto(
        loja_slug=usuario.loja_slug,
        papel=usuario.papel,
        ator_email=usuario.email,
        hoje=datetime.now(timezone.utc).date(),
    )


@router.get(_PAGINA, response_class=HTMLResponse)
def copiloto_home(
    request: Request,
    db: Session = Depends(get_db),
    estoque=Depends(get_estoque_client),
    chatbot=Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _secao_ativa():
        return _nao_existe()
    blocked = check_module_access(request, usuario, db, Module.COPILOTO)
    if blocked is not None:
        return blocked
    if not _pode(usuario):
        return _sem_permissao(request, usuario)

    ctx = _ctx(usuario)
    resumo = montar_resumo_hoje(db, ctx, estoque=estoque, chatbot=chatbot)
    return templates.TemplateResponse(
        "loja/copiloto.html",
        contexto(
            request,
            usuario,
            db=db,
            resumo=resumo,
            sinais=listar_sinais_abertos(db, ctx.loja_slug),
            sinais_novos=contar_sinais_novos(db, ctx.loja_slug),
        ),
    )


async def _acao_sinal(
    request: Request,
    sinal_id: str,
    db: Session,
    operacao,
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _secao_ativa():
        return _nao_existe()
    blocked = check_module_access(request, usuario, db, Module.COPILOTO)
    if blocked is not None:
        return blocked
    if not _pode(usuario):
        return _sem_permissao(request, usuario)

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(f"{_PAGINA}?erro=sessao", status_code=303)

    # loja_slug da sessão: id de sinal sozinho nunca autoriza nada.
    ok = operacao(db, usuario.loja_slug, sinal_id)
    destino = f"{_PAGINA}?ok=1" if ok else f"{_PAGINA}?erro=sinal"
    return RedirectResponse(destino, status_code=303)


@router.post(_PAGINA + "/sinais/{sinal_id}/visto")
async def copiloto_sinal_visto(
    request: Request, sinal_id: str, db: Session = Depends(get_db)
):
    return await _acao_sinal(request, sinal_id, db, marcar_visto)


@router.post(_PAGINA + "/sinais/{sinal_id}/dispensar")
async def copiloto_sinal_dispensar(
    request: Request, sinal_id: str, db: Session = Depends(get_db)
):
    return await _acao_sinal(request, sinal_id, db, dispensar)
