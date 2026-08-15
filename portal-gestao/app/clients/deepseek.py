"""Client do provedor de LLM (DeepSeek, API compatível com OpenAI).

Único lugar do repo que conhece o formato do provedor.

Duas coisas que este client NÃO faz, de propósito:
- não usa ``app/clients/_retry.py``: aquele helper só repete GET/HEAD/OPTIONS
  ou POST com ``Idempotency-Key`` (``_retry.py:44-46``), e este POST não é
  idempotente pelo padrão da casa;
- não loga payload nem chave, nunca. Em falha 4xx loga só o CORPO DA
  RESPOSTA do provedor (truncado) — nunca o corpo do request — porque um
  400 mudo (`status=400`) não diz qual campo o provedor rejeitou.
"""
from __future__ import annotations

import json
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

# 529 nao e padrao HTTP, mas varios provedores (NVIDIA NIM entre eles) usam
# para "sobrecarregado, tente de novo" -- descoberto num smoke real em
# 2026-08-12, quando um turno morreu sem repetir. E o erro mais transitorio
# que existe: nao repetir nele entrega "assistente indisponivel" ao dono por
# causa de fila do provedor.
STATUS_QUE_REPETEM = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

TAMANHO_MAX_LOG_CORPO = 300


def _resumo_corpo_resposta(resposta: httpx.Response) -> str:
    """Corpo da RESPOSTA do provedor, truncado — nunca o request, nunca a
    chave. Best-effort: se nem o texto vier legível, loga string vazia em
    vez de derrubar o client por causa de um log."""
    try:
        texto = (resposta.text or "").strip()
    except Exception:
        return ""
    if len(texto) > TAMANHO_MAX_LOG_CORPO:
        return texto[:TAMANHO_MAX_LOG_CORPO] + "…"
    return texto


def montar_payload(
    mensagens: Sequence[MensagemLLM],
    ferramentas: Sequence[dict[str, Any]],
    *,
    modelo: str,
    esforco: EsforcoLLM,
    max_tokens: int,
    stream: bool = False,
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
        if m.tool_calls:
            # Formato OpenAI: a mensagem assistant que pediu ferramenta leva
            # ``tool_calls`` estruturado, e ``content`` vai None quando não há
            # texto — é essa entrada que a mensagem role=tool seguinte referencia
            # por ``tool_call_id``.
            item["content"] = m.conteudo or None
            item["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.nome,
                        "arguments": json.dumps(tc.argumentos, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
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
    if stream:
        corpo["stream"] = True
        # Sem isto o provedor nao manda usage no fim do stream e o turno
        # perde a contabilidade de token (teto_tokens do runner ficaria cego).
        corpo["stream_options"] = {"include_usage": True}
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
        ao_texto: Callable[[str], None] | None = None,
    ) -> RespostaLLM:
        if not self.configurado:
            raise LLMIndisponivel("provedor de LLM não configurado")

        payload = montar_payload(
            mensagens, ferramentas, modelo=self.modelo, esforco=esforco,
            max_tokens=max_tokens, stream=ao_texto is not None,
        )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        inicio = time.monotonic()

        ultimo_status: int | None = None
        ultimo_corpo_erro: str | None = None
        for tentativa in range(self.retries + 1):
            consumiu_corpo = False
            try:
                with httpx.Client(
                    base_url=self.base_url,
                    headers=headers,
                    timeout=self.timeout,
                    transport=self._transport,
                ) as client:
                    if ao_texto is not None:
                        with client.stream(
                            "POST", "/chat/completions", json=payload
                        ) as resposta:
                            ultimo_status = resposta.status_code
                            if resposta.status_code == 200:
                                # A partir daqui o corpo entra em jogo: retry
                                # queimaria token e duplicaria ao_texto.
                                consumiu_corpo = True
                                saida = self._consumir_stream(resposta, ao_texto)
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
                                if 400 <= resposta.status_code < 500:
                                    ultimo_corpo_erro = _resumo_corpo_resposta(resposta)
                                break
                    else:
                        resposta = client.post("/chat/completions", json=payload)
                        ultimo_status = resposta.status_code
                        if resposta.status_code == 200:
                            try:
                                corpo = resposta.json()
                            except ValueError as exc:
                                raise RespostaLLMInvalida("resposta com corpo inválido") from exc
                            saida = self._interpretar(corpo)
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
                            if 400 <= resposta.status_code < 500:
                                # Só o corpo da RESPOSTA (nunca o payload que mandamos
                                # nem a chave): é a mensagem de erro do provedor —
                                # p.ex. "reasoning_effort não suportado" — que
                                # transforma um 400 mudo num log diagnosticável.
                                ultimo_corpo_erro = _resumo_corpo_resposta(resposta)
                            break  # 4xx de validação: repetir só queima token
            except httpx.HTTPError:
                if consumiu_corpo:
                    break
                ultimo_status = None
            if tentativa < self.retries:
                self._sleeper(self.backoff * (2**tentativa))

        if ultimo_corpo_erro:
            logger.warning(
                "copiloto_llm falha modelo=%s status=%s corpo=%s",
                self.modelo,
                ultimo_status,
                ultimo_corpo_erro,
            )
        else:
            logger.warning(
                "copiloto_llm falha modelo=%s status=%s", self.modelo, ultimo_status
            )
        raise LLMIndisponivel(f"provedor de LLM indisponível (status={ultimo_status})")

    def _consumir_stream(
        self, resposta: httpx.Response, ao_texto: Callable[[str], None]
    ) -> RespostaLLM:
        """Monta RespostaLLM a partir do SSE. Deltas de tool_call chegam
        fatiados e SEM repetir id/nome — a montagem é por ``index``, nunca
        por ordem de chegada."""
        texto = ""
        finish = ""
        entrada = saida = 0
        parciais: dict[int, dict[str, str]] = {}
        for linha in resposta.iter_lines():
            if not linha.startswith("data:"):
                continue
            dado = linha[5:].strip()
            if dado == "[DONE]":
                break
            try:
                pedaco = json.loads(dado)
            except ValueError as exc:
                raise RespostaLLMInvalida("chunk SSE inválido") from exc
            uso = pedaco.get("usage") or {}
            if uso:
                entrada = int(uso.get("prompt_tokens") or 0)
                saida = int(uso.get("completion_tokens") or 0)
            for escolha in pedaco.get("choices") or []:
                if escolha.get("finish_reason"):
                    finish = str(escolha["finish_reason"])
                delta = escolha.get("delta") or {}
                if delta.get("content"):
                    texto += delta["content"]
                    ao_texto(texto)
                for tc in delta.get("tool_calls") or []:
                    slot = parciais.setdefault(
                        int(tc.get("index") or 0), {"id": "", "nome": "", "args": ""}
                    )
                    if tc.get("id"):
                        slot["id"] = str(tc["id"])
                    funcao = tc.get("function") or {}
                    if funcao.get("name"):
                        slot["nome"] = str(funcao["name"])
                    if funcao.get("arguments"):
                        slot["args"] += funcao["arguments"]
        chamadas = tuple(
            ToolCall(id=s["id"], nome=s["nome"], argumentos=parse_argumentos(s["args"]))
            for _, s in sorted(parciais.items())
        )
        return RespostaLLM(
            texto=texto or None,
            tool_calls=chamadas,
            tokens_entrada=entrada,
            tokens_saida=saida,
            finish_reason=finish,
        )

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
