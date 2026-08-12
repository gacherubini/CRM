"""Client do provedor de LLM (DeepSeek, API compatível com OpenAI).

Único lugar do repo que conhece o formato do provedor.

Duas coisas que este client NÃO faz, de propósito:
- não usa ``app/clients/_retry.py``: aquele helper só repete GET/HEAD/OPTIONS
  ou POST com ``Idempotency-Key`` (``_retry.py:44-46``), e este POST não é
  idempotente pelo padrão da casa;
- não loga payload nem chave. Só metadados.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Sequence

import httpx

from app.loja.copiloto.port import (
    EsforcoLLM,
    LLMIndisponivel,
    MensagemLLM,
    RespostaLLM,
    RespostaLLMInvalida,
    ToolCall,
    parse_argumentos,
)

logger = logging.getLogger("portal.copiloto.llm")

# Recomendação da DeepSeek para cenário agêntico. Contraintuitivo: o default
# da casa em tool calling seria temperature=0.
TEMPERATURE_AGENTICA = 1.0
TOP_P_AGENTICO = 0.95

STATUS_QUE_REPETEM = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def montar_payload(
    mensagens: Sequence[MensagemLLM],
    ferramentas: Sequence[dict[str, Any]],
    *,
    modelo: str,
    esforco: EsforcoLLM,
    max_tokens: int,
) -> dict[str, Any]:
    """Corpo do request. Função pura — testável sem rede."""
    corpo: dict[str, Any] = {
        "model": modelo,
        "temperature": TEMPERATURE_AGENTICA,
        "top_p": TOP_P_AGENTICO,
        "max_tokens": max_tokens,
        "reasoning_effort": esforco,
        "messages": [],
    }
    for m in mensagens:
        item: dict[str, Any] = {"role": m.papel, "content": m.conteudo}
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        if m.nome:
            item["name"] = m.nome
        corpo["messages"].append(item)
    if ferramentas:
        corpo["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": f["name"],
                    "description": f.get("description", ""),
                    "parameters": f.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for f in ferramentas
        ]
    return corpo


class DeepSeekClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        modelo: str,
        *,
        timeout: float = 40.0,
        retries: int = 1,
        backoff: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.modelo = modelo
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff = max(0.0, backoff)
        self._transport = transport
        self._sleeper = sleeper

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.api_key and self.modelo)

    def completar(
        self,
        mensagens: Sequence[MensagemLLM],
        ferramentas: Sequence[dict[str, Any]],
        *,
        esforco: EsforcoLLM = "low",
        max_tokens: int = 800,
    ) -> RespostaLLM:
        if not self.configurado:
            raise LLMIndisponivel("provedor de LLM não configurado")

        payload = montar_payload(
            mensagens, ferramentas, modelo=self.modelo, esforco=esforco,
            max_tokens=max_tokens,
        )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        inicio = time.monotonic()

        ultimo_status: int | None = None
        for tentativa in range(self.retries + 1):
            try:
                with httpx.Client(
                    base_url=self.base_url,
                    headers=headers,
                    timeout=self.timeout,
                    transport=self._transport,
                ) as client:
                    resposta = client.post("/chat/completions", json=payload)
                ultimo_status = resposta.status_code
                if resposta.status_code == 200:
                    saida = self._interpretar(resposta.json())
                    logger.info(
                        "copiloto_llm modelo=%s esforco=%s in=%s out=%s ms=%s",
                        self.modelo,
                        esforco,
                        saida.tokens_entrada,
                        saida.tokens_saida,
                        int((time.monotonic() - inicio) * 1000),
                    )
                    return saida
                if resposta.status_code not in STATUS_QUE_REPETEM:
                    break  # 4xx de validação: repetir só queima token
            except httpx.HTTPError:
                ultimo_status = None
            if tentativa < self.retries:
                self._sleeper(self.backoff * (2**tentativa))

        logger.warning("copiloto_llm falha modelo=%s status=%s", self.modelo, ultimo_status)
        raise LLMIndisponivel(f"provedor de LLM indisponível (status={ultimo_status})")

    def _interpretar(self, bruto: dict) -> RespostaLLM:
        try:
            escolha = (bruto.get("choices") or [])[0]
            mensagem = escolha.get("message") or {}
        except (IndexError, AttributeError, TypeError) as exc:
            raise RespostaLLMInvalida("resposta sem choices") from exc

        chamadas: list[ToolCall] = []
        for tc in mensagem.get("tool_calls") or []:
            funcao = tc.get("function") or {}
            chamadas.append(
                ToolCall(
                    id=str(tc.get("id") or ""),
                    nome=str(funcao.get("name") or ""),
                    argumentos=parse_argumentos(funcao.get("arguments")),
                )
            )

        uso = bruto.get("usage") or {}
        return RespostaLLM(
            texto=mensagem.get("content"),
            tool_calls=tuple(chamadas),
            tokens_entrada=int(uso.get("prompt_tokens") or 0),
            tokens_saida=int(uso.get("completion_tokens") or 0),
            finish_reason=str(escolha.get("finish_reason") or ""),
        )
