"""Cadastro, edicao e controle de acesso da equipe da loja."""

from __future__ import annotations

from fastapi import APIRouter

from app.main import (  # import tardio; main registra este router no fim
    Depends,
    EMAIL_EQUIPE_RE,
    HTMLResponse,
    IntegrityError,
    PAPEIS_EQUIPE,
    PAPEIS_EQUIPE_ROTULO,
    PAPEIS_IMUTAVEIS,
    RedirectResponse,
    Request,
    SENHA_EQUIPE_MINIMA,
    Session,
    Usuario,
    contexto,
    csrf_valido,
    get_db,
    hash_senha,
    pode_gerir_equipe,
    pode_ver_equipe,
    redirecionar_login,
    templates,
    usuario_atual,
)

router = APIRouter()


def _membro_da_loja(db: Session, usuario: Usuario, membro_id: str) -> Usuario | None:
    """Busca por id e loja na mesma consulta para impedir acesso entre tenants."""
    return (
        db.query(Usuario)
        .filter(Usuario.id == membro_id, Usuario.loja_slug == usuario.loja_slug)
        .first()
    )


def _membros_da_loja(db: Session, loja_slug: str) -> list[Usuario]:
    return (
        db.query(Usuario)
        .filter(Usuario.loja_slug == loja_slug)
        .order_by(Usuario.ativo.desc(), Usuario.nome, Usuario.email)
        .all()
    )


def _pode_editar_membro(usuario: Usuario, membro: Usuario) -> bool:
    """Contas protegidas só podem alterar os próprios dados e senha."""
    return membro.id == usuario.id or membro.papel in PAPEIS_EQUIPE


def _normalizar_nome(valor: str | None) -> str:
    nome = " ".join((valor or "").split())
    if len(nome) < 2:
        raise ValueError("Informe o nome completo do membro.")
    if len(nome) > 160:
        raise ValueError("O nome deve ter no máximo 160 caracteres.")
    return nome


def _normalizar_email(valor: str | None) -> str:
    email = (valor or "").strip().lower()
    if not email or len(email) > 320 or not EMAIL_EQUIPE_RE.fullmatch(email):
        raise ValueError("Informe um e-mail válido.")
    return email


def _validar_papel_equipe(valor: str | None) -> str:
    papel = (valor or "").strip()
    if papel not in PAPEIS_EQUIPE:
        raise ValueError("Selecione o papel gerente ou vendedor.")
    return papel


def _validar_nova_senha(senha: str | None, confirmacao: str | None) -> str:
    senha = senha or ""
    if len(senha) < SENHA_EQUIPE_MINIMA:
        raise ValueError(f"A senha deve ter pelo menos {SENHA_EQUIPE_MINIMA} caracteres.")
    if len(senha) > 256:
        raise ValueError("A senha deve ter no máximo 256 caracteres.")
    if senha != (confirmacao or ""):
        raise ValueError("A confirmação da senha não confere.")
    return senha


def _valores_membro_form(form) -> dict[str, str]:
    return {
        "nome": form.get("nome") or "",
        "email": form.get("email") or "",
        "papel": form.get("papel") or "vendedor",
    }


MSG_EQUIPE_CONTROL = "Contas e cargos são geridos no Revy Control"


def _equipe_estrutural_no_control() -> bool:
    """Mutações de equipe no Portal (dono).

    O desenho original migrava cadastro para o Control, mas o Control só
    convida **dono** (Admin Revy) e não expõe gerente/vendedor ao dono da
    loja. Enquanto isso, o dono gerencia a equipe operacional aqui.
    """
    return False


def _resposta_equipe_control_only(request: Request, usuario: Usuario | None):
    """403 legado (caminho Control-only). Mantido para testes/compat."""
    return templates.TemplateResponse(
        "erro.html",
        contexto(request, usuario, erro=MSG_EQUIPE_CONTROL),
        status_code=403,
    )


def _render_equipe_lista(
    request: Request,
    usuario: Usuario,
    db: Session,
    *,
    erro: str | None = None,
    status_code: int = 200,
    somente_leitura: bool | None = None,
):
    if somente_leitura is None:
        somente_leitura = _equipe_estrutural_no_control()
    return templates.TemplateResponse(
        "equipe/lista.html",
        contexto(
            request,
            usuario,
            membros=_membros_da_loja(db, usuario.loja_slug),
            papeis_rotulo=PAPEIS_EQUIPE_ROTULO,
            erro=erro,
            equipe_somente_leitura=somente_leitura,
            msg_equipe_control=MSG_EQUIPE_CONTROL if somente_leitura else None,
        ),
        status_code=status_code,
    )


def _render_membro_form(
    request: Request,
    usuario: Usuario,
    valores: dict[str, str],
    *,
    titulo: str,
    membro: Usuario | None = None,
    erro: str | None = None,
    status_code: int = 200,
):
    papel_bloqueado = bool(
        membro and (membro.papel in PAPEIS_IMUTAVEIS or membro.id == usuario.id)
    )
    return templates.TemplateResponse(
        "equipe/form.html",
        contexto(
            request,
            usuario,
            valores=valores,
            titulo=titulo,
            membro=membro,
            papeis=PAPEIS_EQUIPE,
            papeis_rotulo=PAPEIS_EQUIPE_ROTULO,
            papel_bloqueado=papel_bloqueado,
            erro=erro,
        ),
        status_code=status_code,
    )


@router.get("/app/equipe", response_class=HTMLResponse)
def equipe_lista(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    # Dono gerencia; gerente só consulta a lista.
    if not pode_ver_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    somente_leitura = (
        _equipe_estrutural_no_control() or not pode_gerir_equipe(usuario)
    )
    return _render_equipe_lista(
        request, usuario, db, somente_leitura=somente_leitura
    )


@router.get("/app/equipe/novo", response_class=HTMLResponse)
def equipe_novo(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    return _render_membro_form(
        request,
        usuario,
        {"nome": "", "email": "", "papel": "vendedor"},
        titulo="Adicionar membro",
    )


@router.post("/app/equipe/novo")
async def equipe_criar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    valores = _valores_membro_form(form)
    try:
        nome = _normalizar_nome(form.get("nome"))
        email = _normalizar_email(form.get("email"))
        papel = _validar_papel_equipe(form.get("papel"))
        senha = _validar_nova_senha(
            form.get("senha"), form.get("senha_confirmacao")
        )
    except ValueError as exc:
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Adicionar membro",
            erro=str(exc),
            status_code=422,
        )
    if db.query(Usuario.id).filter(Usuario.email == email).first():
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Adicionar membro",
            erro="Este e-mail não está disponível para cadastro.",
            status_code=422,
        )
    db.add(
        Usuario(
            email=email,
            nome=nome,
            senha_hash=hash_senha(senha),
            papel=papel,
            loja_slug=usuario.loja_slug,
            ativo=True,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Adicionar membro",
            erro="Este e-mail não está disponível para cadastro.",
            status_code=422,
        )
    return RedirectResponse("/app/equipe?ok=criado", status_code=303)


@router.get("/app/equipe/{membro_id}/editar", response_class=HTMLResponse)
def equipe_editar_pagina(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    valores = {"nome": membro.nome, "email": membro.email, "papel": membro.papel}
    return _render_membro_form(
        request,
        usuario,
        valores,
        titulo="Editar membro",
        membro=membro,
    )


@router.post("/app/equipe/{membro_id}/editar")
async def equipe_editar(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    valores = {
        "nome": form.get("nome") or "",
        "email": membro.email,
        "papel": form.get("papel") or membro.papel,
    }
    try:
        nome = _normalizar_nome(form.get("nome"))
        if membro.papel in PAPEIS_IMUTAVEIS or membro.id == usuario.id:
            papel = (form.get("papel") or membro.papel).strip()
            if papel != membro.papel:
                raise ValueError("O papel desta conta protegida não pode ser alterado.")
        else:
            papel = _validar_papel_equipe(form.get("papel"))
    except ValueError as exc:
        return _render_membro_form(
            request,
            usuario,
            valores,
            titulo="Editar membro",
            membro=membro,
            erro=str(exc),
            status_code=422,
        )
    membro.nome = nome
    membro.papel = papel
    db.commit()
    return RedirectResponse("/app/equipe?ok=editado", status_code=303)


@router.get("/app/equipe/{membro_id}/senha", response_class=HTMLResponse)
def equipe_senha_pagina(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    return templates.TemplateResponse(
        "equipe/senha.html",
        contexto(
            request,
            usuario,
            membro=membro,
            erro=None,
            senha_minima=SENHA_EQUIPE_MINIMA,
        ),
    )


@router.post("/app/equipe/{membro_id}/senha")
async def equipe_redefinir_senha(request: Request, membro_id: str, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if not _pode_editar_membro(usuario, membro):
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    try:
        senha = _validar_nova_senha(
            form.get("senha"), form.get("senha_confirmacao")
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "equipe/senha.html",
            contexto(
                request,
                usuario,
                membro=membro,
                erro=str(exc),
                senha_minima=SENHA_EQUIPE_MINIMA,
            ),
            status_code=422,
        )
    membro.senha_hash = hash_senha(senha)
    db.commit()
    return RedirectResponse("/app/equipe?ok=senha", status_code=303)


@router.post("/app/equipe/{membro_id}/{acao}")
async def equipe_alterar_acesso(
    request: Request,
    membro_id: str,
    acao: str,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if _equipe_estrutural_no_control():
        return _resposta_equipe_control_only(request, usuario)
    if not pode_gerir_equipe(usuario):
        return RedirectResponse("/app", status_code=303)
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return _render_equipe_lista(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página e tente novamente.",
            status_code=400,
        )
    membro = _membro_da_loja(db, usuario, membro_id)
    if not membro:
        return RedirectResponse("/app/equipe?erro=nao-encontrado", status_code=303)
    if acao not in {"ativar", "desativar"}:
        return RedirectResponse("/app/equipe?erro=acao", status_code=303)
    if acao == "desativar" and membro.id == usuario.id:
        return RedirectResponse("/app/equipe?erro=auto-desativacao", status_code=303)
    if membro.papel not in PAPEIS_EQUIPE:
        return RedirectResponse("/app/equipe?erro=conta-protegida", status_code=303)
    membro.ativo = acao == "ativar"
    db.commit()
    return RedirectResponse(f"/app/equipe?ok={acao}", status_code=303)
