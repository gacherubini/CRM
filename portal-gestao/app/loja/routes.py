"""Rotas do Atendimento unificado (Revy Loja Fase 4 lean).

Flag: ``REVY_LOJA_ATENDIMENTO_ENABLED`` (default off).
Rotas legadas ``/app/leads`` e ``/app/conversas`` permanecem intactas.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import csrf_valido, usuario_atual
from app.clients.chatbot import (
    ChatbotClient,
    ChatbotIndisponivel,
    ConversaNaoEncontrada,
    CamposAgenteInvalidos,
    LeadNaoEncontrado,
    VersaoAgenteNaoEncontrada,
)
from app.config import settings
from app.db import get_db
from app.loja.attendance import (
    ATTENDANCE_STATE_LABELS,
    AttendanceState,
    buscar_venda_por_telefone,
    canal_permite_envio,
    carregar_atribuicoes_ativas,
    filtrar_itens,
    montar_workspace,
    normalizar_telefone,
    pode_usar_atendimento,
    pode_ver_todo_atendimento,
    rotulos_canais_para_filtro,
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

# Espelha `MAX_INSTRUCOES_LIVRES` do `chatbot-api`: o contador da tela precisa do
# número, e o produto vizinho é quem recusa acima dele. Se um dia divergirem,
# quem vence é o 422 de lá — o contador aqui só deixaria de avisar antes.
MAX_INSTRUCOES_AGENTE = 1000

# Import tardio de helpers do main (mesmo padrão de app.relatorios).
from app.main import (  # noqa: E402
    ETAPAS_LEAD,
    contexto,
    get_chatbot_client,
    redirecionar_login,
    registrar_evento_funil_best_effort,
    registrar_handoff_local,
    templates,
)

_PAPEIS_MUTACAO_ATENDIMENTO = frozenset(
    {"dono", "gerente", "vendedor", "admin_plataforma"}
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
    chatbot: ChatbotClient,
    telefone: str,
    *,
    canal_id: str | None = None,
) -> tuple[dict | None, list[dict], str | None]:
    """Retorna (resumo, mensagens, erro). Prefere conversa do ``canal_id``."""
    tel = normalizar_telefone(telefone)
    try:
        conversas = chatbot.listar_conversas(busca=tel, canal_id=canal_id)
        resumo = None
        for c in conversas:
            if normalizar_telefone(c.get("telefone")) != tel:
                continue
            if canal_id and c.get("canal_id") and c.get("canal_id") != canal_id:
                continue
            resumo = c
            # Com canal_id, primeira match já é a desejada; sem, preferir mais recente
            # (listar_conversas já vem ordenada por atualizada_em desc).
            break
        instance = None
        if resumo:
            instance = resumo.get("evolution_instance") or resumo.get("instance")
        try:
            mensagens = chatbot.listar_mensagens(
                tel,
                canal_id=canal_id or (resumo.get("canal_id") if resumo else None),
                instance=instance,
            )
        except ConversaNaoEncontrada:
            mensagens = []
        if resumo is None:
            try:
                estado = chatbot.obter_estado(tel, canal_id=canal_id)
                resumo = {
                    "telefone": tel,
                    "bot_ativo": estado.get("bot_ativo"),
                    "status": estado.get("status"),
                    "canal_id": canal_id,
                }
            except ChatbotIndisponivel:
                pass
        return resumo, mensagens, None
    except ChatbotIndisponivel as exc:
        return None, [], str(exc)


def _canais_para_filtro(chatbot: ChatbotClient) -> list[dict]:
    if not hasattr(chatbot, "listar_canais_whatsapp"):
        return []
    try:
        return chatbot.listar_canais_whatsapp()
    except ChatbotIndisponivel:
        return []
    except Exception:
        # Fake/client sem endpoint — filtro some, lista continua.
        return []


@router.get("/app/loja/atendimento", response_class=HTMLResponse)
def atendimento_lista(
    request: Request,
    busca: str | None = None,
    estado: str | None = None,
    canal_id: str | None = None,
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
        # Filtro no chatbot quando possível (menos payload); UI refiltra por segurança.
        conversas = chatbot.listar_conversas(limit=100, canal_id=canal_id or None)
    except ChatbotIndisponivel as exc:
        erro_integracao = erro_integracao or str(exc)

    canais_raw = _canais_para_filtro(chatbot)
    opcoes_canal = rotulos_canais_para_filtro(canais_raw)

    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    itens = unificar_lista(
        leads=leads,
        conversas=conversas,
        atribuicoes=atribuicoes,
        usuario=usuario,
    )
    esgotadas: list[dict] = []
    try:
        esgotadas = list(chatbot.listar_ofertas(estado="esgotada") or [])
    except ChatbotIndisponivel as exc:
        erro_integracao = erro_integracao or str(exc)
    except Exception:
        esgotadas = []

    sem_vendedor_total = 0
    if pode_ver_todo_atendimento(usuario):
        sem_vendedor_total = len(esgotadas)

    if estado == "aguardando_vendedor":
        itens = [
            SimpleNamespace(
                id=normalizar_telefone(o.get("telefone_cliente")),
                telefone=normalizar_telefone(o.get("telefone_cliente")),
                nome=None,
                estado=SimpleNamespace(value="aguardando_vendedor"),
                interesse=None,
                lead_id=None,
                bot_ativo=None,
                status_conversa=None,
                ultima_mensagem=None,
                atualizada_em=o.get("criado_em"),
                atribuido_a=None,
                canal_id=None,
                canal_label=None,
                canal_ativo=None,
                canal_estado=None,
            )
            for o in esgotadas
            if normalizar_telefone(o.get("telefone_cliente"))
        ]
    else:
        itens = filtrar_itens(itens, busca=busca, estado=estado, canal_id=canal_id)

    estados_ui = dict(ATTENDANCE_STATE_LABELS)
    if sem_vendedor_total or estado == "aguardando_vendedor":
        estados_ui["aguardando_vendedor"] = "Aguardando vendedor"

    return templates.TemplateResponse(
        "loja/atendimento_lista.html",
        contexto(
            request,
            usuario,
            itens=itens,
            estados=estados_ui,
            filtros={
                "busca": busca or "",
                "estado": estado or "",
                "canal_id": canal_id or "",
            },
            canais=opcoes_canal,
            integracao_erro=erro_integracao,
            atendimento_enabled=True,
            sem_vendedor_total=sem_vendedor_total,
        ),
    )


def montar_visao_agente(resumo: dict | None, hoje: date) -> dict | None:
    """View-model do desempenho do agente a partir do resumo do Chatbot.

    O Chatbot devolve ``por_dia`` só com os dias que tiveram conversa, o que faz
    o gráfico mentir sobre a tendência (dias vazios somem em vez de virar zero).
    Aqui a série é preenchida do dia 1 até ``hoje`` — a janela do resumo é o mês
    corrente (``/v1/atendimento/resumo`` usa ``_janela_mes``).
    """
    if not resumo:
        return None

    atendimentos = int(resumo.get("atendimentos") or 0)
    transferidos = int(resumo.get("transferidos") or 0)
    so_agente = max(atendimentos - transferidos, 0)
    por_dia = {
        str(item.get("data")): int(item.get("atendimentos") or 0)
        for item in (resumo.get("por_dia") or [])
    }

    serie: list[dict] = []
    for numero in range(1, hoje.day + 1):
        data = hoje.replace(day=numero).isoformat()
        serie.append(
            {"data": data, "dia": f"{numero:02d}", "atendimentos": por_dia.get(data, 0)}
        )

    maximo = max((d["atendimentos"] for d in serie), default=0)
    for dia in serie:
        dia["altura"] = round(dia["atendimentos"] / maximo * 100) if maximo else 0
        dia["pico"] = maximo > 0 and dia["atendimentos"] == maximo

    pico = next((d for d in serie if d["pico"]), None)
    return {
        "atendimentos": atendimentos,
        "transferidos": transferidos,
        "transferidos_pct": resumo.get("transferidos_pct"),
        "so_agente": so_agente,
        "so_agente_pct": (so_agente / atendimentos) if atendimentos else None,
        "serie": serie,
        "pico": pico,
        "maximo": maximo,
    }


def _oferta_nos_ultimos_dias(oferta: dict, dias: int, agora: datetime) -> bool:
    cru = oferta.get("criado_em") or oferta.get("travada_em")
    if not cru:
        return True
    try:
        quando = datetime.fromisoformat(str(cru).replace("Z", "+00:00"))
    except ValueError:
        return True
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return quando >= agora - timedelta(days=dias)


def montar_card_rodizio(chatbot: ChatbotClient, agora: datetime | None = None) -> dict | None:
    """Quatro números da fila nos últimos 7 dias (spec §5.4). Só Modo 2."""
    agora = agora or datetime.now(timezone.utc)
    try:
        abertas = list(chatbot.listar_ofertas(estado="aberta") or [])
        esgotadas = list(chatbot.listar_ofertas(estado="esgotada") or [])
        travadas = list(chatbot.listar_ofertas(estado="travada") or [])
        expiradas = list(chatbot.listar_ofertas(estado="expirada") or [])
    except (ChatbotIndisponivel, AttributeError):
        return None
    if not (abertas or esgotadas or travadas or expiradas):
        return None
    return {
        "oferecidos": len(abertas),
        "aguardando": len(esgotadas),
        "atendidos": sum(1 for o in travadas if _oferta_nos_ultimos_dias(o, 7, agora)),
        "perdidos": sum(1 for o in expiradas if _oferta_nos_ultimos_dias(o, 7, agora)),
    }


@router.get("/app/loja/agente", response_class=HTMLResponse)
def agente_desempenho(
    request: Request,
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
    resumo = None
    erro_resumo = None
    try:
        resumo = chatbot.resumo_atendimento()
    except ChatbotIndisponivel:
        erro_resumo = "indisponivel"
    return templates.TemplateResponse(
        "loja/agente.html",
        contexto(
            request,
            usuario,
            resumo=resumo,
            visao=montar_visao_agente(resumo, datetime.now(timezone.utc).date()),
            erro_resumo=erro_resumo,
            card_rodizio=montar_card_rodizio(chatbot),
            agente_config_habilitado=agente_config_habilitado(),
        ),
    )


@router.get("/app/loja/atendimento/{workspace_id}", response_class=HTMLResponse)
def atendimento_workspace(
    request: Request,
    workspace_id: str,
    canal_id: str | None = None,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Detalhe do workspace.

    ``workspace_id`` = telefone (dígitos). ``canal_id`` opcional multi-WA.
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

    conversa_resumo, mensagens, err_conv = _conversa_por_telefone(
        chatbot, telefone, canal_id=canal_id
    )
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
    pode_papel = usuario.papel in _PAPEIS_MUTACAO_ATENDIMENTO
    pode_enviar = pode_papel and not workspace.envio_bloqueado_canal
    pode_atualizar_etapa = pode_papel and bool(lead and lead.get("id"))

    return templates.TemplateResponse(
        "loja/atendimento_workspace.html",
        contexto(
            request,
            usuario,
            workspace=workspace.to_template_dict(),
            estados=ATTENDANCE_STATE_LABELS,
            etapas=ETAPAS_LEAD,
            AttendanceState=AttendanceState,
            atendimento_enabled=True,
            pode_enviar=pode_enviar,
            pode_handoff=pode_papel,
            pode_atualizar_etapa=pode_atualizar_etapa,
            canal_id_filtro=canal_id or workspace.canal_id,
            origem_lead=_origem_do_lead(db, usuario.loja_slug, lead),
        ),
    )


def _origem_do_lead(db: Session, loja_slug: str, lead: dict | None) -> dict | None:
    """De qual campanha veio o contato — mesma regra que atribui a venda.

    Devolve None quando não há match: sem campanha casada é melhor não dizer
    nada do que sugerir uma origem que a atribuição da venda não vai confirmar.
    """
    if not lead:
        return None
    try:
        from app.campanhas import resolver_campanhas_do_lead

        primeira, ultima = resolver_campanhas_do_lead(db, loja_slug, lead)
    except Exception:
        return None
    campanha = ultima or primeira
    if campanha is None:
        return None
    return {
        "nome": campanha.nome,
        "canal": campanha.canal,
        "utm_campaign": campanha.utm_campaign,
        "primeiro_clique": (
            primeira.nome if primeira is not None and primeira is not campanha else None
        ),
    }


def _destino_workspace(telefone: str, canal_id: str | None = None) -> str:
    destino = f"/app/loja/atendimento/{telefone}"
    if canal_id:
        destino = f"{destino}?canal_id={canal_id}"
    return destino


def _append_query(destino: str, **params: str) -> str:
    partes = [f"{k}={v}" for k, v in params.items() if v]
    if not partes:
        return destino
    sep = "&" if "?" in destino else "?"
    return f"{destino}{sep}{'&'.join(partes)}"


def _quer_json(request: Request) -> bool:
    """True se o cliente pediu JSON (Accept ou header X-Requested-With)."""
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return True
    if (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest":
        return True
    return False


def _json_erro(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": code, "message": message},
        status_code=status,
    )


def _guard_workspace_mutacao(
    request: Request,
    usuario: Usuario | None,
    telefone: str,
    db: Session,
):
    """Login / flag / papel / escopo. Retorna Response de erro ou None se OK."""
    if not usuario:
        return redirecionar_login(), None
    if not atendimento_habilitado():
        return _flag_off_response(request, usuario), None
    if not pode_usar_atendimento(usuario) or usuario.papel not in _PAPEIS_MUTACAO_ATENDIMENTO:
        return (
            templates.TemplateResponse(
                "erro.html",
                contexto(request, usuario, erro="Sem permissão para o Atendimento."),
                status_code=403,
            ),
            None,
        )
    if not telefone:
        return (
            templates.TemplateResponse(
                "erro.html",
                contexto(request, usuario, erro="Atendimento não encontrado."),
                status_code=404,
            ),
            None,
        )
    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    atr = atribuicao_para_telefone(atribuicoes, telefone)
    if not visivel_para_usuario(usuario, atribuicao=atr):
        return (
            templates.TemplateResponse(
                "erro.html",
                contexto(request, usuario, erro="Atendimento fora do seu escopo."),
                status_code=403,
            ),
            None,
        )
    return None, atr


@router.get("/app/loja/atendimento/{workspace_id}/mensagens.json")
def atendimento_mensagens_json(
    request: Request,
    workspace_id: str,
    canal_id: str | None = None,
    after_id: str | None = None,
    after_criada_em: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Poll de mensagens (JSON). Proxy autenticado ao Chatbot; sem tokens ao browser.

    Query: ``canal_id`` (multi-WA), ``after_id`` (preferido) ou ``after_criada_em``.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        return _json_erro(401, "auth", "Não autenticado")
    if not atendimento_habilitado():
        return _json_erro(404, "flag", "Atendimento não habilitado")
    if not pode_usar_atendimento(usuario):
        return _json_erro(403, "perm", "Sem permissão")

    telefone = normalizar_telefone(workspace_id)
    if not telefone:
        return _json_erro(404, "not_found", "Atendimento não encontrado")

    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    atr = atribuicao_para_telefone(atribuicoes, telefone)
    if not visivel_para_usuario(usuario, atribuicao=atr):
        return _json_erro(403, "scope", "Atendimento fora do seu escopo")

    limit = max(1, min(int(limit or 100), 200))
    canal = (canal_id or "").strip() or None
    cursor_id = (after_id or "").strip() or None
    cursor_ts = (after_criada_em or "").strip() or None

    # Resolve instance da conversa aberta (multi-WA) no servidor.
    instance = None
    try:
        conversas = chatbot.listar_conversas(busca=telefone, canal_id=canal)
        for c in conversas:
            if normalizar_telefone(c.get("telefone")) != telefone:
                continue
            if canal and c.get("canal_id") and c.get("canal_id") != canal:
                continue
            instance = c.get("evolution_instance") or c.get("instance")
            if not canal:
                canal = c.get("canal_id") or canal
            break
    except ChatbotIndisponivel as exc:
        return _json_erro(503, "integracao", str(exc) or "Chatbot indisponível")

    try:
        if hasattr(chatbot, "listar_mensagens_envelope"):
            envelope = chatbot.listar_mensagens_envelope(
                telefone,
                limit=limit,
                canal_id=canal,
                instance=instance,
                after_id=cursor_id,
                after_criada_em=cursor_ts,
            )
            mensagens = envelope.get("mensagens") or []
            last_id = envelope.get("last_id")
            canal_out = envelope.get("canal_id") or canal
        else:
            mensagens = chatbot.listar_mensagens(
                telefone,
                limit=limit,
                canal_id=canal,
                instance=instance,
                after_id=cursor_id,
                after_criada_em=cursor_ts,
            )
            last_id = (
                mensagens[-1].get("id")
                if mensagens and isinstance(mensagens[-1], dict)
                else cursor_id
            )
            canal_out = canal
    except ConversaNaoEncontrada:
        if cursor_id:
            return _json_erro(404, "cursor", "Cursor não encontrado nesta conversa")
        return JSONResponse(
            {
                "ok": True,
                "telefone": telefone,
                "canal_id": canal,
                "mensagens": [],
                "after_id": cursor_id,
                "last_id": cursor_id,
            }
        )
    except ChatbotIndisponivel as exc:
        return _json_erro(503, "integracao", str(exc) or "Chatbot indisponível")

    return JSONResponse(
        {
            "ok": True,
            "telefone": telefone,
            "canal_id": canal_out,
            "mensagens": mensagens,
            "after_id": cursor_id,
            "last_id": last_id or cursor_id,
        }
    )


@router.post("/app/loja/atendimento/{workspace_id}/mensagem")
async def atendimento_enviar_mensagem(
    request: Request,
    workspace_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
    messaging: HumanMessagingPort = Depends(get_human_messaging_port),
):
    quer_json = _quer_json(request)
    usuario = usuario_atual(request, db)
    if not usuario:
        if quer_json:
            return _json_erro(401, "auth", "Não autenticado")
        return redirecionar_login()
    if not atendimento_habilitado():
        if quer_json:
            return _json_erro(404, "flag", "Atendimento não habilitado")
        return _flag_off_response(request, usuario)
    if not pode_usar_atendimento(usuario):
        if quer_json:
            return _json_erro(403, "perm", "Sem permissão")
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Sem permissão para o Atendimento."),
            status_code=403,
        )

    telefone = normalizar_telefone(workspace_id)
    form = await request.form()
    # canal_id do form (hidden) — só o da conversa aberta, nunca seletor livre.
    canal_id_form = (form.get("canal_id") or "").strip() or None
    # Ignora instance/canal arbitrário do cliente: nunca confiar em seletor UI.
    # Canal vem só do resumo da conversa no servidor.
    destino = f"/app/loja/atendimento/{telefone}"
    if canal_id_form:
        destino = f"{destino}?canal_id={canal_id_form}"

    def _redir_erro(code: str):
        if quer_json:
            return _json_erro(400, code, code)
        sep = "&" if "?" in destino else "?"
        return RedirectResponse(f"{destino}{sep}erro={code}", status_code=303)

    if not csrf_valido(request, form.get("csrf")):
        if quer_json:
            return _json_erro(403, "sessao", "Sessão expirada")
        return RedirectResponse(
            f"{destino}&erro=sessao" if "?" in destino else f"{destino}?erro=sessao",
            status_code=303,
        )

    atribuicoes = carregar_atribuicoes_ativas(db, usuario.loja_slug)
    atr = atribuicao_para_telefone(atribuicoes, telefone)
    if not visivel_para_usuario(usuario, atribuicao=atr):
        if quer_json:
            return _json_erro(403, "scope", "Atendimento fora do seu escopo")
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Atendimento fora do seu escopo."),
            status_code=403,
        )

    texto = (form.get("texto") or "").strip()
    if not texto:
        return _redir_erro("texto")
    if len(texto) > 4000:
        return _redir_erro("texto")

    # Resolve canal da conversa no servidor — sem aceitar instance do form.
    conversa_resumo, _, _ = _conversa_por_telefone(
        chatbot, telefone, canal_id=canal_id_form
    )
    if conversa_resumo and not canal_permite_envio(
        canal_ativo=conversa_resumo.get("canal_ativo"),
        canal_estado=conversa_resumo.get("canal_estado"),
    ):
        if quer_json:
            return _json_erro(423, "canal", "Canal inativo ou desconectado")
        return _redir_erro("canal")

    instance_conversa = None
    if conversa_resumo:
        instance_conversa = (
            conversa_resumo.get("evolution_instance")
            or conversa_resumo.get("instance")
        )

    # Idempotência: cliente pode reenviar a mesma chave; senão gera uma nova.
    idem = (form.get("idempotency_key") or "").strip()
    if not idem or len(idem) > 120:
        idem = f"portal:{usuario.loja_slug}:{telefone}:{uuid4().hex}"

    try:
        resultado = messaging.enviar_texto(
            telefone,
            texto,
            idempotency_key=idem,
            # Apenas instance da conversa aberta (não picker da UI).
            instance=instance_conversa,
            ator=usuario.email,
        )
    except MensagemHumanaNaoEncontrada:
        if quer_json:
            return _json_erro(404, "conversa", "Conversa não encontrada")
        return _redir_erro("conversa")
    except MensagemHumanaNaoAutorizada:
        if quer_json:
            return _json_erro(403, "perm", "Envio não autorizado")
        return templates.TemplateResponse(
            "erro.html",
            contexto(request, usuario, erro="Envio não autorizado."),
            status_code=403,
        )
    except (MensagemHumanaErro, ChatbotIndisponivel):
        if quer_json:
            return _json_erro(503, "envio", "Não foi possível enviar a mensagem agora")
        return _redir_erro("envio")

    # Espelha no fake de mensagens do chatbot client se expuser o histórico
    # (testes com ChatbotFake + InMemory port).
    criada_em = datetime.now(timezone.utc).isoformat()
    msg_id = resultado.mensagem_id
    if hasattr(chatbot, "mensagens") and isinstance(getattr(chatbot, "mensagens"), dict):
        hist = chatbot.mensagens.setdefault(telefone, [])
        if not resultado.duplicada:
            hist.append(
                {
                    "id": msg_id,
                    "direcao": "saida",
                    "texto": texto,
                    "criada_em": criada_em,
                    "humana": True,
                }
            )
        if hasattr(chatbot, "estados"):
            chatbot.estados[telefone] = {"bot_ativo": False, "status": "handoff"}

    if quer_json:
        return JSONResponse(
            {
                "ok": True,
                "duplicada": bool(resultado.duplicada),
                "bot_ativo": bool(resultado.bot_ativo),
                "mensagem": {
                    "id": msg_id,
                    "direcao": "saida",
                    "texto": texto,
                    "criada_em": criada_em,
                },
                "canal_id": resultado.canal_id
                or (conversa_resumo or {}).get("canal_id")
                or canal_id_form,
            }
        )

    sufixo = "duplicada" if resultado.duplicada else "enviada"
    sep = "&" if "?" in destino else "?"
    return RedirectResponse(f"{destino}{sep}ok={sufixo}", status_code=303)


@router.post("/app/loja/atendimento/{workspace_id}/handoff")
async def atendimento_handoff(
    request: Request,
    workspace_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Assumir / devolver handoff no workspace.

    Reutiliza ``registrar_handoff_local`` + ``chatbot.definir_bot_ativo``.
    Instance vem do resumo da conversa (não do form). Se o Chatbot falhar no
    toggle do bot, ainda tenta a atribuição local e reporta via flash.
    """
    usuario = usuario_atual(request, db)
    telefone = normalizar_telefone(workspace_id)
    erro_resp, _atr = _guard_workspace_mutacao(request, usuario, telefone, db)
    if erro_resp is not None:
        return erro_resp
    assert usuario is not None

    form = await request.form()
    canal_id_form = (form.get("canal_id") or "").strip() or None
    destino = _destino_workspace(telefone, canal_id_form)

    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(
            _append_query(destino, erro="sessao"), status_code=303
        )

    acao = (form.get("acao") or "").strip()
    if acao not in {"assumir", "devolver"}:
        return RedirectResponse(
            _append_query(destino, erro="acao"), status_code=303
        )

    # Instance da conversa aberta — multi-WA sem seletor arbitrário.
    conversa_resumo, _, _ = _conversa_por_telefone(
        chatbot, telefone, canal_id=canal_id_form
    )
    instance_conversa = None
    if conversa_resumo:
        instance_conversa = (
            conversa_resumo.get("evolution_instance")
            or conversa_resumo.get("instance")
        )

    bot_erro = False
    try:
        chatbot.definir_bot_ativo(
            telefone,
            bot_ativo=acao == "devolver",
            instance=instance_conversa,
        )
    except ChatbotIndisponivel:
        # Degradação: ainda tenta atribuição local; UI mostra aviso.
        bot_erro = True

    registro_indisponivel = False
    try:
        registrar_handoff_local(db, usuario, telefone, assumir=acao == "assumir")
    except (SQLAlchemyError, ValueError):
        db.rollback()
        registro_indisponivel = True

    params: dict[str, str] = {}
    if bot_erro and registro_indisponivel:
        params["erro"] = "handoff"
    elif bot_erro:
        # Atribuição local ok; bot não pausou/reativou no Chatbot.
        params["ok"] = acao
        params["aviso"] = "bot-indisponivel"
    elif registro_indisponivel:
        params["ok"] = acao
        params["registro"] = "indisponivel"
    else:
        params["ok"] = acao
    return RedirectResponse(_append_query(destino, **params), status_code=303)


@router.post("/app/loja/atendimento/{workspace_id}/etapa")
async def atendimento_atualizar_etapa(
    request: Request,
    workspace_id: str,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Altera etapa do lead no workspace (reusa chatbot.atualizar_etapa_lead)."""
    usuario = usuario_atual(request, db)
    telefone = normalizar_telefone(workspace_id)
    erro_resp, _atr = _guard_workspace_mutacao(request, usuario, telefone, db)
    if erro_resp is not None:
        return erro_resp
    assert usuario is not None

    form = await request.form()
    canal_id_form = (form.get("canal_id") or "").strip() or None
    destino = _destino_workspace(telefone, canal_id_form)

    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(
            _append_query(destino, erro="sessao"), status_code=303
        )

    etapa = (form.get("etapa") or "").strip()
    if etapa not in ETAPAS_LEAD:
        return RedirectResponse(
            _append_query(destino, erro="etapa"), status_code=303
        )

    lead = _lead_por_telefone(chatbot, telefone)
    lead_id = (lead or {}).get("id") if lead else None
    form_lead_id = (form.get("lead_id") or "").strip() or None
    if form_lead_id and lead and form_lead_id == lead.get("id"):
        lead_id = form_lead_id
    elif form_lead_id and not lead:
        # Tenta por id se listagem falhou mas o form carrega o lead do workspace.
        try:
            lead = chatbot.obter_lead(form_lead_id)
            if normalizar_telefone(lead.get("telefone")) == telefone:
                lead_id = lead.get("id")
            else:
                lead_id = None
        except (LeadNaoEncontrado, ChatbotIndisponivel):
            lead_id = None

    if not lead_id:
        return RedirectResponse(
            _append_query(destino, erro="lead"), status_code=303
        )

    try:
        lead_atualizado = chatbot.atualizar_etapa_lead(lead_id, etapa)
    except LeadNaoEncontrado:
        return RedirectResponse(
            _append_query(destino, erro="lead"), status_code=303
        )
    except ChatbotIndisponivel:
        return RedirectResponse(
            _append_query(destino, erro="integracao"), status_code=303
        )

    evento_origem = str(lead_atualizado.get("atualizada_em") or uuid4())
    registrar_evento_funil_best_effort(
        db,
        loja_slug=usuario.loja_slug,
        lead_ref=lead_id,
        tipo="etapa_manual",
        idempotency_key=f"portal:lead:{lead_id}:etapa:{evento_origem}",
        ator_email=usuario.email,
        payload={"etapa_nova": etapa, "origem": "atendimento_workspace"},
    )
    if etapa == "perdido":
        registrar_evento_funil_best_effort(
            db,
            loja_slug=usuario.loja_slug,
            lead_ref=lead_id,
            tipo="perda",
            idempotency_key=f"portal:lead:{lead_id}:perda:{evento_origem}",
            ator_email=usuario.email,
            payload={"status": "perdido", "origem": "atendimento_workspace"},
        )

    return RedirectResponse(
        _append_query(destino, ok="etapa-atualizada"), status_code=303
    )


# --- Configuração do agente (spec 2026-08-24-agente-por-loja) -----------------
# A Loja é só tela. Campos, geração do prompt, núcleo Revy, versões e histórico
# moram no `chatbot-api`; aqui não há tabela nem montagem de texto.


def agente_config_habilitado() -> bool:
    return bool(settings.revy_loja_agente_config_enabled)


def _guard_agente_config(request: Request, db: Session, *, json_: bool):
    """Sessão + flag + papel dono/gerente. São três, não quatro.

    A tela vizinha (`/app/loja/agente`) não tem gate de módulo, e a configuração
    segue o gate da tela onde ela mora (spec §6). Devolve `(usuario, None)` ou
    `(None, resposta)`.
    """
    usuario = usuario_atual(request, db)
    if not usuario:
        if json_:
            return None, _json_erro(401, "auth", "Não autenticado")
        return None, redirecionar_login()
    if not agente_config_habilitado():
        if json_:
            return None, _json_erro(404, "flag", "Configuração do agente não habilitada")
        return None, templates.TemplateResponse(
            "erro.html",
            contexto(
                request,
                usuario,
                erro="A configuração do agente ainda não está habilitada nesta loja.",
            ),
            status_code=404,
        )
    if not pode_ver_todo_atendimento(usuario):
        if json_:
            return None, _json_erro(403, "perm", "Sem permissão")
        return None, templates.TemplateResponse(
            "erro.html",
            contexto(
                request,
                usuario,
                erro="Só o dono ou o gerente configuram o agente.",
            ),
            status_code=403,
        )
    return usuario, None


@router.get("/app/loja/agente/configuracao", response_class=HTMLResponse)
def agente_configuracao(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario, recusa = _guard_agente_config(request, db, json_=False)
    if recusa is not None:
        return recusa
    rascunho = None
    versoes: list[dict] = []
    erro_integracao = False
    try:
        rascunho = chatbot.obter_rascunho_agente()
        versoes = list(chatbot.listar_versoes_agente() or [])
    except ChatbotIndisponivel:
        erro_integracao = True
    return templates.TemplateResponse(
        "loja/agente_configuracao.html",
        contexto(
            request,
            usuario,
            rascunho=rascunho,
            versoes=versoes,
            erro_integracao=erro_integracao,
            max_instrucoes=MAX_INSTRUCOES_AGENTE,
        ),
    )


@router.put("/app/loja/agente/configuracao.json")
async def agente_configuracao_salvar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Autosave do rascunho. Devolve o prompt remontado e os conflitos.

    O aviso de conflito é aviso: 422 aqui é campo inválido (Literal fora da
    lista, horário sem zero à esquerda), nunca "você escreveu algo proibido".
    """
    usuario, recusa = _guard_agente_config(request, db, json_=True)
    if recusa is not None:
        return recusa
    corpo = await request.json()
    if not csrf_valido(request, (corpo or {}).get("csrf")):
        return _json_erro(403, "sessao", "Sessão expirada")
    campos = (corpo or {}).get("campos")
    if not isinstance(campos, dict):
        return _json_erro(400, "campos", "Campos ausentes")
    try:
        salvo = chatbot.salvar_rascunho_agente(campos, autor=usuario.email)
    except CamposAgenteInvalidos as e:
        # 422 tem que chegar como 422: virando 502 a tela culpa a conexão por um
        # campo errado, e o lojista não descobre qual.
        return JSONResponse(
            {
                "ok": False,
                "error": "campos",
                "message": "Confira os campos: algum valor não é aceito.",
                "campos": e.campos,
            },
            status_code=422,
        )
    except ChatbotIndisponivel:
        return _json_erro(502, "integracao", "Não foi possível salvar agora")
    return JSONResponse({"ok": True, **salvo})


@router.post("/app/loja/agente/configuracao/publicar")
async def agente_configuracao_publicar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    usuario, recusa = _guard_agente_config(request, db, json_=False)
    if recusa is not None:
        return recusa
    form = await request.form()
    destino = "/app/loja/agente/configuracao"
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(_append_query(destino, erro="sessao"), status_code=303)
    try:
        chatbot.publicar_agente(autor=usuario.email)
    except ChatbotIndisponivel:
        return RedirectResponse(
            _append_query(destino, erro="integracao"), status_code=303
        )
    return RedirectResponse(_append_query(destino, ok="publicado"), status_code=303)


@router.post("/app/loja/agente/configuracao/restaurar")
async def agente_configuracao_restaurar(
    request: Request,
    db: Session = Depends(get_db),
    chatbot: ChatbotClient = Depends(get_chatbot_client),
):
    """Traz uma versão antiga para dentro do rascunho — e apaga o que estava lá.

    Nada publicado é alterado e nenhuma versão some, mas o rascunho em andamento
    é sobrescrito em silêncio do lado do chatbot. Quem avisa é a tela, antes.
    """
    usuario, recusa = _guard_agente_config(request, db, json_=False)
    if recusa is not None:
        return recusa
    form = await request.form()
    destino = "/app/loja/agente/configuracao"
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(_append_query(destino, erro="sessao"), status_code=303)
    versao_id = (form.get("versao_id") or "").strip()
    if not versao_id:
        return RedirectResponse(_append_query(destino, erro="versao"), status_code=303)
    try:
        chatbot.restaurar_versao_agente(versao_id, autor=usuario.email)
    except VersaoAgenteNaoEncontrada:
        return RedirectResponse(_append_query(destino, erro="versao"), status_code=303)
    except ChatbotIndisponivel:
        return RedirectResponse(
            _append_query(destino, erro="integracao"), status_code=303
        )
    return RedirectResponse(_append_query(destino, ok="restaurado"), status_code=303)
