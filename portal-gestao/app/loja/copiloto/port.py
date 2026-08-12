"""Contrato do provedor de LLM. O resto do Copiloto não conhece DeepSeek.

Decisão do dono: DeepSeek para tudo. O Port existe para que o runner e os
testes não dependam de rede — não para trocar de provedor por esporte.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Sequence

EsforcoLLM = Literal["low", "high", "max"]


class LLMIndisponivel(RuntimeError):
    """Provedor fora, timeout ou erro de transporte. Nunca vira número."""


class RespostaLLMInvalida(RuntimeError):
    """O modelo devolveu tool-call malformada. Rejeitar, não adivinhar."""


@dataclass(frozen=True)
class MensagemLLM:
    papel: str  # system | user | assistant | tool
    conteudo: str
    tool_call_id: str | None = None
    nome: str | None = None
    # Só preenchido em mensagens role=assistant que pediram ferramenta: carrega
    # o tool_calls estruturado que o wire da API (compatível OpenAI) exige que
    # a mensagem assistant anterior declare, para o tool_call_id da mensagem
    # role=tool seguinte fazer referência a algo real.
    tool_calls: tuple["ToolCall", ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ToolCall:
    id: str
    nome: str
    argumentos: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RespostaLLM:
    texto: str | None
    tool_calls: tuple[ToolCall, ...]
    tokens_entrada: int
    tokens_saida: int
    finish_reason: str


def parse_argumentos(bruto: str | None) -> dict[str, Any]:
    """Argumentos de tool-call: objeto JSON ou nada. Sem adivinhação."""
    texto = (bruto or "").strip()
    if not texto:
        return {}
    try:
        valor = json.loads(texto)
    except (TypeError, ValueError) as exc:
        raise RespostaLLMInvalida("argumentos não são JSON válido") from exc
    if not isinstance(valor, dict):
        raise RespostaLLMInvalida("argumentos precisam ser um objeto JSON")
    return valor


class LLMPort(Protocol):
    def completar(
        self,
        mensagens: Sequence[MensagemLLM],
        ferramentas: Sequence[dict[str, Any]],
        *,
        esforco: EsforcoLLM = "low",
        max_tokens: int = 800,
    ) -> RespostaLLM: ...


class LLMFake:
    """Provedor determinístico: fila de respostas programadas."""

    def __init__(self, respostas: Sequence[RespostaLLM] | None = None):
        self._fila = list(respostas or [])
        self.chamadas: list[dict[str, Any]] = []

    def programar(self, resposta: RespostaLLM) -> None:
        self._fila.append(resposta)

    def completar(
        self,
        mensagens: Sequence[MensagemLLM],
        ferramentas: Sequence[dict[str, Any]],
        *,
        esforco: EsforcoLLM = "low",
        max_tokens: int = 800,
    ) -> RespostaLLM:
        self.chamadas.append(
            {
                "mensagens": list(mensagens),
                "ferramentas": [f.get("name") for f in ferramentas],
                "esforco": esforco,
                "max_tokens": max_tokens,
            }
        )
        assert self._fila, "LLMFake sem resposta programada para esta chamada"
        return self._fila.pop(0)
