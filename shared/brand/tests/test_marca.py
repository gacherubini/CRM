"""O logo anterior era <text font-family="Inter">: letra viva, sem contorno.
Mudava de forma conforme a maquina e nao dava para levar a impresso nem ao
Canva. Este teste impede que volte.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tokens import RAIZ

ASSETS = RAIZ / "docs" / "brand" / "assets"

ESPERADOS = [
    "revy-mark.svg",
    "revy-mark-reverse.svg",
    "revy-wordmark.svg",
    "revy-signature.svg",
    "revy-signature-reverse.svg",
    "favicon.svg",
]


@pytest.mark.parametrize("nome", ESPERADOS)
def test_arquivo_existe(nome):
    assert (ASSETS / nome).is_file()


@pytest.mark.parametrize("nome", ESPERADOS)
def test_sem_texto_vivo(nome):
    svg = (ASSETS / nome).read_text(encoding="utf-8")
    assert "<text" not in svg, f"{nome} tem <text>: nao e contorno"
    assert "font-family" not in svg, f"{nome} depende de fonte instalada"


def test_simbolo_e_preto():
    svg = (ASSETS / "revy-mark.svg").read_text(encoding="utf-8")
    assert "#1b1b1b" in svg
    assert "#1f4d3a" not in svg, "o simbolo nao e verde"


def test_reversa_tem_fio_de_contraste():
    """Quadrado preto sobre sidebar #161616 sumiria sem o fio."""
    svg = (ASSETS / "revy-mark-reverse.svg").read_text(encoding="utf-8")
    assert "#000000" in svg
    assert "rgba(255,255,255,.16)" in svg
