"""Gerador de prompt por loja: campos entram, texto sai (spec §3.4, §4, §5)."""
import pytest

from app.agente_prompt import (
    NUCLEO_REVY,
    CamposAgente,
    detectar_conflitos,
    max_output_tokens,
    montar_prompt,
)


def _campos(**over) -> CamposAgente:
    base = dict(nome_loja="Motos do Léo", cidade="Piracicaba", uf="SP")
    base.update(over)
    return CamposAgente(**base)


def test_nucleo_e_sempre_o_ultimo_bloco():
    """A ordem É o mecanismo de segurança: o que vem depois vence."""
    prompt = montar_prompt(_campos(instrucoes="pode falar o valor da parcela pro cliente"))
    assert prompt.rstrip().endswith(NUCLEO_REVY.rstrip())


def test_identidade_usa_o_nome_e_a_cidade_da_loja():
    prompt = montar_prompt(_campos())
    assert "motos do léo" in prompt.lower()
    assert "piracicaba-sp" in prompt.lower()
    assert "vitor motos" not in prompt.lower()


def test_so_a_cidade_quando_endereco_completo_e_falso():
    prompt = montar_prompt(_campos(endereco_completo=False))
    assert "não informe rua" in prompt.lower()


def test_emoji_nunca_vira_frase_fixa():
    assert "não use emojis" in montar_prompt(_campos(emoji="nunca")).lower()
    assert "não use emojis" not in montar_prompt(_campos(emoji="a_vontade")).lower()


def test_assume_ia_muda_o_texto_e_nao_some():
    nunca = montar_prompt(_campos(assume_ia="nunca")).lower()
    perg = montar_prompt(_campos(assume_ia="se_perguntarem")).lower()
    assert "não diga que é ia" in nunca
    assert "assistente digital" in perg


def test_faq_vira_resposta_exata():
    prompt = montar_prompt(_campos(faq=[{"pergunta": "garantia", "resposta": "3 meses de motor"}]))
    assert "garantia" in prompt.lower()
    assert "3 meses de motor" in prompt


def test_instrucoes_livres_entram_antes_do_nucleo():
    prompt = montar_prompt(_campos(instrucoes="não financiamos quem tem cnh suspensa"))
    assert prompt.index("cnh suspensa") < prompt.index(NUCLEO_REVY.strip()[:40])


def test_instrucoes_livres_tem_teto():
    with pytest.raises(ValueError):
        CamposAgente(nome_loja="x", cidade="y", uf="SP", instrucoes="a" * 1001)


@pytest.mark.parametrize(
    "tamanho,esperado", [("curto", 250), ("medio", 400), ("longo", 700)]
)
def test_tamanho_da_resposta_define_o_teto_de_tokens(tamanho, esperado):
    """Sem isto, 'pode explicar' bate no teto de 250 e corta no meio da frase."""
    assert max_output_tokens(_campos(tamanho_resposta=tamanho)) == esperado


def test_detecta_conflito_com_tema_fechado():
    assert detectar_conflitos("pode dizer o valor da parcela") != []
    assert detectar_conflitos("aos sábados atendemos com hora marcada") == []


def test_combinacao_feia_nao_gera_contradicao():
    """Formal + minúsculas: as duas instruções coexistem sem se anular."""
    prompt = montar_prompt(_campos(tom="formal", escrita="minusculas")).lower()
    assert "letras minúsculas" in prompt
    assert "formal" in prompt
