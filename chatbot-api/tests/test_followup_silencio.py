import pytest

from app.followup_job import texto_followup


@pytest.mark.parametrize("etapa", [
    "so_oi", "anuncio", "vendo_opcoes", "faltou_dado", "catalogo", "a_vista",
])
def test_toda_etapa_tem_os_dois_toques(etapa):
    assert texto_followup(etapa, 1)
    assert texto_followup(etapa, 2)
    assert texto_followup(etapa, 1) != texto_followup(etapa, 2)


def test_etapa_desconhecida_cai_em_so_oi():
    """Spec §5.9: sem certeza, usa a linha 'só deu oi' — não inventa texto."""
    assert texto_followup("etapa-que-nao-existe", 1) == texto_followup("so_oi", 1)


def test_nao_existe_terceiro_toque():
    with pytest.raises(ValueError):
        texto_followup("so_oi", 3)


def test_texto_nao_menciona_parcela():
    """Invariante do projeto: parcela não vai ao cliente pelo bot."""
    for etapa in ["so_oi", "anuncio", "vendo_opcoes", "faltou_dado", "catalogo", "a_vista"]:
        for toque in (1, 2):
            assert "parcela" not in texto_followup(etapa, toque).lower()
