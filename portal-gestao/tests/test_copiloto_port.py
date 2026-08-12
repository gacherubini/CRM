import pytest

from app.loja.copiloto.port import (
    LLMFake,
    RespostaLLM,
    RespostaLLMInvalida,
    ToolCall,
    parse_argumentos,
)


def test_fake_devolve_as_respostas_na_ordem():
    fake = LLMFake(
        [
            RespostaLLM(
                texto=None,
                tool_calls=(ToolCall(id="1", nome="vendas_resumo", argumentos={}),),
                tokens_entrada=100,
                tokens_saida=20,
                finish_reason="tool_calls",
            ),
            RespostaLLM(
                texto="Você vendeu 2 motos.",
                tool_calls=(),
                tokens_entrada=300,
                tokens_saida=40,
                finish_reason="stop",
            ),
        ]
    )
    primeira = fake.completar([], [], esforco="low", max_tokens=800)
    assert primeira.tool_calls[0].nome == "vendas_resumo"
    segunda = fake.completar([], [], esforco="low", max_tokens=800)
    assert segunda.texto == "Você vendeu 2 motos."
    assert len(fake.chamadas) == 2
    assert fake.chamadas[0]["esforco"] == "low"


def test_fake_sem_resposta_programada_levanta():
    fake = LLMFake([])
    with pytest.raises(AssertionError):
        fake.completar([], [], esforco="low", max_tokens=800)


def test_parse_argumentos_aceita_json_valido():
    assert parse_argumentos('{"periodo": "mes"}') == {"periodo": "mes"}


def test_parse_argumentos_aceita_vazio():
    assert parse_argumentos("") == {}
    assert parse_argumentos(None) == {}


def test_parse_argumentos_recusa_json_quebrado():
    with pytest.raises(RespostaLLMInvalida):
        parse_argumentos('{"periodo": ')


def test_parse_argumentos_recusa_o_que_nao_e_objeto():
    with pytest.raises(RespostaLLMInvalida):
        parse_argumentos('["mes"]')
