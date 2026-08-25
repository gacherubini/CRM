"""`node --check` em todo JS da pasta static.

Não substitui olhar no navegador — pytest não executa uma linha de JS, e foi essa
cegueira que passou dois bugs do Copiloto em 15-16/08. Mas o caso mais bobo, o
arquivo que nem carrega, é barato de pegar aqui: um `'\\n'` que virou quebra de
linha de verdade dentro de aspas simples derrubou o arquivo inteiro da tela de
configuração do agente, e o sintoma na tela foi "nada acontece ao digitar" — que
não parece erro de sintaxe nenhum.

Pula quando não há node: o CI de Python não precisa ganhar uma dependência por
causa disto.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

JS = sorted((Path(__file__).resolve().parents[1] / "app" / "static" / "js").glob("*.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
@pytest.mark.parametrize("arquivo", JS, ids=lambda p: p.name)
def test_arquivo_js_carrega(arquivo):
    r = subprocess.run(
        ["node", "--check", str(arquivo)], capture_output=True, text=True
    )
    assert r.returncode == 0, f"{arquivo.name} não carrega:\n{r.stderr}"
