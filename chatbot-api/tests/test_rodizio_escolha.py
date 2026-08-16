from app.rodizio import escolher_proximo


def test_comeca_no_ponteiro_nao_no_topo():
    vend, pos, fechou = escolher_proximo(
        ["a", "b", "c"], ponteiro=1, pendentes=set(), ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert (vend, pos, fechou) == ("b", 2, False)


def test_pula_quem_ja_tem_oferta_aberta():
    vend, pos, fechou = escolher_proximo(
        ["a", "b", "c"], ponteiro=0, pendentes={"a"}, ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert vend == "b"


def test_todos_ocupados_devolve_none_sem_fechar_volta():
    vend, pos, fechou = escolher_proximo(
        ["a", "b"], ponteiro=0, pendentes={"a", "b"}, ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert vend is None
    assert fechou is False


def test_volta_fecha_quando_todos_ja_receberam():
    vend, pos, fechou = escolher_proximo(
        ["a", "b"], ponteiro=0, pendentes=set(), ja_ofertados={"a", "b"},
        posicao_inicial=0,
    )
    assert vend is None
    assert fechou is True


def test_fila_vazia_fecha_a_volta_na_hora():
    vend, pos, fechou = escolher_proximo(
        [], ponteiro=0, pendentes=set(), ja_ofertados=set(), posicao_inicial=None,
    )
    assert (vend, fechou) == (None, True)


def test_ponteiro_da_volta_circular():
    vend, pos, fechou = escolher_proximo(
        ["a", "b", "c"], ponteiro=2, pendentes=set(), ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert (vend, pos) == ("c", 0)
