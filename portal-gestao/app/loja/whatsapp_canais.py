"""Read-model dos canais WhatsApp para a tela de Ajustes da Loja.

Traduz o estado técnico do Chatbot para linguagem de dono de loja. Nunca
carrega QR: o QR vive só no ciclo de request/response da ação de conectar.
"""
from __future__ import annotations

from dataclasses import dataclass

ROTULOS = {
    "conectado": "Conectado",
    "pendente": "Aguardando leitura do QR",
    "desconectado": "Caiu — reconectar",
    "inativo": "Desativado",
    # Modo 2 (Cloud API). O vocabulário técnico mora em
    # ``whatsapp_provider.ESTADOS_VALIDOS``, no chatbot; aqui ele vira frase de
    # dono de loja. Restrito e banido vêm da Meta e NÃO se consertam clicando —
    # o rótulo precisa dizer isso, senão o lojista fica tentando.
    "cloud_pendente": "Conectado — aguardando liberação da Revy",
    "cloud_ativo": "No ar",
    "cloud_restrito": "Limitado pela Meta — falar com a Revy",
    "cloud_banido": "Bloqueado pela Meta — falar com a Revy",
}


@dataclass(frozen=True)
class CanalView:
    id: str
    label: str
    instancia: str
    estado: str
    rotulo: str
    ativo: bool
    cloud: bool
    principal_estoque: bool
    pode_conectar: bool
    pode_desconectar: bool
    pode_marcar_principal_estoque: bool


@dataclass(frozen=True)
class CanaisView:
    canais: tuple[CanalView, ...]
    erro: str | None
    pode_adicionar: bool


def montar_canais_view(
    canais: list[dict] | None,
    *,
    erro: str | None = None,
    multi_habilitado: bool = True,
) -> CanaisView:
    """Monta a view. ``canais=None`` significa falha de leitura, não lista vazia."""
    if canais is None:
        return CanaisView(canais=(), erro=erro, pode_adicionar=False)

    itens: list[CanalView] = []
    for bruto in canais:
        estado = str(bruto.get("estado") or "pendente")
        ativo = bool(bruto.get("ativo", True))
        # "Apagar" é inativação lógica: o Chatbot é dono de whatsapp_canais e não
        # deleta (histórico de conversas fica preservado). Os inativos ficam de
        # fora da lista para que apagar signifique "sumiu" para o dono.
        if not ativo or estado == "inativo":
            continue
        principal = bool(bruto.get("principal_estoque"))
        # Canal Cloud se reconhece pelo waba_id, que é o que o Modo 2 grava e o
        # Modo 1 deixa nulo — mesma regra do ``cloud_canal.py`` no chatbot.
        cloud = bool(bruto.get("waba_id"))
        itens.append(
            CanalView(
                id=str(bruto.get("id") or ""),
                label=str(bruto.get("e164_or_label") or "—"),
                instancia=str(bruto.get("evolution_instance") or ""),
                estado=estado,
                rotulo=ROTULOS.get(estado, estado),
                ativo=ativo,
                cloud=cloud,
                principal_estoque=principal,
                # Conectar/desconectar são ações da Evolution (QR). Num canal
                # Cloud o botão chamaria ``conectar_canal_whatsapp``, que pede
                # QR para um número que é da Cloud API.
                pode_conectar=not cloud and estado != "conectado",
                pode_desconectar=not cloud and estado == "conectado",
                pode_marcar_principal_estoque=not principal,
            )
        )
    # Se a API ainda não marcou ninguém, o primeiro da lista é o implícito
    # (mesmo fallback do Chatbot: ativo mais antigo).
    if itens and not any(c.principal_estoque for c in itens):
        primeiro = itens[0]
        itens[0] = CanalView(
            id=primeiro.id,
            label=primeiro.label,
            instancia=primeiro.instancia,
            estado=primeiro.estado,
            rotulo=primeiro.rotulo,
            ativo=primeiro.ativo,
            cloud=primeiro.cloud,
            principal_estoque=True,
            pode_conectar=primeiro.pode_conectar,
            pode_desconectar=primeiro.pode_desconectar,
            pode_marcar_principal_estoque=False,
        )
        for i in range(1, len(itens)):
            c = itens[i]
            itens[i] = CanalView(
                id=c.id,
                label=c.label,
                instancia=c.instancia,
                estado=c.estado,
                rotulo=c.rotulo,
                ativo=c.ativo,
                cloud=c.cloud,
                principal_estoque=False,
                pode_conectar=c.pode_conectar,
                pode_desconectar=c.pode_desconectar,
                pode_marcar_principal_estoque=True,
            )
    return CanaisView(
        canais=tuple(itens),
        erro=erro,
        pode_adicionar=bool(multi_habilitado),
    )
