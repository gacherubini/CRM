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


# Unico vocabulario que o app.css pode declarar por conta propria: escala de
# layout. Ritmo e densidade de painel nao sao marca, entao nao vao para o
# canonico; mas os dois paineis compartilham o mesmo shell e nao podem divergir.
LAYOUT_PERMITIDO = {
    "--space-1", "--space-2", "--space-3", "--space-4", "--space-5",
    "--space-6", "--space-7", "--space-8", "--space-9",
    "--text-xs", "--text-sm", "--text-base", "--text-lg", "--text-xl",
    "--text-display-sm", "--text-display", "--text-metric",
    "--gutter", "--page-inline",
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_root_so_declara_escala_de_layout(rel):
    sobrando = sorted(variaveis_do_root(caminho(rel)) - LAYOUT_PERMITIDO)
    assert not sobrando, f"{rel} declara fora do vocabulario de layout: {sobrando}"


def test_escala_de_layout_identica_entre_os_dois_paineis():
    """Loja e Control tem o mesmo shell. Se o ritmo divergir, as duas telas
    equivalentes deixam de parecer o mesmo produto."""
    a = load_tokens(caminho(PAINEIS[0]))["light"]
    b = load_tokens(caminho(PAINEIS[1]))["light"]
    diferentes = sorted(k for k in set(a) & set(b) if a[k].strip() != b[k].strip())
    assert set(a) == set(b), f"conjuntos diferentes: {set(a) ^ set(b)}"
    assert not diferentes, f"mesmo nome, valor diferente: {diferentes}"


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("morto", ["--accent", "--accent-soft"])
def test_acento_preto_do_sistema_antigo_nao_volta(rel, morto):
    """O preto deixou de ser acento quando o verde entrou, em 08/08."""
    assert usos_de_var(caminho(rel), morto) == 0, f"{rel} ainda usa var({morto})"


# Uma secao por peca de interface, na ordem do arquivo. Cada tarefa de peca
# escreve dentro da sua: e isso que impede a regra de uma peca de nascer a
# 1.500 linhas da outra regra da mesma peca.
# Teto de border-radius literais por arquivo. So desce: cada tarefa de peca
# tokeniza os raios da peca dela e baixa o numero aqui. A Tarefa 14 zera.
# O sistema tem tres raios (3/8/12); qualquer quarto valor e um sistema
# paralelo nascendo.
TETO_RAIOS = {
    "portal-gestao/app/static/css/app.css": 49,
    "revy-trafego/app/static/css/app.css": 44,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_teto_de_raios_literais(rel):
    achados = raios_literais(caminho(rel))
    assert len(achados) <= TETO_RAIOS[rel], (
        f"{rel}: {len(achados)} raios literais, teto {TETO_RAIOS[rel]}. "
        f"Primeiros: {achados[:8]}"
    )


SECOES = [
    "Botao",
    "Campo e formulario",
    "Estado",
    "Painel e card",
    "Tabela e lista",
    "Numero e grafico",
    "Navegacao e shell",
    "Alerta, faixa e vazio",
    "Autenticacao",
]


@pytest.mark.parametrize("rel", PAINEIS)
def test_camada_do_fim_foi_dissolvida(rel):
    """Enquanto ela existir, cada peca tem duas regras disputando o seletor."""
    assert not contem(caminho(rel), "Camada Revy 2026"), (
        f"{rel} ainda tem a camada de sobrescritas no fim do arquivo"
    )


@pytest.mark.parametrize("rel", PAINEIS)
def test_arquivo_tem_uma_secao_por_peca(rel):
    """As tarefas seguintes escrevem dentro destas secoes; sem elas, cada
    correcao volta a virar apendice no fim do arquivo."""
    css = caminho(rel).read_text(encoding="utf-8")
    faltando = [s for s in SECOES if f"=== {s} ===" not in css]
    assert not faltando, f"{rel} sem secao para: {faltando}"


@pytest.mark.parametrize("rel", PAINEIS)
def test_secoes_estao_na_ordem_declarada(rel):
    """Os dois paineis compartilham o shell: se a ordem divergir, a mesma peca
    fica em lugar diferente nos dois arquivos e a busca deixa de valer."""
    css = caminho(rel).read_text(encoding="utf-8")
    posicoes = [css.index(f"=== {s} ===") for s in SECOES]
    assert posicoes == sorted(posicoes), f"{rel} tem secoes fora de ordem"
