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
    "portal-gestao/app/static/css/app.css": 39,
    "revy-trafego/app/static/css/app.css": 34,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_teto_de_raios_literais(rel):
    achados = raios_literais(caminho(rel))
    assert len(achados) <= TETO_RAIOS[rel], (
        f"{rel}: {len(achados)} raios literais, teto {TETO_RAIOS[rel]}. "
        f"Primeiros: {achados[:8]}"
    )


# Apelidos genericos herdados do sistema anterior. Cada tarefa migra os seus
# para o nome semantico e baixa o teto; a Tarefa 14 zera e os remove do
# canonico. Enquanto .status pintar por --green, "Proposta" e "Ganho" saem da
# mesma variavel e a regra "o acento nunca e status" nao tem como valer.
APELIDOS = ("--green", "--amber", "--red", "--online")

TETO_APELIDOS = {
    "portal-gestao/app/static/css/app.css": 41,
    "revy-trafego/app/static/css/app.css": 46,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_teto_de_apelidos_genericos(rel):
    total = sum(usos_de_var(caminho(rel), a) for a in APELIDOS)
    assert total <= TETO_APELIDOS[rel], (
        f"{rel}: {total} usos de apelido generico, teto {TETO_APELIDOS[rel]}"
    )


# Terminais presentes nos DOIS paineis. `convertido` ficou de fora de proposito:
# o mapa vigente lhe da ponto verde (lead convertido ainda gera trabalho), e o
# mapa veio do enum real. Quem so existe num painel vai em TERMINAIS_PROPRIOS —
# a guarda protege o que existe, nao inventa classe.
TERMINAIS = ("vendido", "perdido", "indisponivel", "suspensa", "encerrada", "inativo")

TERMINAIS_PROPRIOS = {
    # Loja: enum de simulacao (app/web/simulacoes.py:_SIM_STATUS_LABELS).
    "portal-gestao/app/static/css/app.css": ("cancelada", "falhou"),
    # Control: convite de acesso (app/rotulos.py:ROTULO_ACESSO).
    "revy-trafego/app/static/css/app.css": ("revogado", "recusado", "expirado"),
}


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("terminal", TERMINAIS)
def test_estado_terminal_nao_recebe_ponto(rel, terminal):
    """Ganho e marca de conferido; Perdido e texto apagado. O orcamento de
    destaque vai para quem exige acao — um cliente esperando ha tres horas
    importa mais que uma venda fechada semana passada."""
    css = caminho(rel).read_text(encoding="utf-8")
    assert f".status.{terminal}::before" in css, (
        f"{rel}: o estado terminal '{terminal}' nao suprime o ponto"
    )


@pytest.mark.parametrize("rel", PAINEIS)
def test_terminal_proprio_do_painel_tambem_perde_o_ponto(rel):
    css = caminho(rel).read_text(encoding="utf-8")
    faltando = [t for t in TERMINAIS_PROPRIOS[rel] if f".status.{t}::before" not in css]
    assert not faltando, f"{rel}: terminais sem supressao de ponto: {faltando}"


@pytest.mark.parametrize("rel", PAINEIS)
def test_disponivel_e_repouso_nao_ganho(rel):
    """Ate 08/08 `Disponivel` e `Convertido` saiam da mesma variavel: os dois
    eram o mesmo verde na tela. Disponivel e o estado de repouso da maioria dos
    veiculos e nao exige acao — fica neutro e sem ponto."""
    css = caminho(rel).read_text(encoding="utf-8")
    assert ".status.disponivel::before" in css, (
        f"{rel}: 'disponivel' ainda recebe ponto"
    )
    assert ".status.disponivel { color: var(--ink-muted); }" in css, (
        f"{rel}: 'disponivel' nao esta no neutro"
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
