import httpx
import pytest

from app.clients.deepseek import DeepSeekClient, montar_payload
from app.loja.copiloto.port import (
    LLMIndisponivel,
    MensagemLLM,
    RespostaLLMInvalida,
    ToolCall,
)

FERRAMENTAS = [
    {
        "name": "vendas_resumo",
        "description": "Receita e ticket do período",
        "parameters": {"type": "object", "properties": {}},
    }
]


def _mensagens():
    return [
        MensagemLLM(papel="system", conteudo="Você é o Copiloto."),
        MensagemLLM(papel="user", conteudo="Quantas vendas esse mês?"),
    ]


def test_payload_fixa_os_parametros_agenticos():
    payload = montar_payload(
        _mensagens(), FERRAMENTAS, modelo="DeepSeek-V4-Flash-0731",
        esforco="low", max_tokens=800,
    )
    assert payload["model"] == "DeepSeek-V4-Flash-0731"
    assert payload["temperature"] == 1.0
    assert payload["top_p"] == 0.95
    assert payload["max_tokens"] == 800
    assert payload["reasoning_effort"] == "low"
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["function"]["name"] == "vendas_resumo"


def test_payload_sem_ferramenta_nao_manda_campo_tools():
    payload = montar_payload(
        _mensagens(), [], modelo="m", esforco="low", max_tokens=800
    )
    assert "tools" not in payload


def test_payload_serializa_mensagem_de_tool():
    mensagens = _mensagens() + [
        MensagemLLM(
            papel="tool", conteudo='{"qtd": 2}', tool_call_id="call-1",
            nome="vendas_resumo",
        )
    ]
    payload = montar_payload(
        mensagens, FERRAMENTAS, modelo="m", esforco="low", max_tokens=800
    )
    ultima = payload["messages"][-1]
    assert ultima["role"] == "tool"
    assert ultima["tool_call_id"] == "call-1"


def test_payload_serializa_tool_calls_da_mensagem_assistant():
    """Formato OpenAI: assistant que pediu ferramenta leva ``tool_calls``
    estruturado (id/type/function.name/function.arguments-como-string), não
    um resumo de texto — é isso que a mensagem role=tool seguinte referencia
    por ``tool_call_id``."""
    mensagens = _mensagens() + [
        MensagemLLM(
            papel="assistant",
            conteudo="",
            tool_calls=(
                ToolCall(id="call-1", nome="vendas_resumo", argumentos={"periodo": "mes"}),
            ),
        ),
        MensagemLLM(
            papel="tool", conteudo='{"qtd": 2}', tool_call_id="call-1",
            nome="vendas_resumo",
        ),
    ]
    payload = montar_payload(
        mensagens, FERRAMENTAS, modelo="m", esforco="low", max_tokens=800
    )
    assistant_msg = payload["messages"][-2]
    tool_msg = payload["messages"][-1]

    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] is None
    assert assistant_msg["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "vendas_resumo",
                "arguments": '{"periodo": "mes"}',
            },
        }
    ]
    # Propriedade que importa de verdade: o id declarado no tool_calls do
    # assistant é o mesmo tool_call_id que a mensagem role=tool referencia.
    assert assistant_msg["tool_calls"][0]["id"] == tool_msg["tool_call_id"]


def test_payload_assistant_com_texto_e_tool_calls_preserva_o_texto():
    mensagens = _mensagens() + [
        MensagemLLM(
            papel="assistant",
            conteudo="Vou checar.",
            tool_calls=(ToolCall(id="call-9", nome="vendas_resumo", argumentos={}),),
        ),
    ]
    payload = montar_payload(
        mensagens, FERRAMENTAS, modelo="m", esforco="low", max_tokens=800
    )
    assistant_msg = payload["messages"][-1]
    assert assistant_msg["content"] == "Vou checar."
    assert assistant_msg["tool_calls"][0]["function"]["arguments"] == "{}"


def _client(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return DeepSeekClient(
        base_url="https://api.deepseek.test",
        api_key="chave",
        modelo="DeepSeek-V4-Flash-0731",
        transport=transport,
        sleeper=lambda _: None,
        **kwargs,
    )


def test_le_texto_e_tokens_da_resposta():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Você vendeu 2 motos."}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 40},
            },
        )

    r = _client(handler).completar(_mensagens(), FERRAMENTAS)
    assert r.texto == "Você vendeu 2 motos."
    assert r.tokens_entrada == 1200
    assert r.tokens_saida == 40
    assert r.tool_calls == ()


def test_le_tool_call_com_argumentos():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "vendas_resumo",
                                        "arguments": '{"periodo": "mes"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 900, "completion_tokens": 25},
            },
        )

    r = _client(handler).completar(_mensagens(), FERRAMENTAS)
    assert r.tool_calls[0].nome == "vendas_resumo"
    assert r.tool_calls[0].argumentos == {"periodo": "mes"}


def test_erro_5xx_repete_e_depois_desiste():
    tentativas = []

    def handler(request):
        tentativas.append(1)
        return httpx.Response(503, json={"error": "indisponivel"})

    with pytest.raises(LLMIndisponivel):
        _client(handler, retries=1).completar(_mensagens(), FERRAMENTAS)
    assert len(tentativas) == 2


def test_erro_400_nao_repete():
    tentativas = []

    def handler(request):
        tentativas.append(1)
        return httpx.Response(400, json={"error": "payload invalido"})

    with pytest.raises(LLMIndisponivel):
        _client(handler, retries=2).completar(_mensagens(), FERRAMENTAS)
    assert len(tentativas) == 1


def test_sem_chave_nao_chama_a_rede():
    def handler(request):  # pragma: no cover - não deve ser chamado
        raise AssertionError("não deveria ter feito request")

    client = DeepSeekClient(
        base_url="https://api.deepseek.test",
        api_key="",
        modelo="m",
        transport=httpx.MockTransport(handler),
    )
    assert client.configurado is False
    with pytest.raises(LLMIndisponivel):
        client.completar(_mensagens(), FERRAMENTAS)


def test_chave_nunca_aparece_em_log(caplog):
    def handler(request):
        assert request.headers["authorization"] == "Bearer chave-secreta"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    client = DeepSeekClient(
        base_url="https://api.deepseek.test",
        api_key="chave-secreta",
        modelo="m",
        transport=httpx.MockTransport(handler),
    )
    with caplog.at_level("DEBUG"):
        client.completar(_mensagens(), FERRAMENTAS)
    assert "chave-secreta" not in caplog.text
    assert "Quantas vendas" not in caplog.text


def test_erro_400_loga_o_corpo_da_resposta_para_diagnostico(caplog):
    """I4: um 400 mudo (`status=400`) não diz qual campo o provedor
    rejeitou. O corpo da RESPOSTA (nunca o request) precisa entrar no log
    para o smoke contra o provedor de verdade ser diagnosticável."""

    def handler(request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "reasoning_effort is not supported for this model"
                }
            },
        )

    with caplog.at_level("WARNING"):
        with pytest.raises(LLMIndisponivel):
            _client(handler).completar(_mensagens(), FERRAMENTAS)

    assert "reasoning_effort is not supported for this model" in caplog.text


def test_erro_5xx_nao_loga_corpo_da_resposta(caplog):
    """Só 4xx é diagnóstico de payload — 5xx é o provedor caindo, não a
    gente errando um campo, então o corpo não precisa (nem deveria) aparecer."""

    def handler(request):
        return httpx.Response(503, text="upstream connect error")

    with caplog.at_level("WARNING"):
        with pytest.raises(LLMIndisponivel):
            _client(handler, retries=0).completar(_mensagens(), FERRAMENTAS)

    assert "upstream connect error" not in caplog.text


def test_chave_nunca_aparece_em_log_mesmo_em_erro_400(caplog):
    def handler(request):
        assert request.headers["authorization"] == "Bearer chave-secreta"
        return httpx.Response(
            400, json={"error": {"message": "invalid parameter: top_p"}}
        )

    client = DeepSeekClient(
        base_url="https://api.deepseek.test",
        api_key="chave-secreta",
        modelo="m",
        transport=httpx.MockTransport(handler),
    )
    with caplog.at_level("DEBUG"):
        with pytest.raises(LLMIndisponivel):
            client.completar(_mensagens(), FERRAMENTAS)
    assert "chave-secreta" not in caplog.text
    assert "Quantas vendas" not in caplog.text
    # Log continua diagnosticável: o corpo do erro aparece, só a chave não.
    assert "invalid parameter: top_p" in caplog.text


def test_200_com_corpo_invalido_nao_repete():
    tentativas = []

    def handler(request):
        tentativas.append(1)
        return httpx.Response(200, text="<html>gateway error</html>")

    with pytest.raises(RespostaLLMInvalida):
        _client(handler, retries=2).completar(_mensagens(), FERRAMENTAS)
    assert len(tentativas) == 1


def test_corpo_invalido_sempre_levanta_resposta_llm_invalida():
    def handler(request):
        return httpx.Response(200, text="not json at all")

    with pytest.raises(RespostaLLMInvalida):
        _client(handler).completar(_mensagens(), FERRAMENTAS)


def test_erro_529_sobrecarregado_repete():
    """529 nao e padrao HTTP, mas provedores usam para "tente de novo".

    Achado num smoke real contra a NVIDIA NIM em 2026-08-12: sem isto, fila do
    provedor vira "assistente indisponivel" para o dono na primeira tentativa.
    """
    tentativas = []

    def handler(request):
        tentativas.append(1)
        return httpx.Response(529, json={"error": "overloaded"})

    with pytest.raises(LLMIndisponivel):
        _client(handler, retries=2).completar(_mensagens(), FERRAMENTAS)
    assert len(tentativas) == 3
