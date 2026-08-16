"""Rotas da seção Financeiro da Revy Loja (2026-08-16).

Gate triplo, igual ao Copiloto: shell + flag ``REVY_LOJA_FINANCEIRO_ENABLED``
+ entitlement ``Module.FINANCEIRO`` + papel de gestão. Com qualquer um
faltando a seção NÃO EXISTE (404 para flag/shell, 403 para módulo/papel).

**Vendedor nunca entra aqui.** Custo e lucro são a primeira armadilha do
README da Loja: o gate é de backend, não item de menu escondido.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import usuario_atual  # noqa: E402
from app.config import (  # noqa: E402
    revy_loja_financeiro_enabled,
    revy_loja_shell_enabled,
)
from app.db import get_db  # noqa: E402
from app.loja.financeiro import (  # noqa: E402
    CATEGORIAS_DESPESA,
    competencia_atual,
    competencia_valida,
    despesas_vigentes,
    resultado_financeiro_mes,
)
from app.loja.types import Module  # noqa: E402
from app.main import (  # noqa: E402
    contexto,
    csrf_valido,
    dinheiro,
    redirecionar_login,
    templates,
)
from app.models import DespesaFixaAjuste, DespesaFixaLoja, Usuario, agora  # noqa: E402
from app.web.loja_shell import check_module_access  # noqa: E402

_PAGINA = "/app/loja/financeiro"
_DESPESAS = _PAGINA + "/despesas"

# Mesma constante do Copiloto: quem vê cifra de custo é gestão.
PAPEIS_GESTAO_FINANCEIRO = frozenset({"dono", "gerente"})


def _secao_ativa() -> bool:
    # Lê env em runtime (evita snapshot de Settings poluído entre testes).
    return revy_loja_shell_enabled() and revy_loja_financeiro_enabled()


def _nao_existe() -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def _pode(usuario: Usuario) -> bool:
    return (usuario.papel or "").strip().casefold() in PAPEIS_GESTAO_FINANCEIRO


def _sem_permissao(request: Request, usuario: Usuario):
    return templates.TemplateResponse(
        "erro.html",
        contexto(
            request,
            usuario,
            erro="O Financeiro é do dono e do gerente da loja.",
        ),
        status_code=403,
    )


def _entrar(request: Request, db: Session):
    """Gate das rotas do Financeiro. Devolve (usuario, None) ou (None, resposta)."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return None, redirecionar_login()
    if not _secao_ativa():
        return None, _nao_existe()
    blocked = check_module_access(request, usuario, db, Module.FINANCEIRO)
    if blocked is not None:
        return None, blocked
    if not _pode(usuario):
        return None, _sem_permissao(request, usuario)
    return usuario, None


@router.get(_PAGINA, response_class=HTMLResponse)
def financeiro_resultado(
    request: Request,
    mes: str | None = None,
    db: Session = Depends(get_db),
):
    usuario, erro = _entrar(request, db)
    if erro is not None:
        return erro

    competencia = competencia_valida(mes)
    resultado = resultado_financeiro_mes(db, usuario.loja_slug, competencia)
    return templates.TemplateResponse(
        "loja/financeiro_resultado.html",
        contexto(
            request,
            usuario,
            resultado=resultado,
            competencia=competencia,
            competencia_hoje=competencia_atual(),
            shell_loja=True,
        ),
    )


@router.get(_PAGINA + "/dados")
def financeiro_dados(
    request: Request,
    mes: str | None = None,
    db: Session = Depends(get_db),
):
    """JSON do mesmo cálculo — para smoke/integração sem template."""
    usuario, erro = _entrar(request, db)
    if erro is not None:
        return erro
    competencia = competencia_valida(mes)
    return resultado_financeiro_mes(db, usuario.loja_slug, competencia).to_dict()


@router.get(_DESPESAS, response_class=HTMLResponse)
def financeiro_despesas(
    request: Request,
    mes: str | None = None,
    ok: str | None = None,
    erro_form: str | None = None,
    db: Session = Depends(get_db),
):
    usuario, erro = _entrar(request, db)
    if erro is not None:
        return erro

    competencia = competencia_valida(mes)
    itens = despesas_vigentes(db, usuario.loja_slug, competencia)
    # Fora de vigência continua listado à parte: some do total, não do cadastro.
    todas = (
        db.query(DespesaFixaLoja)
        .filter(DespesaFixaLoja.loja_slug == usuario.loja_slug)
        .order_by(DespesaFixaLoja.categoria, DespesaFixaLoja.descricao)
        .all()
    )
    vigentes_ids = {d.id for d, _v in itens}
    return templates.TemplateResponse(
        "loja/financeiro_despesas.html",
        contexto(
            request,
            usuario,
            competencia=competencia,
            competencia_hoje=competencia_atual(),
            itens=itens,
            encerradas=[d for d in todas if d.id not in vigentes_ids],
            categorias=CATEGORIAS_DESPESA,
            aviso_ok=ok,
            aviso_erro=erro_form,
            shell_loja=True,
        ),
    )


async def _gate_mutacao(request: Request, db: Session):
    usuario, erro = _entrar(request, db)
    if erro is not None:
        return None, None, erro
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return None, None, RedirectResponse(_DESPESAS, status_code=303)
    return usuario, form, None


def _volta(competencia: str, resultado: str) -> RedirectResponse:
    return RedirectResponse(
        f"{_DESPESAS}?mes={competencia}&{resultado}", status_code=303
    )


@router.post(_DESPESAS)
async def financeiro_despesa_nova(request: Request, db: Session = Depends(get_db)):
    usuario, form, bloqueio = await _gate_mutacao(request, db)
    if bloqueio is not None:
        return bloqueio

    competencia = competencia_valida(form.get("mes"))
    categoria = (form.get("categoria") or "").strip()
    descricao = (form.get("descricao") or "").strip()
    if categoria not in CATEGORIAS_DESPESA or not descricao:
        return _volta(competencia, "erro_form=dados")
    try:
        valor = dinheiro(form.get("valor"))
    except Exception:
        return _volta(competencia, "erro_form=valor")
    if valor <= 0:
        return _volta(competencia, "erro_form=valor")

    db.add(
        DespesaFixaLoja(
            loja_slug=usuario.loja_slug,
            categoria=categoria,
            descricao=descricao,
            valor_mensal=valor,
            # Vale a partir do mês que está sendo editado — não retroage sobre
            # meses já fechados que o lojista possa ter conferido.
            inicio_competencia=competencia,
        )
    )
    db.commit()
    return _volta(competencia, "ok=cadastrada")


@router.post(_DESPESAS + "/{despesa_id}/ajuste")
async def financeiro_despesa_ajuste(
    request: Request, despesa_id: str, db: Session = Depends(get_db)
):
    """Valor diferente só neste mês; o cadastro recorrente fica intacto."""
    usuario, form, bloqueio = await _gate_mutacao(request, db)
    if bloqueio is not None:
        return bloqueio

    competencia = competencia_valida(form.get("mes"))
    despesa = (
        db.query(DespesaFixaLoja)
        .filter(
            DespesaFixaLoja.id == despesa_id,
            DespesaFixaLoja.loja_slug == usuario.loja_slug,
        )
        .first()
    )
    if despesa is None:
        return _volta(competencia, "erro_form=dados")
    try:
        valor = dinheiro(form.get("valor"))
    except Exception:
        return _volta(competencia, "erro_form=valor")
    if valor < 0:
        return _volta(competencia, "erro_form=valor")

    existente = (
        db.query(DespesaFixaAjuste)
        .filter(
            DespesaFixaAjuste.despesa_id == despesa.id,
            DespesaFixaAjuste.competencia == competencia,
        )
        .first()
    )
    if existente is None:
        db.add(
            DespesaFixaAjuste(
                despesa_id=despesa.id, competencia=competencia, valor=valor
            )
        )
    else:
        existente.valor = valor
    db.commit()
    return _volta(competencia, "ok=ajustada")


@router.post(_DESPESAS + "/{despesa_id}/encerrar")
async def financeiro_despesa_encerrar(
    request: Request, despesa_id: str, db: Session = Depends(get_db)
):
    """Desativar = gravar a competência final.

    Não apaga a linha: os meses em que a despesa valeu continuam corretos
    quando alguém revisita o passado.
    """
    usuario, form, bloqueio = await _gate_mutacao(request, db)
    if bloqueio is not None:
        return bloqueio

    competencia = competencia_valida(form.get("mes"))
    despesa = (
        db.query(DespesaFixaLoja)
        .filter(
            DespesaFixaLoja.id == despesa_id,
            DespesaFixaLoja.loja_slug == usuario.loja_slug,
        )
        .first()
    )
    if despesa is None:
        return _volta(competencia, "erro_form=dados")

    despesa.fim_competencia = competencia
    despesa.atualizada_em = agora()
    db.commit()
    return _volta(competencia, "ok=encerrada")
