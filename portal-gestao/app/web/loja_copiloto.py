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
from app.loja.copiloto.acoes import AcaoRecusada, desfazer_acao, executar_acao  # noqa: E402
from app.loja.copiloto.conversas import (  # noqa: E402
    cancelar_turno,
    criar_turno,
    listar_conversas,
    listar_turnos,
    obter_turno,
)
from app.loja.copiloto.notificacoes import (  # noqa: E402
    catalogo_regra,
    contar_nao_vistos,
    invalidar_contagem,
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
from app.models import CopilotoSinal, CopilotoTurno, Usuario  # noqa: E402
from app.web.loja_shell import check_module_access  # noqa: E402

_PAGINA = "/app/loja/copiloto"


def _secao_ativa() -> bool:
    # Lê env em runtime (evita snapshot de Settings poluído entre testes).
    #
    # Estas quatro checagens (aqui, em check_module_access() logo abaixo nas
    # rotas — inclusive o bypass de módulo quando revy_loja_entitlements_enabled()
    # está desligada — e em _pode()) e app.web.loja_shell.copiloto_secao_liberada()
    # (que decide se o SINO aparece no shell) têm que andar juntas: mesma
    # flag de shell, mesma flag do copiloto, mesmo bypass de entitlements,
    # mesmo Module.COPILOTO, mesma PAPEIS_GESTAO_COPILOTO. Não foram
    # fundidas numa função só porque aqui cada condição vira uma resposta
    # HTTP diferente (404 de flag desligada vs 403 de módulo vs 403 de
    # papel, com mensagens distintas) — um único bool perderia essa
    # distinção. Mudar uma exige olhar a outra.
    #
    # admin_plataforma é caso à parte dos dois lados: não tem cargo
    # operacional de loja (identity.py), então _pode()/check_module_access()
    # aqui nunca dependem de membership pra esse papel (com entitlements OFF,
    # bypass total antes mesmo de tentar resolver loja); do lado do sino,
    # resolve_store_and_entitlements SEMPRE levanta SemAcessoLoja pra esse
    # papel, então quem fecha a paridade lá é
    # _copiloto_nao_vistos_sem_membership(), não copiloto_secao_liberada().
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
    # Mesma constante que o sino usa (app.web.loja_shell.copiloto_secao_liberada)
    # — ver comentário em _secao_ativa() acima.
    return (usuario.papel or "").strip().casefold() in PAPEIS_GESTAO_COPILOTO


def _ctx(usuario: Usuario) -> CopilotoContexto:
    """loja_slug e papel SEMPRE da sessão — nunca de parâmetro de rota."""
    return CopilotoContexto(
        loja_slug=usuario.loja_slug,
        papel=usuario.papel,
        ator_email=usuario.email,
        hoje=datetime.now(timezone.utc).date(),
    )


def _cartao_do_turno(passos: list[dict]) -> dict | None:
    """O cartão do último `propor_acao` do turno, se houver.

    ``passo.get("extra")``, nunca ``passo["extra"]``: turnos persistidos
    antes desta task têm ``passos_json`` sem a chave ``extra`` no JSON —
    indexação direta quebraria em qualquer turno anterior a este deploy.
    """
    for passo in reversed(passos or []):
        if passo.get("ferramenta") == "propor_acao" and passo.get("extra"):
            return passo["extra"]
    return None


_STATUS_POR_CODE = {
    "acao_invalida": 400,
    "parametro": 400,
    "preco_invalido": 400,
    "banda": 400,
    "piso": 400,
    "preco_esperado_ausente": 400,
    "divergencia": 409,
    "nao_encontrado": 404,
    "escopo": 403,
    "rate_limit": 429,
    "indisponivel": 503,
    "execucao": 502,
}


@router.get(_PAGINA, response_class=HTMLResponse)
def copiloto_home(
    request: Request,
    conversa_id: str | None = None,
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
    conversas = listar_conversas(db, ctx.loja_slug, usuario.id)
    # Só abre conversa que está NESTA lista: listar_conversas já filtra por
    # loja_slug+usuario_id, então um conversa_id de outra loja/usuário (query
    # string é entrada do cliente) nunca aparece aqui — vira "nenhuma escolhida".
    escolhida = next((c for c in conversas if c.id == conversa_id), None)
    turnos = listar_turnos(db, ctx.loja_slug, escolhida.id) if escolhida else []
    turnos_view = []
    for t in turnos:
        passos = json.loads(t.passos_json) if t.passos_json else []
        turnos_view.append(
            {
                "id": t.id,
                "pergunta": t.pergunta,
                "resposta": t.resposta or t.texto_parcial,
                "estado": t.estado,
                "erro_code": t.erro_code,
                "passos": passos,
                "cartao": _cartao_do_turno(passos),
            }
        )
    return templates.TemplateResponse(
        "loja/copiloto.html",
        contexto(
            request,
            usuario,
            db=db,
            resumo=resumo,
            sinais=listar_sinais_abertos(db, ctx.loja_slug),
            sinais_novos=contar_sinais_novos(db, ctx.loja_slug, usuario.id),
            conversas=conversas,
            conversa_atual=escolhida,
            turnos=turnos_view,
        ),
    )


async def _acao_sinal(
    request: Request,
    sinal_id: str,
    db: Session,
    operacao,
):
    """``operacao`` sempre recebe ``(db, loja_slug, sinal_id, usuario_id)``.

    ``dispensar`` não usa pessoa (é da loja, por desenho — ver
    ``sinais_store.py``), então o chamador abaixo o embrulha para ignorar o
    ``usuario_id``. Isso mantém este helper único em vez de duas cópias, sem
    inventar um ``usuario_id`` opcional dentro do próprio ``dispensar``.
    """
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
    ok = operacao(db, usuario.loja_slug, sinal_id, usuario.id)
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
    return await _acao_sinal(
        request,
        sinal_id,
        db,
        lambda db, loja_slug, sid, _usuario_id: dispensar(db, loja_slug, sid),
    )


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


def _serializar_sinal_para_painel(sinal: CopilotoSinal) -> dict:
    """Só os campos que o JS do painel (``base.html``, F4/Task 2) lê.

    ``acao_sugerida`` vem de volta como dict (não string) — o JS só usa
    ``.href`` quando presente; ações sem link (ex.: ajustar_preco) chegam
    sem ``href`` e o botão "Abrir" simplesmente não aparece.

    ``rotulo``/``icone``/``severidade_padrao`` vêm do catálogo único
    (``catalogo_regra``, F4/Task 5) — nunca de ``sinal.regra`` copiado direto
    no payload. ``EntradaCatalogo`` é ``@dataclass(frozen=True)`` e não é
    serializável por ``JSONResponse``/``json.dumps`` puro; em vez de
    ``dataclasses.asdict`` (que devolveria as 3 chaves com os nomes do
    dataclass automaticamente, inclusive se o dataclass ganhar um campo novo
    amanhã), os campos são extraídos um a um aqui, no mesmo estilo manual do
    resto deste dict — explícito sobre o que o payload promete, e o nome
    cru da regra (``sinal.regra``) nunca entra na resposta.
    """
    acao_sugerida = (
        json.loads(sinal.acao_sugerida_json) if sinal.acao_sugerida_json else None
    )
    entrada_catalogo = catalogo_regra(sinal.regra)
    return {
        "id": sinal.id,
        "severidade": sinal.severidade,
        "titulo": sinal.titulo,
        "detalhe": sinal.detalhe,
        "quando": sinal.criado_em.isoformat() if sinal.criado_em else None,
        "acao_sugerida": acao_sugerida,
        "rotulo": entrada_catalogo.rotulo,
        "icone": entrada_catalogo.icone,
        "severidade_padrao": entrada_catalogo.severidade_padrao,
    }


@router.get(_PAGINA + "/notificacoes.json")
def copiloto_notificacoes_json(request: Request, db: Session = Depends(get_db)):
    """Alimenta o painel do sino (F4/Task 2). Mesmo gate quádruplo das demais
    rotas JSON — ``_guard_json`` já resolve ``loja_slug`` da sessão.

    ``itens`` é a lista da LOJA inteira (``listar_sinais_abertos`` — mesma
    função da tela principal do Copiloto): a equipe de gestão toda vê os
    mesmos alertas. ``nao_vistos`` é pessoal (usa o mesmo cache do sino, não
    uma segunda query) para o número do painel nunca discordar do badge que
    já está na tela.
    """
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro
    itens = [
        _serializar_sinal_para_painel(s)
        for s in listar_sinais_abertos(db, usuario.loja_slug)
    ]
    nao_vistos = contar_nao_vistos(db, usuario.loja_slug, usuario.id)
    return JSONResponse({"itens": itens, "nao_vistos": nao_vistos})


@router.post(_PAGINA + "/notificacoes/{sinal_id}/visto")
async def copiloto_notificacao_visto(
    request: Request, sinal_id: str, db: Session = Depends(get_db)
):
    """``sinal_id`` é entrada do cliente e não autoriza nada sozinho:
    ``marcar_visto`` filtra por ``loja_slug`` no WHERE — sinal de outra loja
    devolve ``False`` aqui, nunca confirma que existe em outro lugar."""
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")

    ok = marcar_visto(db, usuario.loja_slug, sinal_id, usuario.id)
    if not ok:
        return _json_erro(404, "not_found", "Notificação não encontrada")
    # "Visto" é por pessoa (Task 0): só o cache DESTE usuário fica velho —
    # invalidar a loja inteira aqui apagaria de graça o cache de quem nem
    # tocou no sinal.
    invalidar_contagem(usuario.loja_slug, usuario.id)
    return JSONResponse({"ok": True})


@router.post(_PAGINA + "/notificacoes/{sinal_id}/dispensar")
async def copiloto_notificacao_dispensar(
    request: Request, sinal_id: str, db: Session = Depends(get_db)
):
    """``dispensar`` é da loja inteira (não por pessoa) — por isso invalida o
    cache de TODA a loja, não só do usuário que clicou (ver docstring de
    ``invalidar_contagem``)."""
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")

    ok = dispensar(db, usuario.loja_slug, sinal_id)
    if not ok:
        return _json_erro(404, "not_found", "Notificação não encontrada")
    invalidar_contagem(usuario.loja_slug)
    return JSONResponse({"ok": True})


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
    passos = json.loads(turno.passos_json) if turno.passos_json else []
    return JSONResponse(
        {
            "ok": True,
            "turno_id": turno.id,
            "conversa_id": turno.conversa_id,
            "estado": turno.estado,
            "texto": turno.resposta or turno.texto_parcial,
            "erro_code": turno.erro_code,
            "passos": passos,
            "cartao": _cartao_do_turno(passos),
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


@router.post(_PAGINA + "/acao")
async def copiloto_executar_acao(
    request: Request,
    db: Session = Depends(get_db),
    # Depends, não uma chamada direta a get_estoque_client(): só assim o
    # dependency_override que os testes usam (EstoqueAcaoFake) tem efeito. Uma
    # chamada direta ignoraria app.dependency_overrides e bateria na rede real.
    estoque=Depends(get_estoque_client),
):
    """Execução da ação. NUNCA sai do turno do LLM — sai do clique humano.

    ``agora`` nunca vem daqui: ``executar_acao`` recebe ``agora=None`` e
    deriva o relógio real internamente. Nenhum campo da requisição (query,
    form ou header) é repassado como ``agora`` — ver ``acoes.py`` para o
    porquê (fura rate-limit e envenena carimbo/prazo de desfazer).
    """
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")

    parametros = {
        "veiculo_id": (form.get("veiculo_id") or "").strip(),
        "novo_preco": (form.get("novo_preco") or "").strip() or None,
        "preco_esperado": (form.get("preco_esperado") or "").strip() or None,
    }
    try:
        registro = executar_acao(
            db,
            _ctx(usuario),
            acao=(form.get("acao") or "").strip(),
            parametros=parametros,
            estoque=estoque,
            turno_id=(form.get("turno_id") or "").strip() or None,
        )
    except AcaoRecusada as exc:
        return _json_erro(_STATUS_POR_CODE.get(exc.code, 400), exc.code, str(exc))

    return JSONResponse(
        {
            "ok": True,
            "acao_id": registro.id,
            "acao": registro.acao,
            "desfazer_ate": (
                registro.desfazer_ate.isoformat() if registro.desfazer_ate else None
            ),
        }
    )


@router.post(_PAGINA + "/acao/{acao_id}/desfazer")
async def copiloto_desfazer_acao(
    request: Request,
    acao_id: str,
    db: Session = Depends(get_db),
    estoque=Depends(get_estoque_client),
):
    """``agora`` também nunca vem da requisição aqui — mesma razão da rota acima."""
    usuario, erro = _guard_json(request, db)
    if erro is not None:
        return erro
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")
    desfeito = desfazer_acao(db, _ctx(usuario), acao_id, estoque=estoque)
    return JSONResponse({"ok": True, "desfeito": desfeito})
