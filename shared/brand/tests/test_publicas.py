"""Guarda das superficies publicas: catalogo e site sao sempre claros e em Hanken."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tokens import RAIZ

SUPERFICIES_PUBLICAS = ["catalogo-publico/app", "site"]


def test_catalogo_nao_usa_mais_inter():
    for rel in ["catalogo-publico/app/static/css/catalog.css",
                "catalogo-publico/app/templates/base.html"]:
        assert "Inter" not in (RAIZ / rel).read_text(encoding="utf-8"), rel


@pytest.mark.parametrize("rel", SUPERFICIES_PUBLICAS)
def test_superficie_publica_nao_tem_tema_escuro(rel):
    """Modo escuro e dos paineis. Vitrine e site sao sempre claros.

    A copia gerada de revy-tokens.css fica de fora da varredura: ela e o
    canonico inteiro, bloco escuro incluso, e sair dela e trabalho do
    sync_tokens.py, nao do produto. O bloco so pinta se alguem escrever
    data-theme no HTML — e e exatamente isso que este teste proibe. Que a
    copia siga identica ao canonico ja e guardado por test_tokens.py.
    """
    base = RAIZ / rel
    arquivos = [f for f in list(base.rglob("*.html")) + list(base.rglob("*.css"))
                if f.name != "revy-tokens.css"]
    with_theme = [f for f in arquivos if "data-theme" in f.read_text(encoding="utf-8")]
    assert not with_theme, [str(f.relative_to(RAIZ)) for f in with_theme]
