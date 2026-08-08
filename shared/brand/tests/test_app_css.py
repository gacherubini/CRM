"""Guardas da varredura de marca.

O app.css de cada painel e carregado DEPOIS do revy-tokens.css. Se ele reabrir
:root e redeclarar um token canonico, o canonico deixa de pintar e a fonte
unica vira decoracao. Foi assim que o ambar do modo escuro divergiu sem que
ninguem visse. Estes testes existem para que isso quebre aqui.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from css_audit import PAINEIS, caminho, contem, raios_literais, usos_de_var, variaveis_do_root
from tokens import CANONICAL, RAIZ, load_tokens

# Apelidos genericos herdados do sistema anterior. Existiam so para o app.css
# antigo continuar funcionando. A Tarefa 14 os aposenta do canonico.
APELIDOS_APOSENTADOS = ("--green", "--amber", "--red", "--online", "--radius")


def test_canonico_nao_carrega_mais_apelido_generico():
    """Eles existiam so para o app.css antigo continuar funcionando. Enquanto
    estiverem la, uma regra nova pode nascer usando --green sem que ninguem
    saiba se aquilo e sucesso, estado de registro ou verde de marca."""
    declarados = set(load_tokens(CANONICAL)["light"])
    sobrando = sorted(set(APELIDOS_APOSENTADOS) & declarados)
    assert not sobrando, f"o canonico ainda declara: {sobrando}"


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


@pytest.mark.parametrize("rel", PAINEIS)
def test_dado_tecnico_usa_a_fonte_mono(rel):
    """Placa, telefone e ID sao para conferir caractere a caractere; em fonte
    proporcional o 0/O e o 1/l se confundem."""
    assert usos_de_var(caminho(rel), "--font-data") > 0, (
        f"{rel} nao usa --font-data em lugar nenhum"
    )


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("token", ["--ok", "--warn", "--danger"])
def test_resultado_de_operacao_usa_token_semantico(rel, token):
    """--ok/--warn/--danger dizem o que aconteceu; --green/--amber/--red so
    diziam a cor. Sem o nome semantico, ninguem sabe se o verde e 'conectou'
    ou 'e da marca'."""
    assert usos_de_var(caminho(rel), token) > 0, f"{rel} nao usa var({token})"


def test_whatsapp_usa_token_semantico_na_loja():
    """--whatsapp e o verde do canal (selo Conectado, botao Enviar do
    atendimento) e so existe na Loja. O Control nunca teve elemento com essa
    cor — exigir o token la seria inventar UI so pra fazer o teste passar,
    nao corrigir uma lacuna real. Fica de fora de
    test_resultado_de_operacao_usa_token_semantico de proposito: aquele e
    parametrizado nos dois paineis, este e Loja-only."""
    assert usos_de_var(caminho(PAINEIS[0]), "--whatsapp") > 0, (
        f"{PAINEIS[0]} nao usa var(--whatsapp)"
    )


# Uma secao por peca de interface, na ordem do arquivo. Cada tarefa de peca
# escreve dentro da sua: e isso que impede a regra de uma peca de nascer a
# 1.500 linhas da outra regra da mesma peca.

# Barra fina: a ponta arredondada e geometria da barra, nao raio de caixa.
# Duas excecoes nominais e documentadas — nao e categoria aberta.
EXCECOES_DE_RAIO = ("roas-bar", "revy-onboarding__progress")


def _raios_relevantes(rel):
    """Raios literais, menos os das barras finas isentas."""
    linhas = caminho(rel).read_text(encoding="utf-8").split("\n")
    return [
        (n, v) for n, v in raios_literais(caminho(rel))
        if not any(e in "\n".join(linhas[max(0, n - 4):n]) for e in EXCECOES_DE_RAIO)
    ]


@pytest.mark.parametrize("rel", PAINEIS)
def test_nenhum_raio_fora_do_sistema(rel):
    """O sistema tem tres raios: 3px controle, 8px menu, 12px superficie.
    Um quarto valor e um sistema paralelo nascendo."""
    achados = _raios_relevantes(rel)
    assert not achados, f"{rel} tem raio fora do sistema: {achados}"


@pytest.mark.parametrize("rel", PAINEIS)
def test_item_de_menu_usa_o_raio_de_navegacao(rel):
    """Nao basta --radius-nav aparecer em algum lugar do arquivo: isso deixa
    passar muda uma contingencia como a da Tarefa 13 (barra de tema do login
    virou --radius-ctl, encolhendo o canto de 8px para 3px). A barra de tema
    do login e item de navegacao — o seletor especifico tem que usar o raio
    certo."""
    css = caminho(rel).read_text(encoding="utf-8")
    assert "border-radius: var(--radius-nav)" in css, (
        f"{rel} nao usa --radius-nav em item de menu"
    )
    bloco = re.search(r"\.login-theme-bar \.theme-toggle\s*\{[^}]*\}", css)
    assert bloco, f"{rel}: bloco .login-theme-bar .theme-toggle nao encontrado"
    assert "border-radius: var(--radius-nav)" in bloco.group(0), (
        f"{rel}: .login-theme-bar .theme-toggle nao usa --radius-nav"
    )


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("apelido", APELIDOS_APOSENTADOS)
def test_apelido_generico_nao_volta(rel, apelido):
    assert usos_de_var(caminho(rel), apelido) == 0, f"{rel} voltou a usar {apelido}"


# Numero que muda a cada refresh nao pode dancar de largura: sem tabular-nums,
# a coluna de valores treme quando o digito 1 entra ou sai.
MINIMO_TABULAR = {
    "portal-gestao/app/static/css/app.css": 12,
    "revy-trafego/app/static/css/app.css": 5,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_numero_e_tabular(rel):
    css = caminho(rel).read_text(encoding="utf-8")
    assert css.count("tabular-nums") >= MINIMO_TABULAR[rel], (
        f"{rel}: {css.count('tabular-nums')} usos, minimo {MINIMO_TABULAR[rel]}"
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


# Cor em template so se justifica no anti-flash: o <script> que aplica o tema
# antes de o CSS carregar, para a tela nao piscar branco. Sao cinco arquivos, e
# os valores tem de bater com o canonico — se divergirem, a tela pisca de uma
# cor para a outra.
TEMPLATES_COM_ANTI_FLASH = {
    "base.html",
    "login.html",
    "convite_aceitar.html",
    "senha_esqueci.html",
    "senha_redefinir.html",
}

HEX_DO_ANTI_FLASH = {"#f9f9f9", "#0a0a0a", "#ffffff", "#1b1b1b", "#f5f5f5", "#111111"}

TEMPLATES = ["portal-gestao/app/templates", "revy-trafego/app/templates"]


def _templates():
    for raiz in TEMPLATES:
        for p in sorted((RAIZ / raiz).rglob("*.html")):
            yield p.relative_to(RAIZ).as_posix(), p


@pytest.mark.parametrize("rel,path", list(_templates()), ids=lambda x: x if isinstance(x, str) else "")
def test_template_nao_carrega_cor_propria(rel, path):
    achados = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", path.read_text(encoding="utf-8"))}
    if not achados:
        return
    permitido = HEX_DO_ANTI_FLASH if path.name in TEMPLATES_COM_ANTI_FLASH else set()
    fora = sorted(achados - permitido)
    assert not fora, (
        f"{rel} tem cor propria: {fora}. Cor vem de token no app.css; "
        f"so os cinco templates de anti-flash podem citar hex, e so os canonicos."
    )
