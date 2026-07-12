from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import servico
from app.admin_auth import (
    autenticar, csrf_token, csrf_valido, encerrar_sessao, iniciar_sessao, usuario_atual,
)
from app.db import get_db
from app.models_db import Loja, UsuarioEstoque

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _contexto(request: Request, db: Session, usuario: UsuarioEstoque | None = None, **extra):
    loja = db.get(Loja, usuario.loja_id) if usuario else None
    return {
        "usuario": usuario,
        "loja": loja,
        "csrf": csrf_token(request),
        "pode_operar": bool(usuario and usuario.papel in {"dono", "gerente", "operador"}),
        "pode_custo": bool(usuario and usuario.papel in {"dono", "gerente"}),
        **extra,
    }


def _login_redirect():
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/admin/login", response_class=HTMLResponse)
def login_pagina(request: Request, db: Session = Depends(get_db)):
    if usuario_atual(request, db):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "admin/login.html", _contexto(request, db))


@router.post("/admin/login", response_class=HTMLResponse)
def login(
    request: Request,
    loja_slug: Annotated[str, Form()],
    email: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    if not csrf_valido(request, csrf):
        return templates.TemplateResponse(
            request, "admin/login.html", _contexto(request, db, erro="Sessão expirada."), status_code=400
        )
    usuario = autenticar(db, loja_slug, email, senha)
    if not usuario:
        return templates.TemplateResponse(
            request, "admin/login.html", _contexto(request, db, erro="Loja, e-mail ou senha inválidos."), status_code=401
        )
    iniciar_sessao(request, usuario)
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/logout")
def logout(request: Request, csrf: Annotated[str, Form()]):
    if csrf_valido(request, csrf):
        encerrar_sessao(request)
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/admin", response_class=HTMLResponse)
def painel(
    request: Request,
    busca: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    veiculos = servico.listar_veiculos(db, usuario.loja_id, status=status, busca=busca)
    metricas = {
        "total": len(veiculos),
        "disponiveis": sum(v.status == "disponivel" for v in veiculos),
        "publicados": sum(v.publicado for v in veiculos),
        "reservados": sum(v.status == "reservado" for v in veiculos),
    }
    return templates.TemplateResponse(
        request,
        "admin/painel.html",
        _contexto(request, db, usuario, veiculos=veiculos, metricas=metricas, busca=busca or "", status=status or ""),
    )


def _dados_form(form, pode_custo: bool):
    dados = {
        "tipo": form.get("tipo", ""), "marca": form.get("marca", "").strip(),
        "modelo": form.get("modelo", "").strip(), "versao": form.get("versao", "").strip() or None,
        "ano_modelo": int(form.get("ano_modelo", 0)), "cor": form.get("cor", "").strip() or None,
        "km": int(form.get("km") or 0), "preco": float(str(form.get("preco", "0")).replace(",", ".")),
        "codigo_interno": form.get("codigo_interno", "").strip() or None,
    }
    if pode_custo and form.get("custo"):
        dados["custo"] = float(str(form.get("custo")).replace(",", "."))
    return dados


@router.get("/admin/veiculos/novo", response_class=HTMLResponse)
def novo_pagina(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    if usuario.papel not in {"dono", "gerente", "operador"}:
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin/form.html", _contexto(request, db, usuario, veiculo=None, titulo="Novo veículo")
    )


@router.post("/admin/veiculos/novo")
async def novo(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    form = await request.form()
    if usuario.papel not in {"dono", "gerente", "operador"} or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/admin", status_code=303)
    try:
        veiculo = servico.criar_veiculo(
            db, usuario.loja_id, _dados_form(form, usuario.papel in {"dono", "gerente"}), usuario.papel
        )
        fotos = [u.strip() for u in form.get("fotos", "").splitlines() if u.strip()]
        if fotos:
            servico.substituir_fotos(db, usuario.loja_id, veiculo.id, fotos, usuario.papel)
    except Exception as exc:
        detalhe = getattr(exc, "detail", str(exc))
        return templates.TemplateResponse(
            request, "admin/form.html",
            _contexto(request, db, usuario, veiculo=dict(form), titulo="Novo veículo", erro=detalhe),
            status_code=422,
        )
    return RedirectResponse("/admin?ok=criado", status_code=303)


@router.get("/admin/veiculos/{veiculo_id}", response_class=HTMLResponse)
def editar_pagina(request: Request, veiculo_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    veiculo = servico.obter_veiculo(db, usuario.loja_id, veiculo_id)
    return templates.TemplateResponse(
        request, "admin/form.html", _contexto(request, db, usuario, veiculo=veiculo, titulo="Editar veículo")
    )


@router.post("/admin/veiculos/{veiculo_id}")
async def editar(request: Request, veiculo_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    form = await request.form()
    if usuario.papel not in {"dono", "gerente", "operador"} or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/admin", status_code=303)
    try:
        servico.atualizar_veiculo(
            db, usuario.loja_id, veiculo_id,
            _dados_form(form, usuario.papel in {"dono", "gerente"}), usuario.papel,
        )
        fotos = [u.strip() for u in form.get("fotos", "").splitlines() if u.strip()]
        servico.substituir_fotos(db, usuario.loja_id, veiculo_id, fotos, usuario.papel)
    except Exception as exc:
        detalhe = getattr(exc, "detail", str(exc))
        return templates.TemplateResponse(
            request, "admin/form.html",
            _contexto(request, db, usuario, veiculo={**dict(form), "id": veiculo_id}, titulo="Editar veículo", erro=detalhe),
            status_code=422,
        )
    return RedirectResponse("/admin?ok=atualizado", status_code=303)


@router.post("/admin/veiculos/{veiculo_id}/{acao}")
async def acao(request: Request, veiculo_id: str, acao: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    form = await request.form()
    if usuario.papel not in {"dono", "gerente", "operador"} or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/admin", status_code=303)
    operacoes = {
        "publicar": lambda: servico.definir_publicado(db, usuario.loja_id, veiculo_id, True, usuario.papel),
        "despublicar": lambda: servico.definir_publicado(db, usuario.loja_id, veiculo_id, False, usuario.papel),
        "reservar": lambda: servico.reservar(db, usuario.loja_id, veiculo_id, usuario.papel),
        "vender": lambda: servico.vender(db, usuario.loja_id, veiculo_id, usuario.papel),
    }
    if acao not in operacoes:
        return RedirectResponse("/admin?erro=acao", status_code=303)
    try:
        operacoes[acao]()
    except Exception:
        return RedirectResponse("/admin?erro=acao", status_code=303)
    return RedirectResponse(f"/admin?ok={acao}", status_code=303)


@router.post("/admin/importar")
async def importar(
    request: Request,
    arquivo: UploadFile = File(),
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return _login_redirect()
    form = await request.form()
    if usuario.papel not in {"dono", "gerente", "operador"} or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/admin", status_code=303)
    conteudo = await arquivo.read()
    resultado = servico.importar_csv(
        db, usuario.loja_id, conteudo, arquivo.filename or "estoque.csv", usuario.papel,
        usuario.papel in {"dono", "gerente"},
    )
    return RedirectResponse(f"/admin?importacao={resultado.status}", status_code=303)
