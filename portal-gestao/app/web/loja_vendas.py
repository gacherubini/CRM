"""Rotas Revy Loja — Vendas → Visão geral (Fase 3) + F5 (equipe / financeiras).

Ativadas somente com REVY_LOJA_SHELL_ENABLED=1. Com a flag off, retornam 404
para não alterar o shell legado em /app.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import (  # noqa: E402
    pode_confirmar_venda,
    pode_gerir_equipe,
    pode_gerir_financeiras,
    pode_registrar_venda,
    pode_ver_custo,
    pode_ver_equipe,
    pode_ver_financeiro,
    pode_ver_resultados_midia,
    usuario_atual,
)
from app.config import revy_loja_shell_enabled, settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.sales_overview import (  # noqa: E402
    PAPEIS_AUTORIZADOS,
    build_sales_overview,
)
from app.main import (  # noqa: E402
    contexto,
    csrf_valido,
    enriquecer_credenciais,
    executar_cancelamento_venda,
    executar_confirmacao_venda,
    get_chatbot_client,
    get_estoque_client,
    get_motor_client,
    redirecionar_login,
    templates,
    PAPEIS_EQUIPE_ROTULO,
)
from app.web.equipe import _membros_da_loja  # noqa: E402
from app.clients.motor import MotorClient, MotorIndisponivel  # noqa: E402
from app.models import Usuario, Venda  # noqa: E402

_LISTA = "/app/loja/vendas/lista"


def _shell_desligado() -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def _shell_ativo() -> bool:
    # Lê env em runtime (evita snapshot de Settings poluído entre testes).
    return revy_loja_shell_enabled()


def _papel_autorizado(usuario: Usuario) -> bool:
    return (usuario.papel or "").strip().casefold() in PAPEIS_AUTORIZADOS


def _fetch_resultados_api():
    """Callable opcional para a API Revy Tráfego / Control (read-only)."""
    if not settings.revy_trafego_resultados_enabled:
        return None
    from app.clients.revy_trafego import RevyTrafegoClient

    client = RevyTrafegoClient()

    def _fetch(
        *,
        loja_slug: str,
        periodo: str = "mes",
        modo: str = "last",
        inicio: str | None = None,
        fim: str | None = None,
    ):
        return client.fetch_resultados(
            loja_slug=loja_slug,
            periodo=periodo,
            modo=modo,
            inicio=inicio,
            fim=fim,
        )

    return _fetch


def _bancos_nao_configurados(usuario: Usuario, motor: MotorClient) -> list[str] | None:
    """Nomes de provedores sem credencial — pendência operacional (F5)."""
    if not pode_gerir_financeiras(usuario):
        return None
    if not motor.configurado:
        return None
    try:
        raw = motor.listar_credenciais(ator=usuario.email)
        try:
            provedores = motor.listar_provedores(ator=usuario.email)
        except MotorIndisponivel:
            provedores = []
        credenciais = enriquecer_credenciais(raw, provedores)
    except MotorIndisponivel:
        return None
    faltando: list[str] = []
    for c in credenciais:
        if c.get("senha_configurada"):
            continue
        nome = (c.get("rotulo") or c.get("provedor") or "").strip()
        if nome:
            faltando.append(nome)
    return faltando or None


def _montar_overview(
    usuario: Usuario,
    db: Session,
    chatbot,
    inicio: str | None,
    fim: str | None,
    motor: MotorClient | None = None,
):
    papel = (usuario.papel or "").strip().casefold()
    fetch = _fetch_resultados_api() if pode_ver_resultados_midia(usuario) else None
    bancos = None
    if motor is not None and papel in {"dono", "gerente", "admin_plataforma"}:
        bancos = _bancos_nao_configurados(usuario, motor)
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
        bancos_nao_configurados=bancos,
    )


@router.get("/app/loja/vendas", response_class=HTMLResponse)
def loja_vendas_visao(
    request: Request,
    inicio: str | None = None,
    fim: str | None = None,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
    motor: MotorClient = Depends(get_motor_client),
):
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _papel_autorizado(usuario):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    overview = _montar_overview(usuario, db, chatbot, inicio, fim, motor=motor)
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
    motor: MotorClient = Depends(get_motor_client),
):
    """JSON do mesmo read model — para smoke/integração sem template."""
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _papel_autorizado(usuario):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    overview = _montar_overview(usuario, db, chatbot, inicio, fim, motor=motor)
    return overview.to_dict()


@router.get("/app/loja/vendas/lista", response_class=HTMLResponse)
def loja_vendas_lista(
    request: Request,
    ok: str | None = None,
    erro: str | None = None,
    db: Session = Depends(get_db),
):
    """Registro de vendas dentro do shell: registrar, confirmar e cancelar.

    Vendedor vê as próprias; dono/gerente veem as da loja.
    """
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _papel_autorizado(usuario):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    consulta = db.query(Venda).filter(Venda.loja_slug == usuario.loja_slug)
    if not pode_ver_financeiro(usuario):
        consulta = consulta.filter(Venda.vendedor_email == usuario.email)
    vendas = consulta.order_by(Venda.criada_em.desc()).all()

    return templates.TemplateResponse(
        "loja/vendas_lista.html",
        contexto(
            request,
            usuario,
            vendas=vendas,
            escopo_proprio=not pode_ver_financeiro(usuario),
            pode_agir=pode_confirmar_venda(usuario),
            pode_registrar=pode_registrar_venda(usuario),
            aviso_ok=ok,
            aviso_erro=erro,
            shell_loja=True,
        ),
    )


@router.post("/app/loja/vendas/{venda_id}/confirmar")
async def loja_venda_confirmar(
    request: Request,
    venda_id: str,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
    estoque=Depends(get_estoque_client),
):
    """Mesma cascata da rota legada, sem tirar a pessoa do shell."""
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_confirmar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(_LISTA, status_code=303)
    resultado = executar_confirmacao_venda(db, usuario, venda_id, chatbot, estoque)
    return RedirectResponse(f"{_LISTA}?{resultado}", status_code=303)


@router.post("/app/loja/vendas/{venda_id}/cancelar")
async def loja_venda_cancelar(
    request: Request,
    venda_id: str,
    db: Session = Depends(get_db),
):
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_confirmar_venda(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(_LISTA, status_code=303)
    resultado = executar_cancelamento_venda(db, usuario, venda_id, form.get("motivo"))
    return RedirectResponse(f"{_LISTA}?{resultado}", status_code=303)


@router.get("/app/loja/vendas/configuracoes-financeiras")
def loja_configuracoes_financeiras_alias(
    request: Request,
    db: Session = Depends(get_db),
):
    """Alias contextual (F5): Configurações financeiras → Acessos bancários."""
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    # Domínio real permanece em /app/financeiras (crypto, test, replace).
    return RedirectResponse("/app/financeiras", status_code=303)


@router.get("/app/loja/equipe", response_class=HTMLResponse)
def loja_equipe_lista(
    request: Request,
    db: Session = Depends(get_db),
):
    """Lista read-only da equipe (nome, papel, ativo) — F5.

    Contas/cargos no Revy Control. Distribuição de atendimento fica na Loja.
    Não exibe números WhatsApp, tokens ou integrações.
    """
    if not _shell_ativo():
        return _shell_desligado()

    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_ver_equipe(usuario):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    # Dono gerencia; gerente só consulta (distribuição de atendimento).
    somente_leitura = not pode_gerir_equipe(usuario)
    return templates.TemplateResponse(
        "equipe/lista.html",
        contexto(
            request,
            usuario,
            membros=_membros_da_loja(db, usuario.loja_slug),
            papeis_rotulo=PAPEIS_EQUIPE_ROTULO,
            equipe_somente_leitura=somente_leitura,
            msg_equipe_control=None,
        ),
    )
