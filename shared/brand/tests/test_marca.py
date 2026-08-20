"""O logo anterior era <text font-family="Inter">: letra viva, sem contorno.
Mudava de forma conforme a maquina e nao dava para levar a impresso nem ao
Canva. Este teste impede que volte.

Desde 20/08/2026 a marca e a do kit: duas barras inclinadas mais a palavra em
Chivo 900. Os arquivos moraram em docs/brand/assets ate a pasta docs/ ser
reorganizada; ficaram orfaos e o teste passou semanas vermelho. Agora moram ao
lado de quem os gera.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tokens import RAIZ

ASSETS = RAIZ / "shared" / "brand" / "assets"

# Herdam a cor de quem os inclui: e assim que a marca fica tinta no tema claro
# e branca no escuro sem uma regra de CSS por tema.
VIVOS = [
    "revy-bars.svg",
    "revy-icon.svg",
    "revy-wordmark.svg",
    "revy-signature.svg",
]

# Cor cravada de proposito: vao para fora da nossa folha de estilo (favicon do
# navegador, icone de app, <img> do site) e la nao existe currentColor.
FIXOS = [
    "revy-icon-tinta.svg",
    "revy-icon-branco.svg",
    "revy-signature-tinta.svg",
    "revy-signature-branca.svg",
    "favicon.svg",
    "icone-app.svg",
]

ESPERADOS = VIVOS + FIXOS


@pytest.mark.parametrize("nome", ESPERADOS)
def test_arquivo_existe(nome):
    assert (ASSETS / nome).is_file()


@pytest.mark.parametrize("nome", ESPERADOS)
def test_sem_texto_vivo(nome):
    svg = (ASSETS / nome).read_text(encoding="utf-8")
    assert "<text" not in svg, f"{nome} tem <text>: nao e contorno"
    assert "font-family" not in svg, f"{nome} depende de fonte instalada"


@pytest.mark.parametrize("nome", VIVOS)
def test_marca_viva_herda_a_cor(nome):
    svg = (ASSETS / nome).read_text(encoding="utf-8")
    assert "currentColor" in svg, f"{nome} precisa herdar a cor de quem o inclui"
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", svg), f"{nome} crava cor"


@pytest.mark.parametrize("nome", VIVOS)
def test_marca_viva_nao_tem_tamanho_proprio(nome):
    """Quem dimensiona e o CSS. width/height no SVG venceria o `height: .811em`."""
    svg = (ASSETS / nome).read_text(encoding="utf-8")
    assert not re.search(r"<svg[^>]*\swidth=", svg), f"{nome} crava width"
    assert not re.search(r"<svg[^>]*\sheight=", svg), f"{nome} crava height"


def test_barras_sao_duas():
    svg = (ASSETS / "revy-bars.svg").read_text(encoding="utf-8")
    assert svg.count("<path") == 2, "o simbolo e duas barras — nem uma, nem tres"


def test_simbolo_e_preto():
    svg = (ASSETS / "revy-icon-tinta.svg").read_text(encoding="utf-8")
    assert "#1b1b1b" in svg
    assert "#1f4d3a" not in svg, "o simbolo nao e verde"


def test_favicon_e_r_branco_no_quadrado_de_tinta():
    """O favicon vive fora da pagina: sobre a aba clara ou escura do navegador,
    so o quadrado de tinta garante que o R apareca."""
    svg = (ASSETS / "favicon.svg").read_text(encoding="utf-8")
    assert "#1b1b1b" in svg, "falta o quadrado de tinta"
    assert "#ffffff" in svg, "falta o R branco"
    assert "rect" in svg


def test_icone_de_app_tem_cantos_arredondados():
    svg = (ASSETS / "icone-app.svg").read_text(encoding="utf-8")
    assert re.search(r'<rect[^>]*\srx="', svg), "icone de app do kit tem canto arredondado"


@pytest.mark.parametrize("nome", ESPERADOS)
def test_viewbox_declarado(nome):
    svg = (ASSETS / nome).read_text(encoding="utf-8")
    assert re.search(r'viewBox="[-\d. ]+"', svg), f"{nome} sem viewBox: nao escala"


def test_quadrado_preto_do_simbolo_antigo_nao_volta():
    """O simbolo anterior era um quadrado rx=9 num viewBox 0 0 40 40 com o R
    vazado a stroke. O kit o aposentou; nenhum arquivo deve reintroduzi-lo."""
    for nome in ESPERADOS:
        svg = (ASSETS / nome).read_text(encoding="utf-8")
        assert 'viewBox="0 0 40 40"' not in svg, f"{nome} voltou ao simbolo antigo"
        assert "stroke-linejoin" not in svg, f"{nome} desenha a marca a stroke, nao em contorno"


from sync_marca import divergentes  # noqa: E402


def test_copias_em_dia():
    """A marca vive em quatro produtos. O canonico e shared/brand/assets;
    `python shared/brand/sync_marca.py` distribui."""
    fora = divergentes()
    assert not fora, "copias divergentes do canonico: " + ", ".join(str(p) for p in fora)
