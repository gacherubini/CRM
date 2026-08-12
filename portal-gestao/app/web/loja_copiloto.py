"""Rotas da seção Copiloto de Vendas (Revy Loja).

Gate quádruplo: shell + flag do Copiloto + entitlement do módulo + papel de
gestão. Com qualquer um faltando a seção NÃO EXISTE (404) — não redireciona.

Menu oculto não substitui checagem (app/loja/permissions.py:1): o entitlement
por loja (Module.COPILOTO) é resolvido e checado aqui, no servidor, com o
mesmo mecanismo que Estoque/Vendas usam (check_module_access) — não basta
esconder o item do nav quando a loja não contratou o módulo.

Resumo/alertas (`copiloto_home`) são determinísticos. O chat com LLM
(`/perguntar`, `/turno/{id}.json`, `/turno/{id}/cancelar`) grava o turno e
volta na hora — quem executa é `app.copiloto_turnos_job`, nunca a requisição:
não há streaming neste repositório, e prender um worker HTTP por segundos
derrubaria a Revy Loja inteira. `_guard_json` replica o MESMO gate quádruplo
das rotas acima para as rotas JSON do chat.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import usuario_atual  # noqa: E402
from app.config import revy_loja_copiloto_enabled, revy_loja_shell_enabled  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.copiloto.conversas import (  # noqa: E402
    cancelar_turno,
    criar_turno,
    obter_turno,
)
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
from app.meta_ads_spend_job import env_float, env_int  # noqa: E402
from app.models import CopilotoTurno, Usuario  # noqa: E402
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


def _json_erro(status: int, code: str, mensagem: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": code, "message": mensagem}, status_code=status
    )


def _guard_json(request: Request, db: Session):
    """Retorna (usuario, None) ou (None, resposta de erro).

    Mesmo gate quádruplo de ``copiloto_home``/``_acao_sinal``: shell + flag do
    Copiloto + entitlement do módulo (server-side, por loja) + papel de
    gestão. Esconder o item do nav não substitui isto — ver módulo docstring.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return None, _json_erro(401, "auth", "Não autenticado")
    if not _secao_ativa():
        return None, _nao_existe()
    blocked = check_module_access(request, usuario, db, Module.COPILOTO)
    if blocked is not None:
        return None, blocked
    if not _pode(usuario):
        return None, _json_erro(403, "perm", "O Copiloto é do dono e do gerente.")
    return usuario, None


@router.post(_PAGINA + "/perguntar")
async def copiloto_perguntar(request: Request, db: Session = Depends(get_db)):
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")

    pergunta = (form.get("pergunta") or "").strip()
    if not pergunta:
        return _json_erro(400, "pergunta", "Escreva uma pergunta.")

    # Guarda de runaway (§9): não é medidor comercial.
    # A janela de tempo é obrigatória, não cosmética: sem ela, turno órfão de um
    # processo morto (deploy no meio da pergunta) conta para sempre e o dono fica
    # num 429 permanente. O worker também expira órfão, mas a rota não pode
    # depender de o worker estar vivo para deixar de trancar o usuário.
    desde = datetime.now(timezone.utc) - timedelta(
        seconds=env_float("PORTAL_COPILOTO_TURNO_TTL_SECONDS", 180.0)
    )
    abertos = (
        db.query(CopilotoTurno)
        .filter(
            CopilotoTurno.usuario_id == usuario.id,
            CopilotoTurno.estado.in_(("pendente", "executando")),
            CopilotoTurno.criado_em >= desde,
        )
        .count()
    )
    if abertos >= env_int("PORTAL_COPILOTO_MAX_TURNOS_ABERTOS", 2):
        return _json_erro(429, "ocupado", "Espere a resposta anterior terminar.")

    try:
        turno = criar_turno(
            db,
            loja_slug=usuario.loja_slug,
            usuario_id=usuario.id,
            pergunta=pergunta,
            # conversa_id só reaproveita a conversa se pertencer a este usuário
            # NESTA loja (criar_turno filtra por loja_slug+usuario_id); um id
            # de outra loja/usuário nunca autoriza nada — vira conversa nova.
            conversa_id=(form.get("conversa_id") or "").strip() or None,
        )
    except ValueError as exc:
        return _json_erro(400, "pergunta", str(exc))

    return JSONResponse(
        {
            "ok": True,
            "turno_id": turno.id,
            "conversa_id": turno.conversa_id,
            "estado": turno.estado,
        }
    )


@router.get(_PAGINA + "/turno/{turno_id}.json")
def copiloto_turno_json(
    request: Request, turno_id: str, db: Session = Depends(get_db)
):
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro
    # loja_slug da sessão: turno_id sozinho nunca autoriza a leitura.
    turno = obter_turno(db, usuario.loja_slug, turno_id)
    if turno is None:
        return _json_erro(404, "not_found", "Turno não encontrado")
    return JSONResponse(
        {
            "ok": True,
            "turno_id": turno.id,
            "conversa_id": turno.conversa_id,
            "estado": turno.estado,
            "texto": turno.resposta or turno.texto_parcial,
            "erro_code": turno.erro_code,
            "passos": json.loads(turno.passos_json) if turno.passos_json else [],
        }
    )


@router.post(_PAGINA + "/turno/{turno_id}/cancelar")
async def copiloto_turno_cancelar(
    request: Request, turno_id: str, db: Session = Depends(get_db)
):
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")
    # loja_slug da sessão: turno_id sozinho nunca autoriza o cancelamento.
    return JSONResponse(
        {"ok": True, "cancelado": cancelar_turno(db, usuario.loja_slug, turno_id)}
    )
