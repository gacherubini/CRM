"""Cadastro e manutencao das metas comerciais da loja."""

from __future__ import annotations

from fastapi import APIRouter

from app.main import (  # import tardio; main registra este router no fim
    Decimal,
    Depends,
    HTMLResponse,
    InvalidOperation,
    Meta,
    RedirectResponse,
    Request,
    Session,
    TIPOS_META,
    Usuario,
    contexto,
    csrf_valido,
    date,
    dinheiro,
    get_db,
    pode_gerir_metas,
    redirecionar_login,
    templates,
    usuario_atual,
)

router = APIRouter()


def valores_meta_form(form) -> dict[str, str]:
    return {
        campo: (form.get(campo) or "")
        for campo in ("escopo", "vendedor_email", "tipo", "periodo_inicio", "periodo_fim", "valor_alvo")
    }


def vendedores_da_loja(db: Session, loja_slug: str) -> list[Usuario]:
    return (
        db.query(Usuario)
        .filter(Usuario.loja_slug == loja_slug, Usuario.papel == "vendedor", Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
        .all()
    )


def validar_meta_form(form, db: Session, loja_slug: str) -> tuple[str, str | None, str, date, date, Decimal]:
    escopo = (form.get("escopo") or "loja").strip()
    if escopo not in ("loja", "vendedor"):
        raise ValueError("Selecione um escopo de meta válido.")
    vendedor_email = None
    if escopo == "vendedor":
        vendedor_email = (form.get("vendedor_email") or "").strip().lower()
        if not vendedor_email:
            raise ValueError("Selecione o vendedor para a meta individual.")
        vendedor = db.query(Usuario).filter(
            Usuario.email == vendedor_email,
            Usuario.loja_slug == loja_slug,
            Usuario.papel == "vendedor",
            Usuario.ativo.is_(True),
        ).first()
        if not vendedor:
            raise ValueError("Selecione um vendedor ativo desta loja.")
    tipo = (form.get("tipo") or "").strip()
    if tipo not in TIPOS_META:
        raise ValueError("Selecione um tipo de meta válido.")
    try:
        inicio = date.fromisoformat(form.get("periodo_inicio") or "")
        fim = date.fromisoformat(form.get("periodo_fim") or "")
    except ValueError as exc:
        raise ValueError("Informe um período válido.") from exc
    if inicio > fim:
        raise ValueError("A data inicial não pode ser posterior à data final.")
    try:
        alvo = dinheiro(form.get("valor_alvo"))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Informe um alvo válido.") from exc
    if alvo <= 0:
        raise ValueError("O alvo deve ser maior que zero.")
    if tipo == "quantidade" and alvo != alvo.to_integral_value():
        raise ValueError("A meta de quantidade deve ser um número inteiro.")
    return escopo, vendedor_email, tipo, inicio, fim, alvo


def meta_sobreposta(
    db: Session,
    loja_slug: str,
    escopo: str,
    vendedor_email: str | None,
    tipo: str,
    inicio: date,
    fim: date,
    ignorar_id: str | None = None,
) -> bool:
    consulta = db.query(Meta).filter(
        Meta.loja_slug == loja_slug,
        Meta.escopo == escopo,
        Meta.tipo == tipo,
        Meta.ativa.is_(True),
        Meta.periodo_inicio <= fim,
        Meta.periodo_fim >= inicio,
    )
    if escopo == "vendedor":
        consulta = consulta.filter(Meta.vendedor_email == vendedor_email)
    if ignorar_id:
        consulta = consulta.filter(Meta.id != ignorar_id)
    return consulta.first() is not None


def render_meta_form(
    request: Request,
    usuario,
    valores,
    titulo: str,
    db: Session,
    erro: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "metas/form.html",
        contexto(
            request,
            usuario,
            valores=valores,
            titulo=titulo,
            tipos=TIPOS_META,
            vendedores=vendedores_da_loja(db, usuario.loja_slug),
            erro=erro,
        ),
        status_code=status_code,
    )


@router.get("/app/metas", response_class=HTMLResponse)
def metas_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    pode_gerir = pode_gerir_metas(usuario)
    consulta = db.query(Meta).filter(Meta.loja_slug == usuario.loja_slug)
    # Metas por vendedor expõem escopo individual: só dono/gerente veem a lista completa.
    # Vendedores continuam vendo somente as metas da loja aqui (o atingimento individual
    # deles é exibido no próprio painel, em /app/vendedor).
    if pode_gerir:
        consulta = consulta.filter(Meta.escopo.in_(["loja", "vendedor"]))
    else:
        consulta = consulta.filter(Meta.escopo == "loja")
    metas = consulta.order_by(Meta.ativa.desc(), Meta.periodo_inicio.desc()).all()
    vendedores_por_email = {
        vendedor.email: vendedor
        for vendedor in db.query(Usuario).filter(Usuario.loja_slug == usuario.loja_slug).all()
    }
    return templates.TemplateResponse(
        "metas/lista.html",
        contexto(
            request,
            usuario,
            metas=metas,
            tipos=TIPOS_META,
            pode_gerir=pode_gerir,
            vendedores_por_email=vendedores_por_email,
        ),
    )


@router.get("/app/metas/nova", response_class=HTMLResponse)
def metas_nova(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_metas(usuario):
        return RedirectResponse("/app/metas", status_code=303)
    return render_meta_form(request, usuario, {}, "Cadastrar meta", db)


@router.post("/app/metas/nova")
async def metas_criar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_metas(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/metas", status_code=303)
    valores = valores_meta_form(form)
    try:
        escopo, vendedor_email, tipo, inicio, fim, alvo = validar_meta_form(form, db, usuario.loja_slug)
    except ValueError as exc:
        return render_meta_form(request, usuario, valores, "Cadastrar meta", db, str(exc), 422)
    if meta_sobreposta(db, usuario.loja_slug, escopo, vendedor_email, tipo, inicio, fim):
        return render_meta_form(
            request,
            usuario,
            valores,
            "Cadastrar meta",
            db,
            "Já existe uma meta ativa desse tipo sobrepondo o período informado.",
            422,
        )
    db.add(
        Meta(
            loja_slug=usuario.loja_slug,
            escopo=escopo,
            vendedor_email=vendedor_email,
            tipo=tipo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            valor_alvo=alvo,
            ativa=True,
        )
    )
    db.commit()
    return RedirectResponse("/app/metas?ok=criada", status_code=303)


@router.get("/app/metas/{meta_id}/editar", response_class=HTMLResponse)
def metas_editar_pagina(request: Request, meta_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not pode_gerir_metas(usuario):
        return RedirectResponse("/app/metas", status_code=303)
    meta = db.query(Meta).filter(Meta.id == meta_id, Meta.loja_slug == usuario.loja_slug).first()
    if not meta or not meta.ativa:
        return RedirectResponse("/app/metas?erro=nao-encontrada", status_code=303)
    valores = {
        "escopo": meta.escopo,
        "vendedor_email": meta.vendedor_email or "",
        "tipo": meta.tipo,
        "periodo_inicio": meta.periodo_inicio.isoformat(),
        "periodo_fim": meta.periodo_fim.isoformat(),
        "valor_alvo": str(meta.valor_alvo),
    }
    return render_meta_form(request, usuario, valores, "Editar meta", db)


@router.post("/app/metas/{meta_id}/editar")
async def metas_editar(request: Request, meta_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_metas(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/metas", status_code=303)
    meta = db.query(Meta).filter(Meta.id == meta_id, Meta.loja_slug == usuario.loja_slug).first()
    if not meta or not meta.ativa:
        return RedirectResponse("/app/metas?erro=nao-encontrada", status_code=303)
    valores = valores_meta_form(form)
    try:
        escopo, vendedor_email, tipo, inicio, fim, alvo = validar_meta_form(form, db, usuario.loja_slug)
    except ValueError as exc:
        return render_meta_form(request, usuario, valores, "Editar meta", db, str(exc), 422)
    if meta_sobreposta(db, usuario.loja_slug, escopo, vendedor_email, tipo, inicio, fim, ignorar_id=meta.id):
        return render_meta_form(
            request,
            usuario,
            valores,
            "Editar meta",
            db,
            "Já existe uma meta ativa desse tipo sobrepondo o período informado.",
            422,
        )
    meta.escopo = escopo
    meta.vendedor_email = vendedor_email
    meta.tipo = tipo
    meta.periodo_inicio = inicio
    meta.periodo_fim = fim
    meta.valor_alvo = alvo
    db.commit()
    return RedirectResponse("/app/metas?ok=editada", status_code=303)


@router.post("/app/metas/{meta_id}/desativar")
async def metas_desativar(request: Request, meta_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    if not pode_gerir_metas(usuario) or not csrf_valido(request, form.get("csrf")):
        return RedirectResponse("/app/metas", status_code=303)
    meta = db.query(Meta).filter(Meta.id == meta_id, Meta.loja_slug == usuario.loja_slug).first()
    if not meta:
        return RedirectResponse("/app/metas?erro=nao-encontrada", status_code=303)
    meta.ativa = False
    db.commit()
    return RedirectResponse("/app/metas?ok=desativada", status_code=303)
