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
}


@dataclass(frozen=True)
class CanalView:
    id: str
    label: str
    instancia: str
    estado: str
    rotulo: str
    ativo: bool
    pode_conectar: bool
    pode_desconectar: bool


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
        operavel = ativo and estado != "inativo"
        itens.append(
            CanalView(
                id=str(bruto.get("id") or ""),
                label=str(bruto.get("e164_or_label") or "—"),
                instancia=str(bruto.get("evolution_instance") or ""),
                estado=estado,
                rotulo=ROTULOS.get(estado, estado),
                ativo=ativo,
                pode_conectar=operavel and estado != "conectado",
                pode_desconectar=operavel and estado == "conectado",
            )
        )
    return CanaisView(
        canais=tuple(itens),
        erro=erro,
        pode_adicionar=bool(multi_habilitado),
    )
