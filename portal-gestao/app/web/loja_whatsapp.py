"""Canais WhatsApp na Loja (Ajustes) — dono/gerente cadastram e pareiam números.

QR nunca vai a log nem a auditoria: vive só no request/response do conectar. A
sessão carrega apenas um token curto; o payload fica no store de `qr_efemero`,
porque um QR em base64 estouraria o limite de ~4 KB do cookie.
Gated por REVY_LOJA_SHELL_ENABLED + REVY_LOJA_WHATSAPP_ENABLED (default off).

Também hospeda o WhatsApp do catálogo (CTA da vitrine), gravado no Estoque —
independente dos canais Evolution.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import csrf_valido, usuario_atual  # noqa: E402
from app.clients.chatbot import ChatbotIndisponivel, OnboardingFalhou  # noqa: E402
from app.clients.estoque import EstoqueClient, EstoqueIndisponivel  # noqa: E402
from app.config import (  # noqa: E402
    portal_meta_app_id,
    portal_meta_config_id,
    revy_loja_shell_enabled,
    revy_loja_whatsapp_enabled,
)
from app.db import get_db  # noqa: E402
from app.loja import qr_efemero  # noqa: E402
from app.loja.types import ROLES_GESTAO, Role  # noqa: E402
from app.loja.whatsapp_canais import ROTULOS, montar_canais_view  # noqa: E402
from app.loja_operacao_auditoria import registrar_auditoria_canal  # noqa: E402
from app.main import (  # noqa: E402
    contexto,
    get_chatbot_client,
    get_estoque_client,
    redirecionar_login,
    templates,
)

_TELA = "/app/loja/whatsapp"
_TELA_FILA = "/app/loja/whatsapp/fila"
_TELA_DECIDIR = "/app/loja/whatsapp/conectar"
# Erro genérico: nenhuma mensagem de canal carrega QR nem detalhe de provedor.
_ERRO_CHATBOT = "chatbot_indisponivel"

# As três saídas do popup pedem frases diferentes. Juntá-las faria o lojista
# tentar de novo quando o problema é dele (número ainda no aparelho), ou
# desistir quando o problema é nosso (chatbot fora do ar).
_ERRO_POPUP_INCOMPLETO = (
    "A janela da Meta fechou sem concluir a conexão. Nenhum número foi migrado. "
    "O motivo mais comum é o número ainda estar ativo no aplicativo de WhatsApp "
    "em algum aparelho: apague a conta dele no aplicativo e comece de novo."
)
_ERRO_CLOUD_INDISPONIVEL = (
    "A janela da Meta concluiu, mas a Revy não conseguiu registrar a conexão "
    "agora. Não refaça a janela: tente de novo em instantes."
)


def _habilitado() -> bool:
    """Gate duplo, lido em runtime (Settings é snapshot de boot)."""
    return revy_loja_shell_enabled() and revy_loja_whatsapp_enabled()


def _autorizado(usuario) -> bool:
    return (getattr(usuario, "papel", "") or "").strip().casefold() in ROLES_GESTAO


def _e_dono(usuario) -> bool:
    """Quem conecta o WhatsApp na nuvem precisa ser admin do portfólio
    empresarial na Meta — gerente normalmente não é. Ele vê a tela, mas o
    botão é só do dono."""
    return (
        getattr(usuario, "papel", "") or ""
    ).strip().casefold() == Role.DONO.value


def _para_app() -> RedirectResponse:
    return RedirectResponse("/app", status_code=303)


def _para_fila() -> RedirectResponse:
    return RedirectResponse(_TELA_FILA, status_code=303)


def _equipe_para_fila(db: Session, loja_slug: str):
    """Quem pode entrar na fila: gente ativa da loja.

    Vem da equipe e não de texto livre porque é daqui que sai o ``Usuario.id``
    que vira destinatário do sino.
    """
    from app.models import Usuario

    return (
        db.query(Usuario)
        .filter(Usuario.loja_slug == loja_slug, Usuario.ativo.is_(True))
        .order_by(Usuario.nome, Usuario.email)
        .all()
    )


def _para_tela() -> RedirectResponse:
    return RedirectResponse(_TELA, status_code=303)


def _carregar_meta_catalogo(
    estoque: EstoqueClient,
) -> tuple[str, str, str | None]:
    """Lê WhatsApp CTA + URL do catálogo no Estoque; falha best-effort."""
    obter = getattr(estoque, "obter_loja", None)
    if not callable(obter):
        # Fakes legados de testes / cliente sem o método ainda.
        return "", "", None
    try:
        dados = obter()
        return (
            str(dados.get("whatsapp") or ""),
            str(dados.get("catalogo_url") or ""),
            None,
        )
    except EstoqueIndisponivel as exc:
        return (
            "",
            "",
            str(exc) or "Não foi possível carregar as configurações do catálogo.",
        )
    except Exception:
        return "", "", None


@router.get(_TELA, response_class=HTMLResponse)
def loja_whatsapp_canais(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or not _autorizado(usuario):
        return _para_app()

    canais, erro = None, None
    try:
        canais = chatbot.listar_canais_whatsapp()
    except ChatbotIndisponivel as exc:
        erro = str(exc)

    view = montar_canais_view(canais, erro=erro)
    return templates.TemplateResponse(
        "loja/whatsapp_canais.html",
        contexto(
            request,
            usuario,
            db,
            view=view,
            # QR só existe neste render; o token sai da sessão e o payload sai do
            # store, para não sobreviver ao reload.
            qr=qr_efemero.consumir(request.session.pop("canal_qr_token", None)),
            acao_erro=request.session.pop("canal_erro", None),
            acao_mensagem=request.session.pop("canal_mensagem", None),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get(_TELA_DECIDIR, response_class=HTMLResponse)
def loja_whatsapp_decidir(
    request: Request,
    db: Session = Depends(get_db),
):
    """A escolha que não volta atrás: número novo ou o que a loja já anuncia.

    Migrar o número anunciado para a nuvem apaga o histórico do celular e o
    torna bot-only para sempre. A escolha aqui **é** o aceite — não existe um
    "li e concordo" separado.

    Gerente vê (precisa responder por que o WhatsApp não está no ar); só o dono
    tem o botão, porque quem clica precisa ser admin do portfólio na Meta.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or not _autorizado(usuario):
        return _para_app()

    app_id, config_id = portal_meta_app_id(), portal_meta_config_id()
    return templates.TemplateResponse(
        "loja/whatsapp_decidir.html",
        contexto(
            request,
            usuario,
            db,
            pode_conectar_cloud=_e_dono(usuario),
            meta_app_id=app_id,
            meta_config_id=config_id,
            # O botão acende sozinho no dia em que as duas variáveis existirem:
            # com uma só, o popup abriria e a Meta recusaria sem dizer por quê.
            popup_pronto=bool(app_id and config_id),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/app/loja/whatsapp/catalogo", response_class=HTMLResponse)
def loja_whatsapp_catalogo_salvar(
    request: Request,
    whatsapp: Annotated[str, Form()] = "",
    catalogo_url: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
    estoque: EstoqueClient = Depends(get_estoque_client),
):
    """Salva CTA WhatsApp da vitrine e o link do catálogo que o bot envia."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or not _autorizado(usuario) or not csrf_valido(request, csrf):
        return _para_app()

    valor_wa = (whatsapp or "").strip()
    valor_url = (catalogo_url or "").strip()
    try:
        estoque.atualizar_loja(
            whatsapp=valor_wa or None,
            catalogo_url=valor_url or None,
        )
        request.session["catalogo_mensagem"] = "Configurações do catálogo atualizadas."
    except EstoqueIndisponivel as exc:
        request.session["catalogo_erro"] = (
            str(exc) or "Não foi possível salvar as configurações do catálogo."
        )
    # O painel mora na Vitrine (Estoque): toda a configuração do catálogo
    # público num lugar só.
    return RedirectResponse("/app/loja/estoque/vitrine#catalogo-wa", status_code=303)


async def _guarda(request: Request, db: Session):
    """Devolve (usuario, form, resposta_de_erro) para as ações de escrita."""
    usuario = usuario_atual(request, db)
    if not usuario:
        return None, None, redirecionar_login()
    form = await request.form()
    if (
        not _habilitado()
        or not _autorizado(usuario)
        or not csrf_valido(request, form.get("csrf"))
    ):
        return None, None, _para_app()
    return usuario, form, None


def _auditar(
    db: Session,
    usuario,
    acao: str,
    *,
    success: bool,
    error_code=None,
    provedor: str = "evolution",
) -> None:
    """`acao` continua no vocabulário de ACOES_CANAL; quem separa Cloud de
    Evolution é o `provedor`, não uma ação nova."""
    registrar_auditoria_canal(
        db,
        loja_slug=usuario.loja_slug,
        acao=acao,
        ator_email=usuario.email,
        provedor=provedor,
        success=success,
        error_code=error_code,
        commit=True,
    )


@router.post(_TELA_DECIDIR)
async def loja_whatsapp_conectar_cloud(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Recebe o que o popup da Meta devolveu e repassa ao Chatbot (spec §4).

    O portal não vê segredo da Meta: o que chega aqui é um `code` de uso único
    e três ids públicos. Quem troca o `code` por token é o Chatbot, porque a
    troca exige o App Secret — e ele não ganha segunda cópia aqui.

    Decisão 9: `_guarda` deixa o gerente passar (ROLES_GESTAO), então o gate de
    dono é explícito. Quem clica precisa ser admin do portfólio na Meta.
    """
    usuario, form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    if not _e_dono(usuario):
        return _para_app()

    code = (form.get("code") or "").strip()
    waba_id = (form.get("waba_id") or "").strip()
    phone_number_id = (form.get("phone_number_id") or "").strip()
    business_id = (form.get("business_id") or "").strip()
    if not (code and waba_id and phone_number_id and business_id):
        # O popup fechou no meio. O `code` sozinho não conecta nada, e mandar
        # meia conexão ao Chatbot só queimaria o code de uso único.
        request.session["canal_erro"] = _ERRO_POPUP_INCOMPLETO
        return _para_tela()

    try:
        chatbot.conectar_whatsapp_cloud(
            code=code,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            business_id=business_id,
        )
        request.session["canal_mensagem"] = (
            "Número recebido. A Meta ainda está concluindo o registro — "
            "acompanhe aqui, não é preciso refazer a janela."
        )
        _auditar(db, usuario, "conectar", success=True, provedor="cloud")
    except OnboardingFalhou as exc:
        # A cadeia parou e sabemos onde. A mensagem do Chatbot nomeia o elo;
        # repeti-la é o que separa "a Meta recusou o número" de "estamos fora
        # do ar", que pedem ações opostas do lojista.
        request.session["canal_erro"] = (
            f"A conexão parou no caminho da Meta: {exc}"
        )
        _auditar(
            db,
            usuario,
            "conectar",
            success=False,
            error_code=f"onboarding_elo_{exc.elo}",
            provedor="cloud",
        )
    except ChatbotIndisponivel:
        request.session["canal_erro"] = _ERRO_CLOUD_INDISPONIVEL
        _auditar(
            db,
            usuario,
            "conectar",
            success=False,
            error_code=_ERRO_CHATBOT,
            provedor="cloud",
        )
    return _para_tela()


@router.post("/app/loja/whatsapp/canais")
async def loja_whatsapp_criar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    label = (form.get("label") or "").strip()
    if not label:
        request.session["canal_erro"] = "Informe um nome para o número."
        return _para_tela()
    try:
        chatbot.registrar_canal_whatsapp(label)
        _auditar(db, usuario, "criar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "criar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/conectar")
async def loja_whatsapp_conectar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        resultado = chatbot.conectar_canal_whatsapp(canal_id)
        # Pareamento consumido no próximo GET. Nunca em log, nunca em auditoria.
        # Só o token curto vai para o cookie: o QR em base64 estouraria os ~4 KB.
        if resultado.get("qr_payload"):
            request.session["canal_qr_token"] = qr_efemero.guardar(
                canal_id, resultado["qr_payload"]
            )
        _auditar(db, usuario, "conectar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "conectar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/desconectar")
async def loja_whatsapp_desconectar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.desconectar_canal_whatsapp(canal_id)
        _auditar(db, usuario, "desconectar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "desconectar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/inativar")
async def loja_whatsapp_inativar(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Remoção é lógica: o Chatbot marca ativo=False, o histórico fica."""
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.inativar_canal_whatsapp(canal_id)
        _auditar(db, usuario, "inativar", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(db, usuario, "inativar", success=False, error_code=_ERRO_CHATBOT)
    return _para_tela()


@router.post("/app/loja/whatsapp/canais/{canal_id}/principal-estoque")
async def loja_whatsapp_principal_estoque(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Define qual número opera o grupo de estoque e envia alertas de simulação."""
    usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.definir_principal_estoque_whatsapp(canal_id)
        request.session["canal_mensagem"] = (
            "Número principal do estoque atualizado. Só ele responde no grupo."
        )
        _auditar(db, usuario, "principal_estoque", success=True)
    except ChatbotIndisponivel as exc:
        request.session["canal_erro"] = str(exc)
        _auditar(
            db, usuario, "principal_estoque", success=False, error_code=_ERRO_CHATBOT
        )
    return _para_tela()


@router.get("/app/loja/whatsapp/canais/{canal_id}/status")
def loja_whatsapp_status(
    canal_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Rota fina para o polling enquanto há QR na tela (JSON, sem redirect)."""
    usuario = usuario_atual(request, db)
    if not usuario or not _habilitado() or not _autorizado(usuario):
        return JSONResponse({"erro": "nao_autorizado"}, status_code=403)
    try:
        dados = chatbot.obter_status_canal_whatsapp(canal_id)
    except ChatbotIndisponivel:
        return JSONResponse({"erro": "indisponivel"}, status_code=503)
    estado = str(dados.get("estado") or "pendente")
    return JSONResponse(
        {"estado": estado, "rotulo": ROTULOS.get(estado, estado)},
        headers={"Cache-Control": "no-store"},
    )


@router.get(_TELA_FILA, response_class=HTMLResponse)
def loja_whatsapp_fila(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    """Cadastro da fila de rodízio do Modo 2 (spec §5.8).

    A pessoa vem da **equipe da loja**, não de nome digitado: é assim que o
    ``Usuario.id`` entra no cadastro e o sino 1:1 ganha destinatário real.
    Sem vínculo o vendedor ainda recebe a oferta pelo WhatsApp, mas o sino
    não toca para ele — a lista avisa isso na cara.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _habilitado() or not _autorizado(usuario):
        return _para_app()

    fila, erro = [], None
    try:
        fila = chatbot.listar_fila_vendedores()
    except ChatbotIndisponivel as exc:
        # Chatbot fora do ar não derruba a tela: some a lista, o resto renderiza.
        erro = str(exc)

    return templates.TemplateResponse(
        "loja/whatsapp_fila.html",
        contexto(
            request,
            usuario,
            db,
            fila=fila,
            erro_fila=erro,
            equipe=_equipe_para_fila(db, usuario.loja_slug),
            acao_erro=request.session.pop("fila_erro", None),
            acao_mensagem=request.session.pop("fila_mensagem", None),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post(_TELA_FILA)
async def loja_whatsapp_fila_criar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    usuario, form, erro = await _guarda(request, db)
    if erro is not None:
        return erro

    escolhido = (form.get("usuario_id") or "").strip()
    telefone = (form.get("telefone") or "").strip()
    # O id vem do form: sem conferir a equipe, daria para injetar pessoa de
    # outra loja no rodízio desta.
    membro = next(
        (m for m in _equipe_para_fila(db, usuario.loja_slug) if m.id == escolhido), None
    )
    if membro is None:
        request.session["fila_erro"] = "Escolha uma pessoa da equipe da loja."
        return _para_fila()
    if not telefone:
        request.session["fila_erro"] = "Informe o WhatsApp do vendedor."
        return _para_fila()

    try:
        ordem = int((form.get("ordem") or "0").strip() or 0)
    except ValueError:
        ordem = 0

    try:
        chatbot.criar_fila_vendedor(
            nome=membro.nome, telefone=telefone, ordem=ordem, usuario_id=membro.id
        )
        request.session["fila_mensagem"] = f"{membro.nome} entrou na fila."
    except ChatbotIndisponivel as exc:
        request.session["fila_erro"] = str(exc)
    return _para_fila()


@router.post(_TELA_FILA + "/{vendedor_id}/remover")
async def loja_whatsapp_fila_remover(
    vendedor_id: str,
    request: Request,
    db: Session = Depends(get_db),
    chatbot=Depends(get_chatbot_client),
):
    _usuario, _form, erro = await _guarda(request, db)
    if erro is not None:
        return erro
    try:
        chatbot.remover_fila_vendedor(vendedor_id)
        request.session["fila_mensagem"] = "Vendedor saiu da fila."
    except ChatbotIndisponivel as exc:
        request.session["fila_erro"] = str(exc)
    return _para_fila()
