"""Shell Revy Loja — injeção de nav, sessão multi-loja e gates de módulo."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import csrf_valido, usuario_atual
from app.config import (
    revy_loja_copiloto_enabled,
    revy_loja_entitlements_enabled,
    revy_loja_shell_enabled,
)
from app.db import SessionLocal, get_db
from app.loja import entitlements as ents_mod
from app.loja import identity, navigation
from app.loja.copiloto import notificacoes as copiloto_notificacoes
from app.loja.copiloto.tipos import PAPEIS_GESTAO_COPILOTO
from app.loja.permissions import (
    LojaPermissionError,
    ModuloNaoContratado,
    SemAcessoLoja,
    module_enabled,
    require_module,
)
from app.loja.types import (
    ActorLoja,
    EntitlementState,
    Module,
    NavSection,
    StoreContext,
)
from app.models import SINAL_REGRAS

logger = logging.getLogger(__name__)

BRAND_NAME = "Revy Loja"

router = APIRouter(tags=["revy-loja-shell"])


def _actor_for(usuario: Any, control_memberships=None) -> ActorLoja:
    return identity.actor_from_usuario(usuario, memberships=control_memberships)


def control_memberships_for(usuario: Any, db: Session | None):
    """Memberships da pessoa na projeção do Control; ``None`` quando não há fonte.

    Fonte ÚNICA para as duas entradas que precisam da mesma lista: o shell, que
    desenha o seletor de loja (``template_extras`` → ``lojas_disponiveis``), e o
    POST que troca a loja da sessão (``loja_selecionar``). As duas já divergiram:
    o seletor listava as lojas do Control e o POST montava o actor só com
    ``usuario.loja_slug``, então toda opção do seletor que não fosse a loja
    legada caía em ``/app?erro=loja-nao-autorizada``. Não voltar a chamar o port
    direto de um dos lados só.
    """
    from app.loja.control_projection import HttpControlProjectionPort

    if db is None or not revy_loja_entitlements_enabled():
        return None
    pessoa_id = str(getattr(usuario, "id", "") or "")
    if not pessoa_id:
        return None
    return HttpControlProjectionPort(db_session=db).get_memberships(pessoa_id) or None


def resolve_store_and_entitlements(
    request: Request,
    usuario: Any,
    db: Session | None = None,
    *,
    control_memberships=None,
    control_entitlements: EntitlementState | None = None,
) -> tuple[StoreContext, EntitlementState, ActorLoja]:
    if control_memberships is None:
        control_memberships = control_memberships_for(usuario, db)

    actor = _actor_for(usuario, control_memberships)
    store = identity.resolve_store_context(
        actor, identity.session_loja_slug(request.session)
    )
    ents = ents_mod.resolve_entitlements(
        store.loja_slug,
        store.roles,
        entitlements_enabled=revy_loja_entitlements_enabled(),
        db=db,
        control_entitlements=control_entitlements,
    )
    # Alinha loja_state com entitlement real quando flag on
    if revy_loja_entitlements_enabled():
        store = StoreContext(
            loja_slug=store.loja_slug,
            roles=store.roles,
            loja_state="ativa" if ents.loja_ativa else "suspensa",
        )
    return store, ents, actor


def build_loja_nav(
    store: StoreContext,
    entitlements: EntitlementState,
) -> tuple[NavSection, ...]:
    if not revy_loja_shell_enabled():
        return ()
    return navigation.build_nav(store, entitlements, shell_enabled=True)


def copiloto_secao_liberada(
    ents: EntitlementState,
    usuario: Any,
    *,
    shell_enabled: bool,
    copiloto_enabled: bool,
    entitlements_enabled: bool,
) -> bool:
    """A seção Copiloto existe para esta pessoa agora, nesta loja?

    Fonte única para os QUATRO gates que hoje decidem se a seção Copiloto
    existe (``_secao_ativa`` + ``check_module_access`` + ``_pode`` em
    ``app/web/loja_copiloto.py``): shell ligado, flag global do Copiloto
    ligada, módulo Copiloto no entitlement da loja (o que também cobre loja
    inativa/suspensa) e papel em ``PAPEIS_GESTAO_COPILOTO``.

    ``entitlements_enabled`` replica o MESMO bypass de
    ``check_module_access()``: com a flag de entitlements desligada, a rota
    nunca olha ``module_enabled`` — devolve sempre liberado nesse quesito
    (comportamento legado fail-open). Sem replicar esse bypass aqui, papéis
    fora de ``ROLES_OPERACIONAIS`` mas dentro de ``PAPEIS_GESTAO_COPILOTO``
    (``admin_plataforma`` — ver ``identity.py``) entram na seção (200) e o
    sino, que aplicaria ``module_enabled`` mesmo assim, devolveria ``None``:
    a mesma discordância sino/seção que motivou esta função existir.

    Quem chama esta função (o sino, aqui embaixo) e quem decide se a página
    responde 404/403 (``loja_copiloto.py``) precisam concordar sempre — os
    dois lugares usam os MESMOS primitivos (``revy_loja_copiloto_enabled``,
    ``revy_loja_entitlements_enabled``, ``module_enabled``/``Module.COPILOTO``,
    ``PAPEIS_GESTAO_COPILOTO``), não reimplementam a checagem. Ver comentário
    simétrico em ``app/web/loja_copiloto.py``: os dois pontos têm que andar
    juntos, ou o sino discorda da seção.
    """
    if not (shell_enabled and copiloto_enabled):
        return False
    papel = (getattr(usuario, "papel", "") or "").strip().casefold()
    if papel not in PAPEIS_GESTAO_COPILOTO:
        return False
    if not entitlements_enabled:
        return True
    return module_enabled(ents, Module.COPILOTO)


def regras_elegiveis(
    ents, usuario, *, shell_enabled: bool, copiloto_enabled: bool, entitlements_enabled: bool
) -> frozenset[str]:
    if copiloto_secao_liberada(
        ents, usuario, shell_enabled=shell_enabled,
        copiloto_enabled=copiloto_enabled, entitlements_enabled=entitlements_enabled,
    ):
        return frozenset(SINAL_REGRAS)
    return frozenset()


def central_disponivel(ents, usuario, *, shell_enabled, copiloto_enabled, entitlements_enabled) -> bool:
    return bool(regras_elegiveis(
        ents, usuario, shell_enabled=shell_enabled,
        copiloto_enabled=copiloto_enabled, entitlements_enabled=entitlements_enabled,
    ))


def _contar_nao_vistos_com_sessao_propria(
    loja_slug: str,
    usuario_id: str,
    db: Session | None,
    regras: frozenset[str] | None = None,
) -> int | None:
    """Conta usando ``db`` se vier; senão abre e fecha uma sessão só nossa.

    ``template_extras`` roda em TODA renderização do shell — inclusive nas
    ~90% das telas cujo ``contexto(...)`` não passa ``db=`` explicitamente
    (achado da revisão: sem sessão própria, o sino só funcionava na própria
    tela do Copiloto, que é a única que já resolve ``db`` para outra coisa).
    Por isso, quando ``db`` vem ``None``, abrimos uma sessão aqui —
    independente de ``revy_loja_entitlements_enabled()`` — e a fechamos
    sempre, inclusive se a contagem levantar. O custo continua limitado pelo
    cache de ``contar_nao_vistos``: abrir uma ``Session`` não fala com o
    banco por si só (SQLAlchemy só conecta na primeira query); num acerto de
    cache, nenhuma query roda, então nenhuma conexão é sequer aberta.

    O sino é acessório: uma falha aqui NUNCA pode derrubar a tela (a exceção
    não propaga), mas também não é engolida em silêncio — vai para
    ``warning`` (achado I2 da revisão da F1).
    """
    session = db
    sessao_propria = False
    if session is None:
        try:
            session = SessionLocal()
            sessao_propria = True
        except Exception:
            logger.warning(
                "copiloto: falha ao abrir sessão para contar sinais não vistos (loja=%s)",
                loja_slug,
                exc_info=True,
            )
            return None

    try:
        if regras is None:
            return copiloto_notificacoes.contar_nao_vistos(session, loja_slug, usuario_id)
        return copiloto_notificacoes.contar_nao_vistos(
            session, loja_slug, usuario_id, regras=regras
        )
    except Exception:
        logger.warning(
            "copiloto: falha ao contar sinais não vistos (loja=%s)",
            loja_slug,
            exc_info=True,
        )
        return None
    finally:
        if sessao_propria:
            session.close()


def _copiloto_nao_vistos(
    store: StoreContext,
    ents: EntitlementState,
    usuario: Any,
    db: Session | None,
) -> int | None:
    """``None`` = sem sino; ``int`` (inclusive 0) = sino com essa contagem.

    ``None`` cobre: conjunto vazio de ``regras_elegiveis`` (hoje o mesmo
    que as quatro condições de ``copiloto_secao_liberada``) e falha ao
    obter uma sessão de banco para consultar. O template usa a diferença
    entre "sem sino" e "sino zerado" — não trocar por 0 nesses casos.
    """
    regras = regras_elegiveis(
        ents, usuario,
        shell_enabled=revy_loja_shell_enabled(),
        copiloto_enabled=revy_loja_copiloto_enabled(),
        entitlements_enabled=revy_loja_entitlements_enabled(),
    )
    if not regras:
        return None
    usuario_id = getattr(usuario, "id", None)
    if not usuario_id:
        return None
    return _contar_nao_vistos_com_sessao_propria(
        store.loja_slug, usuario_id, db, regras=regras
    )


def _copiloto_nao_vistos_sem_membership(usuario: Any, db: Session | None) -> int | None:
    """Caminho de quem tem ``PAPEIS_GESTAO_COPILOTO`` mas nenhum cargo
    operacional de loja — hoje só ``admin_plataforma`` (``identity.py``:
    "admin_plataforma não é cargo operacional da Loja; não concede união
    implícita"). Para essa pessoa, ``resolve_store_and_entitlements`` SEMPRE
    levanta ``SemAcessoLoja`` (``active_memberships`` descarta membership com
    ``roles`` vazio), então ``template_extras`` nunca chega a resolver
    ``store``/``ents`` — e nunca chamaria ``_copiloto_nao_vistos`` acima.

    A seção Copiloto não depende dessa resolução para este papel: com
    ``revy_loja_entitlements_enabled()`` desligada, ``check_module_access()``
    devolve ``None`` (liberado) ANTES de tentar resolver store, e
    ``_pode()``/``_ctx()`` usam ``usuario.papel``/``usuario.loja_slug`` direto
    — a rota nunca olha para membership. Espelhamos aqui, com o mesmo
    ``usuario.loja_slug`` que a rota usa.

    Só vale quando entitlements está desligada: com ela ligada,
    ``check_module_access()`` também chama ``resolve_store_and_entitlements``
    e também recebe ``SemAcessoLoja`` (subclasse de ``LojaPermissionError``,
    que o `except` de lá já captura) — a rota responde 403 e o sino já
    concorda devolvendo ``None`` sem precisar deste caminho.
    """
    if revy_loja_entitlements_enabled():
        return None
    if not (revy_loja_shell_enabled() and revy_loja_copiloto_enabled()):
        return None
    papel = (getattr(usuario, "papel", "") or "").strip().casefold()
    if papel not in PAPEIS_GESTAO_COPILOTO:
        return None
    loja_slug = str(getattr(usuario, "loja_slug", "") or "").strip()
    if not loja_slug:
        return None
    usuario_id = getattr(usuario, "id", None)
    if not usuario_id:
        return None
    return _contar_nao_vistos_com_sessao_propria(loja_slug, usuario_id, db)


def template_extras(
    request: Request,
    usuario: Any,
    db: Session | None = None,
    **_kwargs,
) -> dict[str, Any]:
    """Extras de template quando o shell está ligado; dict vazio se desligado."""
    if not revy_loja_shell_enabled() or usuario is None:
        return {}
    try:
        store, ents, actor = resolve_store_and_entitlements(request, usuario, db)
    except SemAcessoLoja:
        return {
            "loja_shell": True,
            "loja_brand": BRAND_NAME,
            "loja_nav": (),
            "lojas_disponiveis": (),
            "store_context": None,
            "entitlements": None,
            "copiloto_nao_vistos": _copiloto_nao_vistos_sem_membership(usuario, db),
        }
    nav = build_loja_nav(store, ents)
    return {
        "loja_shell": True,
        "loja_brand": BRAND_NAME,
        "loja_nav": nav,
        "lojas_disponiveis": identity.available_store_slugs(actor),
        "store_context": store,
        "entitlements": ents,
        "copiloto_nao_vistos": _copiloto_nao_vistos(store, ents, usuario, db),
    }


def check_module_access(
    request: Request,
    usuario: Any,
    db: Session,
    module: Module | str,
) -> JSONResponse | HTMLResponse | None:
    """Retorna resposta 403 se entitlements on e módulo bloqueado; senão None.

    Com flag de entitlements desligada → sempre None (comportamento legado).
    """
    if not revy_loja_entitlements_enabled():
        return None
    try:
        _store, ents, _actor = resolve_store_and_entitlements(request, usuario, db)
        require_module(ents, module)
    except ModuloNaoContratado as exc:
        return _forbidden(request, str(exc.message))
    except LojaPermissionError as exc:
        return _forbidden(request, str(exc.message))
    return None


def _forbidden(request: Request, detail: str) -> HTMLResponse:
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"detail": detail}, status_code=403)  # type: ignore[return-value]
    html = (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        f"<title>403 — {BRAND_NAME}</title></head><body>"
        f"<h1>Acesso negado</h1><p>{detail}</p>"
        "<p><a href='/app'>Voltar</a></p></body></html>"
    )
    return HTMLResponse(html, status_code=403)


def redirecionar_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


# --- Rotas do shell (seleção multi-loja; overviews em loja_vendas/estoque/routes) ---


@router.post("/app/loja/selecionar")
async def loja_selecionar(
    request: Request,
    db: Session = Depends(get_db),
):
    """Troca a loja ativa na sessão (multi-loja)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app?erro=csrf", status_code=303)
    actor = _actor_for(usuario)
    try:
        # memberships multi-loja podem vir de request.state (testes) ou, em
        # produção, da MESMA projeção do Control que desenhou o seletor —
        # ver control_memberships_for(). Autorizar aqui só por
        # ``usuario.loja_slug`` rejeitava toda loja listada pelo seletor que
        # não fosse a legada.
        extra = getattr(request.state, "loja_memberships", None)
        if extra is None:
            extra = control_memberships_for(usuario, db)
        if extra is not None:
            actor = identity.actor_from_usuario(usuario, memberships=extra)
        slug = identity.select_store_slug(actor, str(form.get("loja_slug") or ""))
    except SemAcessoLoja:
        return RedirectResponse("/app?erro=loja-nao-autorizada", status_code=303)
    request.session[identity.SESSION_LOJA_KEY] = slug
    return RedirectResponse("/app", status_code=303)


def ensure_session_loja(request: Request, usuario: Any) -> None:
    """Garante loja_slug na sessão a partir do Usuario quando ainda vazio."""
    if identity.session_loja_slug(request.session):
        return
    slug = str(getattr(usuario, "loja_slug", "") or "").strip()
    if slug:
        request.session[identity.SESSION_LOJA_KEY] = slug
