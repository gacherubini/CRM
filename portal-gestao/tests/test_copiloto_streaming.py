"""Streaming SSE do provedor (wire compatível com OpenAI).

Sem ``ao_texto`` o client tem que continuar fazendo POST normal — é isso que
mantém o resto da suíte verde e o caminho de produção inalterado até o worker
optar por streaming.
"""
import httpx

from app.clients.deepseek import DeepSeekClient
from app.loja.copiloto.port import MensagemLLM

SSE = (
    'data: {"choices":[{"delta":{"content":"Você "},"index":0}]}\n\n'
    'data: {"choices":[{"delta":{"content":"vendeu "},"index":0}]}\n\n'
    'data: {"choices":[{"delta":{"content":"2."},"index":0,"finish_reason":"stop"}]}\n\n'
    'data: {"choices":[],"usage":{"prompt_tokens":100,"completion_tokens":8}}\n\n'
    "data: [DONE]\n\n"
)


def _client(handler):
    return DeepSeekClient(
        "https://provedor.test", "chave", "modelo-x",
        transport=httpx.MockTransport(handler),
    )


def test_streaming_entrega_pedacos_e_o_texto_final():
    vistos = []

    def handler(request):
        assert httpx.Request is not None
        import json as _json
        assert _json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=SSE,
                              headers={"content-type": "text/event-stream"})

    resposta = _client(handler).completar(
        [MensagemLLM(papel="user", conteudo="quanto vendi?")], [],
        ao_texto=vistos.append,
    )
    assert resposta.texto == "Você vendeu 2."
    assert vistos == ["Você ", "Você vendeu ", "Você vendeu 2."]
    assert resposta.tokens_entrada == 100
    assert resposta.tokens_saida == 8
    assert resposta.finish_reason == "stop"


def test_sem_callback_continua_sem_stream():
    """Caminho de produção atual: nenhum byte de comportamento muda enquanto
    o worker não pedir streaming."""
    def handler(request):
        import json as _json
        assert "stream" not in _json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    assert _client(handler).completar(
        [MensagemLLM(papel="user", conteudo="oi")], []
    ).texto == "ok"


def test_streaming_monta_tool_call_por_indice():
    sse = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1",'
        '"function":{"name":"vendas_resumo","arguments":"{\\"per"}}]},"index":0}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"iodo\\":\\"mes\\"}"}}]},"index":0,'
        '"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=sse,
                              headers={"content-type": "text/event-stream"})

    resposta = _client(handler).completar(
        [MensagemLLM(papel="user", conteudo="vendas?")], [], ao_texto=lambda _: None
    )
    assert len(resposta.tool_calls) == 1
    assert resposta.tool_calls[0].nome == "vendas_resumo"
    assert resposta.tool_calls[0].argumentos == {"periodo": "mes"}
