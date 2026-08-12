"""Corte do histórico do Copiloto por orçamento de tokens (app/loja/copiloto/historico.py).

Funções puras: sem banco, sem cliente HTTP, sem LLM.
"""
from app.loja.copiloto.historico import estimar_tokens, selecionar_historico

# Par "aaaa"/"aaaa": 4 caracteres cada -> ceil(4/4) + sobrecarga(4) = 5 tokens
# por mensagem, 10 tokens por par. Usado como unidade previsível nos testes
# de corte por orçamento.
_PAR_10_TOKENS = ("aaaa", "aaaa")


def _par(rotulo: str, tamanho: int) -> tuple[str, str]:
    """Par com pergunta/resposta do tamanho pedido, identificável por rótulo."""
    return (f"{rotulo}-pergunta-" + "x" * tamanho, f"{rotulo}-resposta-" + "x" * tamanho)


def test_estimar_tokens_usa_4_caracteres_por_token_arredondando_para_cima():
    # 4 chars -> 1 token de texto + 4 de sobrecarga = 5.
    assert estimar_tokens("aaaa") == 5
    # 5 chars não cabe em 1 token exato -> arredonda para cima (2) + 4 = 6.
    assert estimar_tokens("aaaaa") == 6


def test_estimar_tokens_string_vazia_ainda_cobra_a_sobrecarga_da_mensagem():
    assert estimar_tokens("") == 4


def test_selecionar_historico_lista_vazia_devolve_lista_vazia():
    assert selecionar_historico([], 2000) == []


def test_selecionar_historico_orcamento_zero_ainda_devolve_o_par_mais_recente():
    pares = [_PAR_10_TOKENS, ("qual meu ticket em agosto?", "Foi R$ 25.000.")]
    resultado = selecionar_historico(pares, 0)
    assert resultado == [pares[-1]]


def test_selecionar_historico_orcamento_negativo_ainda_devolve_o_par_mais_recente():
    pares = [_PAR_10_TOKENS, ("e agora?", "Também não sei.")]
    resultado = selecionar_historico(pares, -10)
    assert resultado == [pares[-1]]


def test_selecionar_historico_par_unico_grande_demais_e_incluido_mesmo_assim():
    """Perder a última troca é o pior corte: é ela que dá sentido a perguntas
    como "e o mês passado?". Seguro na prática porque a resposta do provedor
    é limitada por max_tokens (runner.executar_turno)."""
    par_grande = _par("unico", tamanho=5000)
    assert selecionar_historico([par_grande], orcamento_tokens=1) == [par_grande]


def test_selecionar_historico_cabe_tudo_devolve_todos_os_pares():
    pares = [_PAR_10_TOKENS, _PAR_10_TOKENS, _PAR_10_TOKENS]
    # 3 pares de 10 tokens = 30; orçamento generoso não corta nada.
    assert selecionar_historico(pares, orcamento_tokens=1000) == pares


def test_selecionar_historico_corta_os_pares_mais_antigos_primeiro():
    antigo = _par("antigo", 0)
    meio = _par("meio", 0)
    recente = _par("recente", 0)
    pares = [antigo, meio, recente]  # cronológico: antigo -> meio -> recente

    # Cada par custa 10 tokens (medido via estimar_tokens, não hardcoded).
    custo_par = estimar_tokens(antigo[0]) + estimar_tokens(antigo[1])
    assert custo_par == estimar_tokens(meio[0]) + estimar_tokens(meio[1])

    # Cabe o recente (10) + o meio (10) = 20, mas não sobra para o antigo
    # (mais 10 estouraria 25).
    resultado = selecionar_historico(pares, orcamento_tokens=custo_par * 2 + 5)
    assert resultado == [meio, recente]
    assert antigo not in resultado


def test_selecionar_historico_para_no_par_grande_em_vez_de_pular():
    """Um par grande no MEIO da conversa não pode ser pulado para encaixar um
    par pequeno mais antigo depois dele — buraco no meio é pior que
    histórico curto: o modelo veria uma sequência que nunca aconteceu."""
    antigo_pequeno = _par("antigo", 0)
    meio_grande = _par("meio-grande", tamanho=2000)
    recente = _par("recente", 0)
    pares = [antigo_pequeno, meio_grande, recente]

    custo_recente = estimar_tokens(recente[0]) + estimar_tokens(recente[1])
    custo_antigo = estimar_tokens(antigo_pequeno[0]) + estimar_tokens(antigo_pequeno[1])
    # Orçamento cobre o recente + o antigo pequeno somados, mas NÃO cobre o
    # par grande do meio — se o corte "pulasse" o grande para pegar o
    # pequeno mais antigo, o teste abaixo falharia.
    orcamento = custo_recente + custo_antigo + 2

    resultado = selecionar_historico(pares, orcamento_tokens=orcamento)

    assert resultado == [recente]
    assert antigo_pequeno not in resultado
    assert meio_grande not in resultado


def test_selecionar_historico_preserva_ordem_cronologica_na_saida():
    p1 = _par("t1", 0)
    p2 = _par("t2", 0)
    p3 = _par("t3", 0)
    pares = [p1, p2, p3]

    resultado = selecionar_historico(pares, orcamento_tokens=10_000)

    assert resultado == [p1, p2, p3]  # mais antigo primeiro, igual à entrada
