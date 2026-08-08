"""Guardas da varredura de marca.

O app.css de cada painel e carregado DEPOIS do revy-tokens.css. Se ele reabrir
:root e redeclarar um token canonico, o canonico deixa de pintar e a fonte
unica vira decoracao. Foi assim que o ambar do modo escuro divergiu sem que
ninguem visse. Estes testes existem para que isso quebre aqui.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from css_audit import PAINEIS, caminho, contem, raios_literais, usos_de_var, variaveis_do_root
from tokens import CANONICAL, RAIZ, load_tokens


@pytest.mark.parametrize("rel", PAINEIS)
def test_app_css_nao_redeclara_token_canonico(rel):
    """Quem redeclara vence no cascade e anula a fonte unica."""
    canonicos = set(load_tokens(CANONICAL)["light"])
    locais = variaveis_do_root(caminho(rel))
    invasores = sorted(canonicos & locais)
    assert not invasores, (
        f"{rel} redeclara {len(invasores)} token(s) canonico(s), entao "
        f"shared/brand/revy-tokens.css nao pinta: {' '.join(invasores)}"
    )
