"""Gerador de prompt por loja: campos entram, texto sai (spec §3.4, §4, §5)."""
import pydantic
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


@pytest.mark.parametrize(
    "campo,invalido",
    [
        ("assume_ia", "as_vezes"),
        ("tom", "amigavel"),
        ("tratamento", "apelido"),
        ("escrita", "MINUSCULAS"),
        ("emoji", "sempre"),
        ("tamanho_resposta", "gigante"),
        ("fotos", "so_quando_pedir "),
        ("sem_moto_anuncio", "segura "),
    ],
)
def test_valor_invalido_em_campo_de_escolha_e_recusado(campo, invalido):
    """Antes: lookup direto em dicionário — `{"tom": "amigavel"}` virava 500
    (KeyError), e um typo com espaço a mais (`"segura "`) caía no `else` e
    trocava o comportamento em silêncio, sem erro nenhum. Agora é 422 do
    pydantic antes de qualquer um dos dois."""
    with pytest.raises(pydantic.ValidationError):
        _campos(**{campo: invalido})


@pytest.mark.parametrize(
    "opcao,trecho",
    [
        ("quando_pedir", "quando o cliente pedir explicitamente"),
        ("depois_da_simulacao", "depois que a simulação for concluída"),
        ("fora_do_horario", "fora do horário de atendimento"),
    ],
)
def test_cada_opcao_de_handoff_aparece_no_prompt(opcao, trecho):
    """spec §3.4: REGRAS DA LOJA inclui handoff. Antes, o campo era persistido
    e publicado mas nunca virava texto nenhum."""
    prompt = montar_prompt(_campos(handoff=[opcao])).lower()
    assert trecho in prompt


def test_handoff_vazio_nao_gera_linha_orfa():
    prompt = montar_prompt(_campos(handoff=[])).lower()
    assert "encaminhe o atendimento" not in prompt


def test_horario_sem_zero_a_esquerda_e_recusado():
    """"8:00" compara errado em `esta_em_horario` (comparação de string) e
    deixa o bot mudo o dia inteiro sem erro nenhum — bloqueia na entrada."""
    with pytest.raises(pydantic.ValidationError):
        _campos(horario={"ter": ["8:00", "18:00"]})


def test_horario_com_uma_entrada_e_recusado():
    with pytest.raises(pydantic.ValidationError):
        _campos(horario={"ter": ["08:00"]})


def test_horario_com_zero_a_esquerda_e_aceito():
    campos = _campos(horario={"ter": ["08:00", "18:00"]})
    assert campos.horario["ter"] == ["08:00", "18:00"]


def test_so_lead_anuncio_foi_removido():
    """Decisão do dono: campo morto sai do schema (nada no produto o consome
    — o gate dependeria da atribuição CTWA, que tem buraco conhecido)."""
    assert "so_lead_anuncio" not in CamposAgente.model_fields
