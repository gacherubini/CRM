from app.loja.copiloto.cache import CacheTTL, chave_overview


def test_segunda_chamada_nao_reexecuta_o_produtor():
    relogio = {"t": 1000.0}
    cache = CacheTTL(ttl_segundos=90, agora=lambda: relogio["t"])
    chamadas = []

    def produtor():
        chamadas.append(1)
        return "overview"

    assert cache.obter("k", produtor) == "overview"
    assert cache.obter("k", produtor) == "overview"
    assert len(chamadas) == 1


def test_expira_depois_do_ttl():
    relogio = {"t": 1000.0}
    cache = CacheTTL(ttl_segundos=90, agora=lambda: relogio["t"])
    chamadas = []

    def produtor():
        chamadas.append(1)
        return "overview"

    cache.obter("k", produtor)
    relogio["t"] += 91
    cache.obter("k", produtor)
    assert len(chamadas) == 2


def test_chaves_diferentes_nao_se_misturam():
    cache = CacheTTL(ttl_segundos=90)
    assert cache.obter("a", lambda: 1) == 1
    assert cache.obter("b", lambda: 2) == 2
    assert cache.obter("a", lambda: 99) == 1


def test_producao_que_levanta_nao_fica_cacheada():
    cache = CacheTTL(ttl_segundos=90)
    chamadas = []

    def explode():
        chamadas.append(1)
        raise RuntimeError("boom")

    for _ in range(2):
        try:
            cache.obter("k", explode)
        except RuntimeError:
            pass
    assert len(chamadas) == 2


def test_invalidar_por_prefixo_da_loja():
    cache = CacheTTL(ttl_segundos=90)
    cache.obter("loja-a:x", lambda: 1)
    cache.obter("loja-b:x", lambda: 2)
    cache.invalidar(prefixo="loja-a:")
    assert cache.tamanho == 1


def test_chave_do_overview_separa_papel_e_periodo():
    a = chave_overview("loja-teste", "dono", "2026-08-01", "2026-08-31")
    b = chave_overview("loja-teste", "vendedor", "2026-08-01", "2026-08-31")
    c = chave_overview("loja-teste", "dono", "2026-07-01", "2026-07-31")
    assert a != b != c and a != c
    assert a.startswith("loja-teste:")
