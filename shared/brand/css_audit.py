"""Medicoes objetivas sobre os CSS de produto.

Existe para que as guardas da varredura facam perguntas verificaveis em vez de
depender de leitura humana de um arquivo de 3.000 linhas. Nao opina sobre
estilo: so conta, lista e localiza.
"""
import re
from pathlib import Path

from tokens import RAIZ, load_tokens

# Os dois paineis. Site e catalogo nao tem app.css reabrindo :root.
PAINEIS = [
    "portal-gestao/app/static/css/app.css",
    "revy-trafego/app/static/css/app.css",
]

# border-radius que NAO conta como raio de caixa:
# 50% e circulo (ponto de estado, avatar), inherit copia o pai, 0 e ausencia.
_RAIO_LIVRE = ("50%", "inherit", "0")

_RADIUS = re.compile(r"border-radius:\s*([^;]+);")


def variaveis_do_root(path: Path) -> set[str]:
    """Nomes declarados nos blocos :root / [data-theme] do arquivo.

    Reaproveita o parser do canonico: ele ja ignora declaracoes que estao
    dentro de regra de componente (como o --sc dos resultados), que sao
    locais de propósito e nao fazem parte do vocabulario global.
    """
    t = load_tokens(path)
    return set(t["light"]) | set(t["dark"])


def usos_de_var(path: Path, nome: str) -> int:
    padrao = re.compile(r"var\(\s*" + re.escape(nome) + r"\s*[,)]")
    return len(padrao.findall(path.read_text(encoding="utf-8")))


def raios_literais(path: Path) -> list[tuple[int, str]]:
    achados = []
    for n, linha in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        for valor in _RADIUS.findall(linha):
            v = valor.strip()
            if v.startswith("var(--radius-") or v in _RAIO_LIVRE:
                continue
            achados.append((n, v))
    return achados


def contem(path: Path, trecho: str) -> bool:
    return trecho in path.read_text(encoding="utf-8")


def caminho(rel: str) -> Path:
    return RAIZ / rel
