"""Rotas do Atendimento unificado (Revy Loja Fase 4 lean).

Flag: ``REVY_LOJA_ATENDIMENTO_ENABLED`` (default off).
Rotas legadas ``/app/leads`` e ``/app/conversas`` permanecem intactas.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import csrf_valido, usuario_atual
from app.clients.chatbot import (
    ChatbotClient,
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    LeadNaoEncontrado,
)
from app.config import settings
from app.db import get_db
from app.loja.attendance import (
    ATTENDANCE_STATE_LABELS,
    AttendanceState,
    buscar_venda_por_telefone,
    carregar_atribuicoes_ativas,
    filtrar_itens,
    montar_workspace,
    normalizar_telefone,
    pode_usar_atendimento,
    unificar_lista,
    visivel_para_usuario,
    atribuicao_para_telefone,
)
from app.loja.human_messaging import (
    HumanMessagingPort,
    MensagemHumanaErro,
    MensagemHumanaNaoEncontrada,
    MensagemHumanaNaoAutorizada,
)
from app.models import Usuario

router = APIRouter()

# Import tardio de helpers do main (mesmo padrão de app.relatorios).
from app.main import (  # noqa: E402
    contexto,
    get_chatbot_client,
    redirecionar_login,
    templates,
)


def _human_messaging_port() -> HumanMessagingPort:
    """Factory default; testes sobrescrevem via dependency_overrides."""
    from app.loja.human_messaging import HttpHumanMessagingPort

    return HttpHumanMessagingPort()


def get_human_messaging_port() -> HumanMessagingPort:
    return _human_messaging_port()


def atendimento_habilitado() -> bool:
    return bool(settings.revy_loja_atendimento_enabled)


def _flag_off_response(request: Request, usuario: Usuario | None):
    return templates.TemplateResponse(
        "erro.html",
        contexto(
            request,
            usuario,
            erro="Atendimento unificado ainda não está habilitado nesta loja.",
        ),
        status_code=404,
    )


def _lead_por_telefone(chatbot: ChatbotClient, telefone: str) -> dict | None:
    tel = normalizar_telefone(telefone)
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel:
        return None
    for lead in leads:
        if normalizar_telefone(lead.get("telefone")) == tel:
            return lead
    return None


def _conversa_por_telefone(
    chatbot: ChatbotClient, telefone: str
) -> tuple[dict | None, list[dict], str | None]:
    """Retorna (resumo, mensagens, erro)."""
    tel = normalizar_telefone(telefone)
    try:
        conversas = chatbot.listar_conversas(busca=tel)
        resumo = None
        for c in conversas:
            if normalizar_telefone(c.get("telefone")) == tel:
                resumo = c
                break
        try:
            mensagens = chatbot.listar_mensagens(tel)
        except ConversaNaoEncontrada:
            mensagens = []
        if resumo is None:
            try:
                estado = chatbot.obter_estado(tel)
                resumo = {
                    "telefone": tel,
                    "bot_ativo": estado.get("bot_ativo"),
                    "status": estado.get("status"),
                }
            except ChatbotIndisponivel:
                pass
        return resumo, mensagens, None
    except ChatbotIndisponivel as exc:
        return None, [], str(exc)


@router.get("/app/loja/atendimento", response_class=HTMLResponse)
def atendimento_lista(
    request: Request,
    busca: str | None = None,
    estado: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not atendimento_habilitado():
        return _flag_off_response(request, usuario)
    if not pode_usar_atendimento(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Sem permissão para o Atendimento."),
            status_code=403,
        )

    erro_integracao = None
    leads: list[dict] = []
    conversas: list[dict] = []
    try:
        leads = chatbot.listar_leads()
    except ChatbotIndisponivel as exc:
        erro_integracao = str(exc)
    try:
        conversas = chatbot.listar_conversas(limit=100)
    except ChatbotIndisponivel as exc:
        erro_integracao = erro_integracao or str(exc)

    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    itens = unificar_lista(
        leads=leads,
        conversas=conversas,
        atribuicoes=atribuicoes,
        usuario=usuario,
    )
    itens = filtrar_itens(itens, busca=busca, estado=estado)

    return templates.TemplateResponse(
        "loja/atendimento_lista.html",
        contexto(
            request,
            usuario,
            itens=itens,
            estados=ATTENDANCE_STATE_LABELS,
            filtros={"busca": busca or "", "estado": estado or ""},
            integracao_erro=erro_integracao,
            atendimento_enabled=True,
        ),
    )


@router.get("/app/loja/atendimento/{workspace_id}", response_class=HTMLResponse)
def atendimento_workspace(
    request: Request,
    workspace_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Detalhe do workspace.

    ``workspace_id`` = telefone (dígitos). Ver docstring de ``attendance.py``.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not atendimento_habilitado():
        return _flag_off_response(request, usuario)
    if not pode_usar_atendimento(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Sem permissão para o Atendimento."),
            status_code=403,
        )

    telefone = normalizar_telefone(workspace_id)
    if not telefone:
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Atendimento não encontrado."),
            status_code=404,
        )

    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    atr = atribuicao_para_telefone(atribuicoes, telefone)
    if not visivel_para_usuario(usuario, atribuicao=atr):
        # 403 seguro: não vaza existência de contatos fora do escopo.
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Atendimento fora do seu escopo."),
            status_code=403,
        )

    erros: dict[str, str] = {}
    lead = None
    try:
        # Prefer lead_id se workspace_id for um id de lead conhecido.
        if workspace_id.startswith("l") or len(workspace_id) < 8:
            try:
                lead = chatbot.obter_lead(workspace_id)
                telefone = normalizar_telefone(lead.get("telefone")) or telefone
            except (LeadNaoEncontrado, ChatbotIndisponivel):
                lead = _lead_por_telefone(chatbot, telefone)
        else:
            lead = _lead_por_telefone(chatbot, telefone)
    except ChatbotIndisponivel as exc:
        erros["lead"] = str(exc)

    conversa_resumo, mensagens, err_conv = _conversa_por_telefone(chatbot, telefone)
    if err_conv:
        erros["conversa"] = err_conv

    lead_id = (lead or {}).get("id") if lead else None
    venda = buscar_venda_por_telefone(
        db, usuario.loja_slug, telefone, lead_id=lead_id
    )

    # Revalida atribuição se telefone veio do lead
    atr = atribuicao_para_telefone(atribuicoes, telefone)
    if not visivel_para_usuario(usuario, atribuicao=atr):
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Atendimento fora do seu escopo."),
            status_code=403,
        )

    workspace = montar_workspace(
        telefone=telefone,
        lead=lead,
        conversa_resumo=conversa_resumo,
        mensagens=mensagens,
        atribuicao=atr,
        venda=venda,
        erros_bloco=erros,
    )

    return templates.TemplateResponse(
        "loja/atendimento_workspace.html",
        contexto(
            request,
            usuario,
            workspace=workspace.to_template_dict(),
            estados=ATTENDANCE_STATE_LABELS,
            AttendanceState=AttendanceState,
            atendimento_enabled=True,
            pode_enviar=usuario.papel
            in {"dono", "gerente", "vendedor", "admin_plataforma"},
        ),
    )


@router.post("/app/loja/atendimento/{workspace_id}/mensagem")
async def atendimento_enviar_mensagem(
    request: Request,
    workspace_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    messaging: HumanMessagingPort = Depends(get_human_messaging_port),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not atendimento_habilitado():
        return _flag_off_response(request, usuario)
    if not pode_usar_atendimento(usuario):
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Sem permissão para o Atendimento."),
            status_code=403,
        )

    telefone = normalizar_telefone(workspace_id)
    destino = f"/app/loja/atendimento/{telefone}"
    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(f"{destino}?erro=sessao", status_code=303)

    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    atr = atribuicao_para_telefone(atribuicoes, telefone)
    if not visivel_para_usuario(usuario, atribuicao=atr):
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Atendimento fora do seu escopo."),
            status_code=403,
        )

    texto = (form.get("texto") or "").strip()
    if not texto:
        return RedirectResponse(f"{destino}?erro=texto", status_code=303)
    if len(texto) > 4000:
        return RedirectResponse(f"{destino}?erro=texto", status_code=303)

    # Idempotência: cliente pode reenviar a mesma chave; senão gera uma nova.
    idem = (form.get("idempotency_key") or "").strip()
    if not idem or len(idem) > 120:
        idem = f"portal:{usuario.loja_slug}:{telefone}:{uuid4().hex}"

    try:
        resultado = messaging.enviar_texto(
            telefone,
            texto,
            idempotency_key=idem,
            ator=usuario.email,
        )
    except MensagemHumanaNaoEncontrada:
        return RedirectResponse(f"{destino}?erro=conversa", status_code=303)
    except MensagemHumanaNaoAutorizada:
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Envio não autorizado."),
            status_code=403,
        )
    except (MensagemHumanaErro, ChatbotIndisponivel):
        return RedirectResponse(f"{destino}?erro=envio", status_code=303)

    # Espelha no fake de mensagens do chatbot client se expuser o histórico
    # (testes com ChatbotFake + InMemory port).
    if hasattr(chatbot, "mensagens") and isinstance(getattr(chatbot, "mensagens"), dict):
        hist = chatbot.mensagens.setdefault(telefone, [])
        if not resultado.duplicada:
            hist.append(
                {
                    "direcao": "saida",
                    "texto": texto,
                    "criada_em": None,
                    "humana": True,
                }
            )
        if hasattr(chatbot, "estados"):
            chatbot.estados[telefone] = {"bot_ativo": False, "status": "handoff"}

    sufixo = "duplicada" if resultado.duplicada else "enviada"
    return RedirectResponse(f"{destino}?ok={sufixo}", status_code=303)
