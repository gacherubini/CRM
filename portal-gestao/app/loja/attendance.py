"""Atendimento unificado (Revy Loja Fase 4 + multi-canal F6 lean).

Composição read-model: lead + conversa + atribuição local + interesse +
venda. Não duplica propriedade — Chatbot/Estoque/Motor/Portal permanecem
donos de seus dados.

Identificador do workspace
--------------------------
O ``id`` do workspace é o **telefone** (somente dígitos). Com multi-WA,
a disambiguação de canal usa ``canal_id`` (query param / campo no item).
Leads permanecem por ``(loja, telefone)``; conversas por ``(canal_id,
telefone)`` no Chatbot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.financeiro_calc import identidade_telefone
from app.models import AtendimentoAtribuicao, Usuario, Venda


# ---------------------------------------------------------------------------
# Estados de atendimento (mapa a partir das etapas de lead quando possível)
# ---------------------------------------------------------------------------


class AttendanceState(str, Enum):
    """Estados canônicos do workspace de atendimento."""

    NOVO = "novo"
    EM_ATENDIMENTO = "em_atendimento"
    AGUARDANDO_CLIENTE = "aguardando_cliente"
    AGUARDANDO_SIMULACAO = "aguardando_simulacao"
    NEGOCIACAO = "negociacao"
    VENDIDO = "vendido"
    PERDIDO = "perdido"


ATTENDANCE_STATE_LABELS: dict[str, str] = {
    AttendanceState.NOVO.value: "Novo",
    AttendanceState.EM_ATENDIMENTO.value: "Em atendimento",
    AttendanceState.AGUARDANDO_CLIENTE.value: "Aguardando cliente",
    AttendanceState.AGUARDANDO_SIMULACAO.value: "Aguardando simulação",
    AttendanceState.NEGOCIACAO.value: "Negociação",
    AttendanceState.VENDIDO.value: "Vendido",
    AttendanceState.PERDIDO.value: "Perdido",
}

# Mapeamento etapa de lead (Chatbot) → estado de atendimento.
_LEAD_ETAPA_PARA_ESTADO: dict[str, AttendanceState] = {
    "novo": AttendanceState.NOVO,
    "em_atendimento": AttendanceState.EM_ATENDIMENTO,
    "qualificado": AttendanceState.AGUARDANDO_SIMULACAO,
    "convertido": AttendanceState.VENDIDO,
    "perdido": AttendanceState.PERDIDO,
}

# Canal inativo / desconectado: histórico visível, envio bloqueado.
_CANAL_ESTADOS_BLOQUEIAM_ENVIO = frozenset({"inativo", "desconectado"})


def mapear_estado_de_lead(etapa: str | None) -> AttendanceState:
    if not etapa:
        return AttendanceState.NOVO
    return _LEAD_ETAPA_PARA_ESTADO.get(etapa, AttendanceState.EM_ATENDIMENTO)


def normalizar_telefone(telefone: str | None) -> str:
    return "".join(c for c in (telefone or "") if c.isdigit())


def rotulo_canal_de_conversa(conv: Mapping[str, Any] | None) -> str | None:
    """Preferência: canal_label → numero_mascarado → instance → canal_id."""
    if not conv:
        return None
    for chave in ("canal_label", "numero_mascarado", "evolution_instance", "instance"):
        valor = conv.get(chave)
        if valor:
            return str(valor)
    canal_id = conv.get("canal_id")
    return str(canal_id) if canal_id else None


def canal_permite_envio(
    *,
    canal_ativo: bool | None = None,
    canal_estado: str | None = None,
) -> bool:
    """False somente quando status de canal está disponível e inoperante.

    Se a API não envia status (legado), permite envio (comportamento F4).
    """
    if canal_ativo is False:
        return False
    if canal_estado and canal_estado in _CANAL_ESTADOS_BLOQUEIAM_ENVIO:
        return False
    return True


# ---------------------------------------------------------------------------
# Política de visibilidade (DEFAULT documentada)
# ---------------------------------------------------------------------------

# Vendedor vê fila sem responsável (ainda não atribuída).
# Constante configurável; trocar para False restringe só aos atribuídos a ele.
VENDEDOR_VE_FILA_SEM_RESPONSAVEL: bool = True

PAPEIS_VEEM_TODA_LOJA = frozenset({"dono", "gerente", "admin_plataforma"})
PAPEIS_ATENDIMENTO = frozenset({"dono", "gerente", "vendedor", "admin_plataforma"})


def pode_usar_atendimento(usuario: Usuario) -> bool:
    return usuario.papel in PAPEIS_ATENDIMENTO


def pode_ver_todo_atendimento(usuario: Usuario) -> bool:
    """dono/gerente (e admin plataforma): toda a loja."""
    return usuario.papel in PAPEIS_VEEM_TODA_LOJA


@dataclass(frozen=True)
class AssignmentInfo:
    vendedor_email: str | None
    origem: str | None = None
    ativa: bool = False


@dataclass
class AttendanceListItem:
    """Linha da lista unificada (lead ∪ conversa)."""

    id: str  # telefone (dígitos)
    telefone: str
    nome: str | None
    estado: AttendanceState
    interesse: str | None
    lead_id: str | None
    bot_ativo: bool | None
    status_conversa: str | None
    ultima_mensagem: str | None
    atualizada_em: str | None
    atribuido_a: str | None
    canal_id: str | None = None
    canal_label: str | None = None
    canal_ativo: bool | None = None
    canal_estado: str | None = None
    evolution_instance: str | None = None
    origem: str | None = None


@dataclass
class AttendanceWorkspace:
    """Workspace de negociação: composição sem copiar ownership."""

    id: str  # telefone (dígitos)
    telefone: str
    estado: AttendanceState
    lead: dict[str, Any] | None = None
    conversa_resumo: dict[str, Any] | None = None
    mensagens: list[dict[str, Any]] = field(default_factory=list)
    assignment: AssignmentInfo | None = None
    veiculo_interesse: str | None = None
    veiculo_ref: str | None = None
    ultima_simulacao_ref: str | None = None
    venda_status: str | None = None
    venda_id: str | None = None
    canal_id: str | None = None
    canal_label: str | None = None
    canal_ativo: bool | None = None
    canal_estado: str | None = None
    evolution_instance: str | None = None
    envio_bloqueado_canal: bool = False
    erros_bloco: dict[str, str] = field(default_factory=dict)

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "telefone": self.telefone,
            "estado": self.estado.value,
            "estado_label": ATTENDANCE_STATE_LABELS.get(
                self.estado.value, self.estado.value
            ),
            "lead": self.lead,
            "conversa_resumo": self.conversa_resumo,
            "mensagens": self.mensagens,
            "assignment": (
                {
                    "vendedor_email": self.assignment.vendedor_email,
                    "origem": self.assignment.origem,
                    "ativa": self.assignment.ativa,
                }
                if self.assignment
                else None
            ),
            "veiculo_interesse": self.veiculo_interesse,
            "veiculo_ref": self.veiculo_ref,
            "ultima_simulacao_ref": self.ultima_simulacao_ref,
            "venda_status": self.venda_status,
            "venda_id": self.venda_id,
            "canal_id": self.canal_id,
            "canal_label": self.canal_label,
            "canal_ativo": self.canal_ativo,
            "canal_estado": self.canal_estado,
            "evolution_instance": self.evolution_instance,
            "envio_bloqueado_canal": self.envio_bloqueado_canal,
            "erros_bloco": self.erros_bloco,
        }


def carregar_atribuicoes_ativas(
    db: Session, loja_slug: str
) -> dict[str, AtendimentoAtribuicao]:
    """Mapa telefone_hmac → atribuição ativa da loja."""
    rows = (
        db.query(AtendimentoAtribuicao)
        .filter(
            AtendimentoAtribuicao.loja_slug == loja_slug,
            AtendimentoAtribuicao.ativa.is_(True),
        )
        .all()
    )
    return {row.telefone_hmac: row for row in rows}


def atribuicao_para_telefone(
    atribuicoes: Mapping[str, AtendimentoAtribuicao], telefone: str | None
) -> AtendimentoAtribuicao | None:
    hmac_tel = identidade_telefone(telefone)
    if not hmac_tel:
        return None
    return atribuicoes.get(hmac_tel)


def visivel_para_usuario(
    usuario: Usuario,
    *,
    atribuicao: AtendimentoAtribuicao | None,
) -> bool:
    """Política DEFAULT de visibilidade.

    - dono/gerente/admin_plataforma: tudo da loja
    - vendedor: atribuído a ele **ou** fila sem responsável
      (se ``VENDEDOR_VE_FILA_SEM_RESPONSAVEL``)
    """
    if pode_ver_todo_atendimento(usuario):
        return True
    if usuario.papel != "vendedor":
        return False
    if atribuicao is None:
        return VENDEDOR_VE_FILA_SEM_RESPONSAVEL
    return (atribuicao.vendedor_email or "").lower() == (usuario.email or "").lower()


def resolver_estado(
    *,
    lead_etapa: str | None,
    bot_ativo: bool | None,
    venda_status: str | None,
) -> AttendanceState:
    if venda_status == "confirmada":
        return AttendanceState.VENDIDO
    if lead_etapa == "perdido":
        return AttendanceState.PERDIDO
    if lead_etapa == "convertido":
        return AttendanceState.VENDIDO
    if lead_etapa == "qualificado":
        # Pediu simular com dados completos: fila humana (Motor pode estar off).
        return AttendanceState.AGUARDANDO_SIMULACAO
    if bot_ativo is False:
        return AttendanceState.EM_ATENDIMENTO
    if lead_etapa == "em_atendimento":
        return AttendanceState.EM_ATENDIMENTO
    if lead_etapa == "novo" or lead_etapa is None:
        return AttendanceState.NOVO
    return mapear_estado_de_lead(lead_etapa)


def _preview_mensagem(ultima: dict | None) -> str | None:
    if not ultima:
        return None
    texto = ultima.get("texto")
    return str(texto) if texto else None


def _campos_canal(conv: Mapping[str, Any] | None) -> dict[str, Any]:
    if not conv:
        return {
            "canal_id": None,
            "canal_label": None,
            "canal_ativo": None,
            "canal_estado": None,
            "evolution_instance": None,
        }
    ativo = conv.get("canal_ativo")
    if ativo is not None:
        ativo = bool(ativo)
    return {
        "canal_id": str(conv["canal_id"]) if conv.get("canal_id") else None,
        "canal_label": rotulo_canal_de_conversa(conv),
        "canal_ativo": ativo,
        "canal_estado": (
            str(conv["canal_estado"]) if conv.get("canal_estado") else None
        ),
        "evolution_instance": (
            str(conv.get("evolution_instance") or conv.get("instance") or "") or None
        ),
    }


def unificar_lista(
    *,
    leads: list[dict],
    conversas: list[dict],
    atribuicoes: Mapping[str, AtendimentoAtribuicao],
    vendas_por_telefone: Mapping[str, Venda] | None = None,
    usuario: Usuario,
) -> list[AttendanceListItem]:
    """Merge leads + conversas; multi-WA: uma linha por (telefone, canal_id)."""
    vendas_por_telefone = vendas_por_telefone or {}
    leads_por_tel: dict[str, dict] = {}
    for lead in leads:
        tel = normalizar_telefone(lead.get("telefone"))
        if tel:
            leads_por_tel[tel] = lead

    itens: list[AttendanceListItem] = []
    telefones_com_conversa: set[str] = set()

    for conv in conversas:
        tel = normalizar_telefone(conv.get("telefone"))
        if not tel:
            continue
        telefones_com_conversa.add(tel)
        lead = leads_por_tel.get(tel) or {}
        atr = atribuicao_para_telefone(atribuicoes, tel)
        if not visivel_para_usuario(usuario, atribuicao=atr):
            continue
        venda = vendas_por_telefone.get(tel)
        bot_ativo = conv.get("bot_ativo")
        estado = resolver_estado(
            lead_etapa=lead.get("etapa") if lead else None,
            bot_ativo=bot_ativo,
            venda_status=venda.status if venda else None,
        )
        canal = _campos_canal(conv)
        ultima = conv.get("ultima_mensagem")
        itens.append(
            AttendanceListItem(
                id=tel,
                telefone=tel,
                nome=(lead.get("nome") if lead else None) or None,
                estado=estado,
                interesse=(lead.get("interesse") if lead else None) or None,
                lead_id=(lead.get("id") if lead else None) or None,
                bot_ativo=bot_ativo,
                status_conversa=conv.get("status"),
                ultima_mensagem=_preview_mensagem(ultima),
                atualizada_em=(
                    conv.get("atualizada_em")
                    or (lead.get("atualizada_em") if lead else None)
                    or (lead.get("criada_em") if lead else None)
                ),
                atribuido_a=atr.vendedor_email if atr else None,
                origem=(lead.get("origem") if lead else None) or None,
                **canal,
            )
        )

    # Leads sem conversa correspondente.
    for tel, lead in leads_por_tel.items():
        if tel in telefones_com_conversa:
            continue
        atr = atribuicao_para_telefone(atribuicoes, tel)
        if not visivel_para_usuario(usuario, atribuicao=atr):
            continue
        venda = vendas_por_telefone.get(tel)
        estado = resolver_estado(
            lead_etapa=lead.get("etapa"),
            bot_ativo=None,
            venda_status=venda.status if venda else None,
        )
        itens.append(
            AttendanceListItem(
                id=tel,
                telefone=tel,
                nome=lead.get("nome"),
                estado=estado,
                interesse=lead.get("interesse"),
                lead_id=lead.get("id"),
                bot_ativo=None,
                status_conversa=None,
                ultima_mensagem=None,
                atualizada_em=lead.get("atualizada_em") or lead.get("criada_em"),
                atribuido_a=atr.vendedor_email if atr else None,
                origem=lead.get("origem"),
            )
        )

    itens.sort(
        key=lambda i: i.atualizada_em or "",
        reverse=True,
    )
    return itens


def montar_workspace(
    *,
    telefone: str,
    lead: dict | None,
    conversa_resumo: dict | None,
    mensagens: list[dict],
    atribuicao: AtendimentoAtribuicao | None,
    venda: Venda | None,
    erros_bloco: dict[str, str] | None = None,
) -> AttendanceWorkspace:
    tel = normalizar_telefone(telefone)
    bot_ativo = None
    if conversa_resumo is not None:
        bot_ativo = conversa_resumo.get("bot_ativo")
    estado = resolver_estado(
        lead_etapa=(lead or {}).get("etapa"),
        bot_ativo=bot_ativo,
        venda_status=venda.status if venda else None,
    )
    canal = _campos_canal(conversa_resumo)
    bloqueado = not canal_permite_envio(
        canal_ativo=canal["canal_ativo"],
        canal_estado=canal["canal_estado"],
    )
    return AttendanceWorkspace(
        id=tel,
        telefone=tel,
        estado=estado,
        lead=lead,
        conversa_resumo=conversa_resumo,
        mensagens=list(mensagens or []),
        assignment=(
            AssignmentInfo(
                vendedor_email=atribuicao.vendedor_email,
                origem=atribuicao.origem,
                ativa=bool(atribuicao.ativa),
            )
            if atribuicao
            else AssignmentInfo(vendedor_email=None, ativa=False)
        ),
        veiculo_interesse=(lead or {}).get("interesse"),
        veiculo_ref=(lead or {}).get("veiculo_ref"),
        ultima_simulacao_ref=None,  # lean: ref opcional futura (Motor)
        venda_status=venda.status if venda else None,
        venda_id=venda.id if venda else None,
        canal_id=canal["canal_id"],
        canal_label=canal["canal_label"],
        canal_ativo=canal["canal_ativo"],
        canal_estado=canal["canal_estado"],
        evolution_instance=canal["evolution_instance"],
        envio_bloqueado_canal=bloqueado,
        erros_bloco=dict(erros_bloco or {}),
    )


def buscar_venda_por_telefone(
    db: Session, loja_slug: str, telefone: str, lead_id: str | None = None
) -> Venda | None:
    """Melhor esforço: por lead_ref; sem telefone em claro na tabela de vendas."""
    if lead_id:
        venda = (
            db.query(Venda)
            .filter(Venda.loja_slug == loja_slug, Venda.lead_ref == lead_id)
            .order_by(Venda.criada_em.desc())
            .first()
        )
        if venda:
            return venda
    return None


def filtrar_itens(
    itens: list[AttendanceListItem],
    *,
    busca: str | None = None,
    estado: str | None = None,
    canal_id: str | None = None,
) -> list[AttendanceListItem]:
    resultado = itens
    if canal_id:
        resultado = [i for i in resultado if i.canal_id == canal_id]
    if estado:
        resultado = [i for i in resultado if i.estado.value == estado]
    if busca:
        termo = busca.strip().lower()
        if termo:
            filtrados = []
            for i in resultado:
                campos = [
                    i.nome or "",
                    i.telefone or "",
                    i.interesse or "",
                    i.atribuido_a or "",
                    i.canal_label or "",
                ]
                if any(termo in c.lower() for c in campos):
                    filtrados.append(i)
            resultado = filtrados
    return resultado


def rotulos_canais_para_filtro(
    canais: list[dict],
) -> list[dict[str, str]]:
    """Opções do dropdown de canal (somente canais conhecidos da loja)."""
    opcoes: list[dict[str, str]] = []
    for c in canais or []:
        cid = c.get("id")
        if not cid:
            continue
        label_bruto = (c.get("e164_or_label") or c.get("evolution_instance") or cid)
        digitos = "".join(ch for ch in str(label_bruto) if ch.isdigit())
        if len(digitos) >= 8 and len(digitos) >= len(str(label_bruto).strip()) - 2:
            label = f"***{digitos[-4:]}"
        else:
            label = str(label_bruto)
        estado = c.get("estado") or ("ativo" if c.get("ativo", True) else "inativo")
        if not c.get("ativo", True) or estado == "inativo":
            label = f"{label} (inativo)"
        opcoes.append({"id": str(cid), "label": label})
    return opcoes
