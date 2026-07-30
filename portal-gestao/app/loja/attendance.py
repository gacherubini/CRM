"""Atendimento unificado (Revy Loja Fase 4 lean).

Composição read-model: lead + conversa + atribuição local + interesse +
venda. Não duplica propriedade — Chatbot/Estoque/Motor/Portal permanecem
donos de seus dados.

Identificador do workspace
--------------------------
O ``id`` do workspace é o **telefone** (somente dígitos). Motivo: leads e
conversas já se correlacionam por telefone na loja; a lista unificada e o
composer humano usam o mesmo eixo. ``lead_id`` aparece como campo opcional
quando houver lead correspondente.
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
    NEGOCIACAO = "negociacao"
    VENDIDO = "vendido"
    PERDIDO = "perdido"


ATTENDANCE_STATE_LABELS: dict[str, str] = {
    AttendanceState.NOVO.value: "Novo",
    AttendanceState.EM_ATENDIMENTO.value: "Em atendimento",
    AttendanceState.AGUARDANDO_CLIENTE.value: "Aguardando cliente",
    AttendanceState.NEGOCIACAO.value: "Negociação",
    AttendanceState.VENDIDO.value: "Vendido",
    AttendanceState.PERDIDO.value: "Perdido",
}

# Mapeamento etapa de lead (Chatbot) → estado de atendimento.
_LEAD_ETAPA_PARA_ESTADO: dict[str, AttendanceState] = {
    "novo": AttendanceState.NOVO,
    "em_atendimento": AttendanceState.EM_ATENDIMENTO,
    "qualificado": AttendanceState.NEGOCIACAO,
    "convertido": AttendanceState.VENDIDO,
    "perdido": AttendanceState.PERDIDO,
}


def mapear_estado_de_lead(etapa: str | None) -> AttendanceState:
    if not etapa:
        return AttendanceState.NOVO
    return _LEAD_ETAPA_PARA_ESTADO.get(etapa, AttendanceState.EM_ATENDIMENTO)


def normalizar_telefone(telefone: str | None) -> str:
    return "".join(c for c in (telefone or "") if c.isdigit())


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
    canal_label: str | None = None
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
    canal_label: str | None = None
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
            "canal_label": self.canal_label,
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
        return AttendanceState.NEGOCIACAO
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


def unificar_lista(
    *,
    leads: list[dict],
    conversas: list[dict],
    atribuicoes: Mapping[str, AtendimentoAtribuicao],
    vendas_por_telefone: Mapping[str, Venda] | None = None,
    usuario: Usuario,
) -> list[AttendanceListItem]:
    """Merge leads + conversas por telefone; aplica visibilidade."""
    vendas_por_telefone = vendas_por_telefone or {}
    por_tel: dict[str, dict[str, Any]] = {}

    for lead in leads:
        tel = normalizar_telefone(lead.get("telefone"))
        if not tel:
            continue
        por_tel.setdefault(tel, {})["lead"] = lead
        por_tel[tel]["telefone"] = tel

    for conv in conversas:
        tel = normalizar_telefone(conv.get("telefone"))
        if not tel:
            continue
        por_tel.setdefault(tel, {})["conversa"] = conv
        por_tel[tel]["telefone"] = tel

    itens: list[AttendanceListItem] = []
    for tel, bloco in por_tel.items():
        lead = bloco.get("lead") or {}
        conv = bloco.get("conversa") or {}
        atr = atribuicao_para_telefone(atribuicoes, tel)
        if not visivel_para_usuario(usuario, atribuicao=atr):
            continue
        venda = vendas_por_telefone.get(tel)
        bot_ativo = conv.get("bot_ativo") if conv else None
        estado = resolver_estado(
            lead_etapa=lead.get("etapa") if lead else None,
            bot_ativo=bot_ativo,
            venda_status=venda.status if venda else None,
        )
        ultima = conv.get("ultima_mensagem") if conv else None
        canal_label = None
        if conv:
            canal_label = conv.get("canal_label") or conv.get("canal_id")
        itens.append(
            AttendanceListItem(
                id=tel,
                telefone=tel,
                nome=(lead.get("nome") if lead else None) or None,
                estado=estado,
                interesse=(lead.get("interesse") if lead else None) or None,
                lead_id=(lead.get("id") if lead else None) or None,
                bot_ativo=bot_ativo,
                status_conversa=conv.get("status") if conv else None,
                ultima_mensagem=_preview_mensagem(ultima),
                atualizada_em=(
                    conv.get("atualizada_em")
                    or (lead.get("atualizada_em") if lead else None)
                    or (lead.get("criada_em") if lead else None)
                ),
                atribuido_a=atr.vendedor_email if atr else None,
                canal_label=str(canal_label) if canal_label else None,
                origem=(lead.get("origem") if lead else None) or None,
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
    canal_label = None
    if conversa_resumo:
        canal_label = (
            conversa_resumo.get("canal_label")
            or conversa_resumo.get("canal_id")
            or conversa_resumo.get("evolution_instance")
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
        canal_label=str(canal_label) if canal_label else None,
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
    itens: list[AttendanceListItem], *, busca: str | None = None, estado: str | None = None
) -> list[AttendanceListItem]:
    resultado = itens
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
                ]
                if any(termo in c.lower() for c in campos):
                    filtrados.append(i)
            resultado = filtrados
    return resultado
