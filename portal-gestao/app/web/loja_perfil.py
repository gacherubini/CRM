"""Perfil do usuário logado — dados da conta, avatar e troca de senha (própria).

Disponível a qualquer usuário autenticado (dono, gerente, vendedor, etc.).
Não depende de REVY_LOJA_SHELL_ENABLED: a UI legada também pode acessar
via redirect de /conta/senha ou link no header.

Avatar: OU um bichinho da galeria (`avatar_key`) OU uma foto enviada
(`foto_perfil`, bytes no banco — disco local não persiste no Fly).
NULL/NULL = inicial do nome, o comportamento de antes. Escolher um lado
limpa o outro; "usar inicial" limpa os dois.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

router = APIRouter(tags=["revy-loja-perfil"])

from app.auth import (  # noqa: E402
    csrf_valido,
    hash_senha,
    usuario_atual,
    verifica_senha,
)
from app.db import get_db  # noqa: E402
from app.main import (  # noqa: E402
    PAPEIS_EQUIPE_ROTULO,
    contexto,
    redirecionar_login,
    templates,
)
from app.models import Usuario  # noqa: E402
from app.password_rules import SenhaInvalida, validar_nova_senha  # noqa: E402

_TELA = "/app/loja/perfil"
_POST_SENHA = "/app/loja/perfil/senha"
_POST_AVATAR = "/app/loja/perfil/avatar"
_POST_FOTO = "/app/loja/perfil/foto"

_FOTO_MIMES = {"image/jpeg", "image/png", "image/webp"}
_FOTO_MAX_BYTES = 2 * 1024 * 1024

# Galeria de avatares padrão: 8 bichinhos originais em estilo "tile" ousado
# (fundo chapado vívido por bicho + rosto geométrico em alto contraste),
# mesma caixa (64x64 com cantos arredondados). Fonte única — os três lugares
# que mostram avatar (topbar, Perfil, Equipe) servem daqui via /foto/{id}.
_AVATAR_ATRIBUTOS = 'viewBox="0 0 64 64" aria-hidden="true"'
_AVATAR_CORPOS = {
    "gato": (
        '<rect width="64" height="64" rx="14" fill="#EA580C"/>'
        '<path d="M15 30 12 10l18 10z" fill="#FFF7ED"/>'
        '<path d="M49 30l3-20-18 10z" fill="#FFF7ED"/>'
        '<path d="M18 26l-2-9 9 5z" fill="#EA580C"/>'
        '<path d="M46 26l2-9-9 5z" fill="#EA580C"/>'
        '<ellipse cx="32" cy="39" rx="18" ry="15" fill="#FFF7ED"/>'
        '<circle cx="25" cy="38" r="3.4" fill="#1F2937"/>'
        '<circle cx="39" cy="38" r="3.4" fill="#1F2937"/>'
        '<circle cx="26.2" cy="36.8" r="1.1" fill="#FFFFFF"/>'
        '<circle cx="40.2" cy="36.8" r="1.1" fill="#FFFFFF"/>'
        '<path d="M29 44h6l-3 3.6z" fill="#1F2937"/>'
        '<path d="M32 47.6v2.2M32 49.8c-1.8 1.8-4.6 1.8-6.4 0'
        'M32 49.8c1.8 1.8 4.6 1.8 6.4 0" stroke="#1F2937" '
        'stroke-width="2" stroke-linecap="round" fill="none"/>'
    ),
    "cachorro": (
        '<rect width="64" height="64" rx="14" fill="#2563EB"/>'
        '<path d="M15 20c-7 1-9 17-5 23 2.4 3.4 8 2.2 8.4-2.4L19 26z" fill="#1F2937"/>'
        '<path d="M49 20c7 1 9 17 5 23-2.4 3.4-8 2.2-8.4-2.4L45 26z" fill="#1F2937"/>'
        '<ellipse cx="32" cy="36" rx="16" ry="15" fill="#FFF7ED"/>'
        '<ellipse cx="39" cy="30" rx="6" ry="5.4" fill="#FBBF24"/>'
        '<circle cx="26" cy="35" r="3.2" fill="#1F2937"/>'
        '<circle cx="38" cy="35" r="3.2" fill="#1F2937"/>'
        '<ellipse cx="32" cy="44" rx="8.5" ry="6.5" fill="#FFFFFF"/>'
        '<ellipse cx="32" cy="42" rx="3.6" ry="2.8" fill="#1F2937"/>'
        '<path d="M32 45v3" stroke="#1F2937" stroke-width="2" stroke-linecap="round"/>'
    ),
    "raposa": (
        '<rect width="64" height="64" rx="14" fill="#DC2626"/>'
        '<path d="M16 30 14 8l16 11z" fill="#FFF7ED"/>'
        '<path d="M48 30l2-22-16 11z" fill="#FFF7ED"/>'
        '<path d="M15 16l-1-8 8 5z" fill="#1F2937"/>'
        '<path d="M49 16l1-8-8 5z" fill="#1F2937"/>'
        '<path d="M16 30c0 12 7 20 16 20s16-8 16-20c0-3-7-6-16-6s-16 3-16 6z" fill="#FFF7ED"/>'
        '<circle cx="26" cy="36" r="3.2" fill="#1F2937"/>'
        '<circle cx="38" cy="36" r="3.2" fill="#1F2937"/>'
        '<circle cx="32" cy="42.5" r="2.6" fill="#1F2937"/>'
        '<path d="M32 45v1.8M32 46.8c-1.6 1.6-4 1.6-5.6 0'
        'M32 46.8c1.6 1.6 4 1.6 5.6 0" stroke="#1F2937" '
        'stroke-width="2" stroke-linecap="round" fill="none"/>'
    ),
    "urso": (
        '<rect width="64" height="64" rx="14" fill="#9333EA"/>'
        '<circle cx="17" cy="18" r="7" fill="#FFF7ED"/>'
        '<circle cx="47" cy="18" r="7" fill="#FFF7ED"/>'
        '<circle cx="17" cy="18" r="3" fill="#9333EA"/>'
        '<circle cx="47" cy="18" r="3" fill="#9333EA"/>'
        '<circle cx="32" cy="38" r="17" fill="#FFF7ED"/>'
        '<circle cx="26" cy="36" r="3.2" fill="#1F2937"/>'
        '<circle cx="38" cy="36" r="3.2" fill="#1F2937"/>'
        '<circle cx="27.2" cy="34.8" r="1.1" fill="#FFFFFF"/>'
        '<circle cx="39.2" cy="34.8" r="1.1" fill="#FFFFFF"/>'
        '<ellipse cx="32" cy="45" rx="8" ry="6" fill="#E9D5FF"/>'
        '<ellipse cx="32" cy="43" rx="3.4" ry="2.6" fill="#1F2937"/>'
        '<path d="M32 45.6v2M32 47.6c-1.6 1.4-4 1.4-5.4 0'
        'M32 47.6c1.6 1.4 4 1.4 5.4 0" stroke="#1F2937" '
        'stroke-width="2" stroke-linecap="round" fill="none"/>'
    ),
    "coelho": (
        '<rect width="64" height="64" rx="14" fill="#0D9488"/>'
        '<rect x="22" y="4" width="8" height="22" rx="4" fill="#FFF7ED"/>'
        '<rect x="34" y="4" width="8" height="22" rx="4" fill="#FFF7ED"/>'
        '<rect x="24.5" y="8" width="3" height="14" rx="1.5" fill="#0D9488"/>'
        '<rect x="36.5" y="8" width="3" height="14" rx="1.5" fill="#0D9488"/>'
        '<circle cx="32" cy="42" r="14" fill="#FFF7ED"/>'
        '<circle cx="27" cy="41" r="3" fill="#1F2937"/>'
        '<circle cx="37" cy="41" r="3" fill="#1F2937"/>'
        '<path d="M29.5 46h5l-2.5 3z" fill="#DB2777"/>'
        '<rect x="29.5" y="50" width="5" height="5" rx="1" fill="#FFFFFF" '
        'stroke="#1F2937" stroke-width="1.6"/>'
    ),
    "sapo": (
        '<rect width="64" height="64" rx="14" fill="#16A34A"/>'
        '<circle cx="21" cy="18" r="8" fill="#DCFCE7"/>'
        '<circle cx="43" cy="18" r="8" fill="#DCFCE7"/>'
        '<circle cx="21" cy="18" r="3.6" fill="#1F2937"/>'
        '<circle cx="43" cy="18" r="3.6" fill="#1F2937"/>'
        '<circle cx="22.2" cy="16.8" r="1.2" fill="#FFFFFF"/>'
        '<circle cx="44.2" cy="16.8" r="1.2" fill="#FFFFFF"/>'
        '<rect x="12" y="26" width="40" height="26" rx="13" fill="#DCFCE7"/>'
        '<circle cx="20" cy="37" r="2.4" fill="#86EFAC"/>'
        '<circle cx="44" cy="37" r="2.4" fill="#86EFAC"/>'
        '<path d="M22 40c3.5 4.5 16.5 4.5 20 0" stroke="#15803D" '
        'stroke-width="3" stroke-linecap="round" fill="none"/>'
    ),
    "panda": (
        '<rect width="64" height="64" rx="14" fill="#DB2777"/>'
        '<circle cx="17" cy="20" r="7" fill="#1F2937"/>'
        '<circle cx="47" cy="20" r="7" fill="#1F2937"/>'
        '<circle cx="32" cy="38" r="17" fill="#FFFFFF"/>'
        '<ellipse cx="25" cy="36" rx="5" ry="6" fill="#1F2937" transform="rotate(-15 25 36)"/>'
        '<ellipse cx="39" cy="36" rx="5" ry="6" fill="#1F2937" transform="rotate(15 39 36)"/>'
        '<circle cx="25" cy="35" r="1.5" fill="#FFFFFF"/>'
        '<circle cx="39" cy="35" r="1.5" fill="#FFFFFF"/>'
        '<ellipse cx="32" cy="45" rx="3" ry="2.4" fill="#1F2937"/>'
        '<path d="M32 47.4v1.8M32 49.2c-1.5 1.3-3.8 1.3-5 0'
        'M32 49.2c1.5 1.3 3.8 1.3 5 0" stroke="#1F2937" '
        'stroke-width="2" stroke-linecap="round" fill="none"/>'
    ),
    "pinguim": (
        '<rect width="64" height="64" rx="14" fill="#0891B2"/>'
        '<ellipse cx="32" cy="36" rx="16" ry="19" fill="#1F2937"/>'
        '<ellipse cx="32" cy="41" rx="10" ry="12" fill="#FFFFFF"/>'
        '<circle cx="27" cy="28" r="4" fill="#FFFFFF"/>'
        '<circle cx="37" cy="28" r="4" fill="#FFFFFF"/>'
        '<circle cx="27" cy="28.5" r="2" fill="#1F2937"/>'
        '<circle cx="37" cy="28.5" r="2" fill="#1F2937"/>'
        '<path d="M28 33h8l-4 4.5z" fill="#F59E0B"/>'
        '<ellipse cx="25" cy="54" rx="4" ry="2.2" fill="#F59E0B"/>'
        '<ellipse cx="39" cy="54" rx="4" ry="2.2" fill="#F59E0B"/>'
    ),
}
AVATAR_PRESETS: tuple[str, ...] = tuple(_AVATAR_CORPOS)
AVATAR_ROTULOS = {
    "gato": "Gato",
    "cachorro": "Cachorro",
    "raposa": "Raposa",
    "urso": "Urso",
    "coelho": "Coelho",
    "sapo": "Sapo",
    "panda": "Panda",
    "pinguim": "Pinguim",
}


def avatar_svg(key: str | None) -> str:
    """SVG inline do bichinho, ou "" quando a key não é um preset válido."""
    corpo = _AVATAR_CORPOS.get((key or "").strip().lower())
    if corpo is None:
        return ""
    return f"<svg {_AVATAR_ATRIBUTOS}>{corpo}</svg>"


def _mime_por_assinatura(conteudo: bytes) -> str | None:
    """MIME pela assinatura binária — cabeçalho do upload não é confiável.

    SVG nunca entra aqui de propósito (XSS via <script> embutido): a
    allowlist é só jpeg/png/webp, e sem assinatura conhecida não serve.
    """
    if conteudo[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if conteudo[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(conteudo) >= 12 and conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp"
    return None


def aplicar_troca_senha(
    usuario: Usuario,
    *,
    senha_atual: str,
    senha: str,
    senha_confirmacao: str,
) -> str | None:
    """Valida e aplica hash da nova senha no objeto usuário (sem commit).

    Retorna mensagem de erro em PT-BR ou None em caso de sucesso.
    """
    if not verifica_senha(usuario.senha_hash, senha_atual):
        return "Senha atual incorreta."
    try:
        senha_validada = validar_nova_senha(senha, senha_confirmacao)
    except SenhaInvalida as exc:
        return str(exc)
    usuario.senha_hash = hash_senha(senha_validada)
    return None


def _render_perfil(
    request: Request,
    usuario: Usuario,
    db: Session,
    *,
    erro: str | None = None,
    mensagem: str | None = None,
    status_code: int = 200,
):
    papel = (usuario.papel or "").strip().casefold()
    return templates.TemplateResponse(
        "loja/perfil.html",
        contexto(
            request,
            usuario,
            db,
            erro=erro,
            mensagem=mensagem,
            papel_rotulo=PAPEIS_EQUIPE_ROTULO.get(papel, usuario.papel or "—"),
            avatares=[
                {
                    "key": key,
                    "rotulo": AVATAR_ROTULOS[key],
                    "svg": avatar_svg(key),
                }
                for key in AVATAR_PRESETS
            ],
            avatar_atual=(usuario.avatar_key or "").strip().lower()
            if usuario.avatar_key
            else "",
            tem_foto=bool(usuario.foto_perfil),
        ),
        status_code=status_code,
    )


@router.get(_TELA, response_class=HTMLResponse)
def loja_perfil(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    return _render_perfil(request, usuario, db)


@router.post(_POST_SENHA, response_class=HTMLResponse)
def loja_perfil_senha_salvar(
    request: Request,
    senha_atual: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    senha_confirmacao: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not csrf_valido(request, csrf):
        return _render_perfil(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página.",
            status_code=400,
        )
    erro = aplicar_troca_senha(
        usuario,
        senha_atual=senha_atual,
        senha=senha,
        senha_confirmacao=senha_confirmacao,
    )
    if erro:
        return _render_perfil(request, usuario, db, erro=erro, status_code=400)
    db.commit()
    return _render_perfil(
        request, usuario, db, mensagem="Senha alterada com sucesso."
    )


@router.post(_POST_AVATAR, response_class=HTMLResponse)
def loja_perfil_avatar_salvar(
    request: Request,
    avatar_key: Annotated[str | None, Form()] = None,
    csrf: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not csrf_valido(request, csrf):
        return _render_perfil(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página.",
            status_code=400,
        )
    escolha = (avatar_key or "").strip().lower()
    if not escolha or escolha == "inicial":
        usuario.avatar_key = None
        usuario.foto_perfil = None
        db.commit()
        return _render_perfil(
            request, usuario, db, mensagem="Foto removida. Voltou a inicial."
        )
    if escolha not in _AVATAR_CORPOS:
        return _render_perfil(
            request,
            usuario,
            db,
            erro="Avatar inválido. Escolha um dos bichinhos ou a inicial.",
            status_code=400,
        )
    usuario.avatar_key = escolha
    usuario.foto_perfil = None
    db.commit()
    return _render_perfil(request, usuario, db, mensagem="Avatar atualizado.")


@router.post(_POST_FOTO, response_class=HTMLResponse)
async def loja_perfil_foto_salvar(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    form = await request.form()
    csrf = form.get("csrf")
    if not csrf_valido(request, csrf if isinstance(csrf, str) else None):
        return _render_perfil(
            request,
            usuario,
            db,
            erro="Sessão expirada. Recarregue a página.",
            status_code=400,
        )
    foto = form.get("foto")
    conteudo: bytes | None = None
    if foto is not None and hasattr(foto, "read") and getattr(foto, "filename", ""):
        conteudo = await foto.read()
    erro: str | None = None
    if not conteudo:
        erro = "Escolha um arquivo de imagem para enviar."
    elif len(conteudo) > _FOTO_MAX_BYTES:
        erro = "A foto excede o limite de 2 MB. Escolha uma imagem menor."
    elif (getattr(foto, "content_type", "") or "").lower() not in _FOTO_MIMES:
        erro = "Formato de foto inválido (use JPG, PNG ou WEBP)."
    elif _mime_por_assinatura(conteudo) is None:
        erro = "Formato de foto inválido (use JPG, PNG ou WEBP)."
    if erro:
        # Sem stack no log de propósito: upload inválido é erro do usuário,
        # não falha do servidor — e o corpo do arquivo nunca vai para log.
        return _render_perfil(request, usuario, db, erro=erro, status_code=400)
    assert conteudo is not None
    usuario.foto_perfil = conteudo
    usuario.avatar_key = None
    db.commit()
    return _render_perfil(
        request, usuario, db, mensagem="Foto de perfil atualizada."
    )


@router.get("/app/loja/perfil/foto/{usuario_id}")
def loja_perfil_foto_ver(
    request: Request, usuario_id: str, db: Session = Depends(get_db)
):
    """Serve o avatar/foto de um membro da MESMA loja.

    404 para fora da loja e para inexistente, sem distinguir: o id na URL
    não pode virar oráculo de quem existe em outra loja. Sem dado sensível
    aqui — só a imagem que a própria Equipe já lista.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    alvo = db.get(Usuario, usuario_id)
    if alvo is None or alvo.loja_slug != usuario.loja_slug:
        return Response(status_code=404)
    if alvo.foto_perfil:
        conteudo = bytes(alvo.foto_perfil)
        mime = _mime_por_assinatura(conteudo) or "application/octet-stream"
        return Response(
            content=conteudo,
            media_type=mime,
            headers={"Cache-Control": "private, max-age=300"},
        )
    svg = avatar_svg(alvo.avatar_key)
    if svg:
        return Response(
            content=svg.encode("utf-8"),
            media_type="image/svg+xml",
            headers={"Cache-Control": "private, max-age=300"},
        )
    return Response(status_code=404)
