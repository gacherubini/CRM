"""A tela de canais tem de falar do canal Cloud sem mentir.

Hoje ela mostra o nome tecnico cru como rotulo e oferece o botao Conectar do
Modo 1 — que pede QR na Evolution — para um numero que e da Cloud API.
"""
import re

from app.loja.whatsapp_canais import montar_canais_view


def _bruto(estado, **extra):
    base = {
        "id": "c1",
        "e164_or_label": "linha-cloud",
        "evolution_instance": "1227059273831581",
        "estado": estado,
        "ativo": True,
        "principal_estoque": False,
    }
    base.update(extra)
    return base


def test_canal_cloud_nao_mostra_o_nome_tecnico():
    view = montar_canais_view([_bruto("cloud_pendente", waba_id="waba-1")])

    canal = view.canais[0]
    assert canal.rotulo != "cloud_pendente"
    assert "cloud_" not in canal.rotulo


def test_canal_cloud_nao_oferece_o_botao_do_modo_1():
    """O botao chama conectar_canal_whatsapp, que pede QR na Evolution."""
    view = montar_canais_view([_bruto("cloud_pendente", waba_id="waba-1")])

    canal = view.canais[0]
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is False
    assert canal.cloud is True


def test_canal_cloud_ativo_tambem_nao_oferece():
    view = montar_canais_view([_bruto("cloud_ativo", waba_id="waba-1")])

    assert view.canais[0].pode_desconectar is False


def test_os_quatro_estados_cloud_tem_rotulo_proprio():
    """Restrito e banido vem da Meta e nao se conserta clicando: o rotulo tem
    de dizer isso, senao o lojista fica tentando."""
    estados = ["cloud_pendente", "cloud_ativo", "cloud_restrito", "cloud_banido"]
    view = montar_canais_view(
        [_bruto(e, id=f"c{i}", evolution_instance=f"12270592738315{80 + i}",
                waba_id="waba-1")
         for i, e in enumerate(estados)]
    )

    rotulos = [c.rotulo for c in view.canais]
    assert len(set(rotulos)) == 4, f"estados diferentes com o mesmo rotulo: {rotulos}"
    for rotulo in rotulos:
        assert "cloud_" not in rotulo


def test_canal_do_modo_1_nao_muda():
    """Regressao: a loja piloto opera no Modo 1 e nada aqui pode mexer nela."""
    view = montar_canais_view([_bruto("conectado")])

    canal = view.canais[0]
    assert canal.rotulo == "Conectado"
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is True
    assert canal.cloud is False


def test_dois_canais_cloud_continuam_cloud_depois_do_principal_estoque():
    """A loja com mais de um canal e o caso que ninguem testa a mao.

    Quando nenhum canal vem marcado como principal, ``montar_canais_view``
    reconstroi cada ``CanalView`` campo a campo para eleger o primeiro. Se
    ``cloud`` nao for repassado nessa reconstrucao, o canal volta ``cloud=False``
    e a tela oferece de novo o botao de QR — sem nenhum outro teste ficar
    vermelho.
    """
    view = montar_canais_view([
        _bruto("cloud_ativo", id="c1", evolution_instance="111", waba_id="waba-1"),
        _bruto("cloud_pendente", id="c2", evolution_instance="222", waba_id="waba-2"),
    ])

    assert [c.id for c in view.canais] == ["c1", "c2"]
    assert [c.principal_estoque for c in view.canais] == [True, False]
    for canal in view.canais:
        assert canal.cloud is True, f"canal {canal.id} perdeu o cloud na reconstrucao"
        assert canal.pode_conectar is False
        assert canal.pode_desconectar is False


# --- Task 5: em que passo parou e de quem e a vez ---------------------------
#
# A tela de decisao (GET /app/loja/whatsapp/conectar) existe e e testada, mas
# ninguem a alcanca clicando. E, com canal Cloud, esta tela precisa dizer em
# que passo o onboarding parou: "erro" nao e informacao de dono de loja.

CONECTAR = "/app/loja/whatsapp/conectar"
FILA = "/app/loja/whatsapp/fila"
# Copiado do chatbot, nao inventado: chatbot-api/app/meta_onboarding.py:185, o
# erro do elo 3 quando o registro estoura o teto e a Meta bloqueia o numero.
ERRO_CRU_TETO = (
    "a Meta bloqueou novos registros deste número por 72 horas; fale com a Revy"
)
# Um erro qualquer com vocabulario de dentro: a tela nunca ecoa o texto do
# chatbot, seja ele qual for.
ERRO_CRU_TECNICO = "(#133016) re-registration blocked for 72 horas"


def _render(canais):
    """Renderiza o bloco ``content`` da tela real, com um base.html de mentira.

    A view sozinha nao prova nada: campo que o template nao usa nao vira tela, e
    link que o template nao imprime nao leva ninguem a lugar nenhum.
    """
    from pathlib import Path

    from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

    pastas = Path(__file__).resolve().parents[1] / "app" / "templates"
    env = Environment(
        loader=ChoiceLoader([
            DictLoader({"base.html": "{% block content %}{% endblock %}"}),
            FileSystemLoader(str(pastas)),
        ]),
        autoescape=True,
    )
    return env.get_template("loja/whatsapp_canais.html").render(
        view=montar_canais_view(canais),
        csrf="tok",
        qr=None,
        acao_erro=None,
        acao_mensagem=None,
    )


def test_sem_canal_cloud_a_tela_leva_para_a_de_conectar():
    """A tela de decisao nao tem porta: quem so tem Modo 1 nunca a alcanca."""
    view = montar_canais_view([_bruto("conectado")])

    assert view.mostrar_link_conectar is True


def test_loja_sem_nenhum_canal_tambem_leva_para_a_de_conectar():
    view = montar_canais_view([])

    assert view.mostrar_link_conectar is True


def test_com_canal_cloud_a_tela_nao_repete_o_convite():
    """Com canal Cloud, o lugar do estado e esta tela — nao um segundo convite."""
    view = montar_canais_view([
        _bruto("conectado", id="c1"),
        _bruto("cloud_pendente", id="c2", waba_id="waba-1"),
    ])

    assert view.mostrar_link_conectar is False


def test_chatbot_fora_do_ar_nao_convida_a_conectar():
    """Sem a lista nao da para saber se a loja ja tem canal Cloud."""
    view = montar_canais_view(None, erro="chatbot_indisponivel")

    assert view.mostrar_link_conectar is False


def test_a_tela_renderiza_o_link_para_a_de_conectar():
    """Sem <a href> impresso, o campo da view nao leva ninguem a lugar nenhum."""
    html = _render([_bruto("conectado")])

    assert f'href="{CONECTAR}"' in html


def test_com_canal_cloud_a_tela_renderizada_nao_repete_o_convite():
    html = _render([_bruto("cloud_ativo", waba_id="waba-1")])

    assert CONECTAR not in html


def test_erro_no_elo_3_nomeia_o_passo_que_parou():
    view = montar_canais_view([
        _bruto(
            "cloud_pendente",
            waba_id="waba-1",
            onboarding_elo=3,
            onboarding_erro="timeout ao chamar o registro",
        )
    ])

    canal = view.canais[0]
    assert canal.onboarding_falhou is True
    assert canal.onboarding_elo == 3
    assert "registrar o número" in canal.onboarding_texto
    assert canal.pode_tentar_de_novo is True
    assert canal.onboarding_acao_url == CONECTAR


def test_cada_elo_tem_nome_de_dono_de_loja():
    """Cinco passos, cinco frases — e nenhuma com vocabulario de dentro."""
    view = montar_canais_view([
        _bruto(
            "cloud_pendente",
            id=f"c{elo}",
            evolution_instance=str(elo),
            waba_id="waba-1",
            onboarding_elo=elo,
            onboarding_erro="falhou",
        )
        for elo in range(1, 6)
    ])

    textos = [c.onboarding_texto for c in view.canais]
    assert len(set(textos)) == 5, f"passos diferentes com a mesma frase: {textos}"
    for texto in textos:
        assert texto.startswith("Parou ao "), texto
        baixo = texto.casefold()
        # Palavra inteira: "modelo de mensagem" contem "elo" e e frase de dono.
        for tecnico in ("elo", "onboarding", "waba", "token", "webhook", "api"):
            assert not re.search(rf"\b{tecnico}\b", baixo), (
                f"{tecnico!r} vazou para a tela: {texto}"
            )


def test_o_teto_de_tentativas_nao_oferece_clique_que_a_meta_recusa():
    """O chatbot para em 5 tentativas porque a Meta bloqueia por 72 horas."""
    view = montar_canais_view([
        _bruto(
            "cloud_pendente",
            waba_id="waba-1",
            onboarding_elo=3,
            onboarding_erro=ERRO_CRU_TETO,
        )
    ])

    canal = view.canais[0]
    assert canal.onboarding_falhou is True
    assert canal.pode_tentar_de_novo is False
    assert canal.onboarding_acao_url == ""
    assert "Revy" in canal.onboarding_acao
    assert "72 horas" in canal.onboarding_acao


def test_o_texto_cru_do_erro_nao_vai_para_a_tela():
    view = montar_canais_view([
        _bruto(
            "cloud_pendente",
            waba_id="waba-1",
            onboarding_elo=3,
            onboarding_erro=ERRO_CRU_TECNICO,
        )
    ])

    canal = view.canais[0]
    juntos = f"{canal.onboarding_texto} {canal.onboarding_acao}"
    assert "133016" not in juntos
    assert "re-registration" not in juntos


def test_primeiro_passo_sem_erro_diz_que_a_vez_e_do_lojista():
    view = montar_canais_view([
        _bruto("cloud_pendente", waba_id="waba-1", onboarding_elo=1)
    ])

    canal = view.canais[0]
    assert canal.onboarding_falhou is False
    assert "sua vez" in canal.onboarding_texto.casefold()
    assert canal.onboarding_acao_url == CONECTAR


def test_passo_do_meio_sem_erro_diz_que_a_vez_e_da_revy():
    view = montar_canais_view([
        _bruto("cloud_pendente", waba_id="waba-1", onboarding_elo=3)
    ])

    canal = view.canais[0]
    assert canal.onboarding_falhou is False
    assert "Revy" in canal.onboarding_texto
    assert canal.onboarding_acao_url == ""


def test_ultimo_passo_empurra_para_a_fila_que_e_o_unico_acionavel():
    view = montar_canais_view([
        _bruto("cloud_pendente", waba_id="waba-1", onboarding_elo=5)
    ])

    canal = view.canais[0]
    assert canal.onboarding_falhou is False
    assert "liberação da Revy" in canal.onboarding_texto
    assert canal.onboarding_acao_url == FILA
    assert "fila" in canal.onboarding_acao.casefold()


def test_erro_nao_inventa_estado_novo_no_canal():
    """Falhou e estado de tela: no banco o canal continua cloud_pendente."""
    view = montar_canais_view([
        _bruto(
            "cloud_pendente",
            waba_id="waba-1",
            onboarding_elo=2,
            onboarding_erro="deu ruim",
        )
    ])

    canal = view.canais[0]
    assert canal.estado == "cloud_pendente"
    assert "falhou" not in canal.rotulo.casefold()


def test_canal_cloud_no_ar_nao_fala_de_passo_nenhum():
    view = montar_canais_view([
        _bruto("cloud_ativo", waba_id="waba-1", onboarding_elo=5)
    ])

    canal = view.canais[0]
    assert canal.onboarding_texto == ""
    assert canal.onboarding_falhou is False


def test_canal_do_modo_1_nao_ganha_nada_do_onboarding():
    """Regressao: a loja piloto opera no Modo 1 — mesmo que o chatbot mande os
    campos novos, canal de QR nao fala de passo da nuvem."""
    view = montar_canais_view([
        _bruto("conectado", onboarding_elo=3, onboarding_erro="deu ruim")
    ])

    canal = view.canais[0]
    assert canal.onboarding_elo is None
    assert canal.onboarding_texto == ""
    assert canal.onboarding_acao == ""
    assert canal.onboarding_acao_url == ""
    assert canal.onboarding_falhou is False
    assert canal.pode_tentar_de_novo is False


def test_dois_canais_cloud_mantem_o_onboarding_depois_do_principal_estoque():
    """O irmao do teste de cima: eleger o principal reconstroi cada CanalView.

    Campo do onboarding que nao for repassado na reconstrucao some da tela sem
    nenhum outro teste ficar vermelho.
    """
    view = montar_canais_view([
        _bruto("cloud_pendente", id="c1", evolution_instance="111",
               waba_id="waba-1", onboarding_elo=5),
        _bruto("cloud_pendente", id="c2", evolution_instance="222",
               waba_id="waba-2", onboarding_elo=3, onboarding_erro="deu ruim"),
    ])

    primeiro, segundo = view.canais
    assert [primeiro.principal_estoque, segundo.principal_estoque] == [True, False]

    assert primeiro.onboarding_elo == 5
    assert "liberação da Revy" in primeiro.onboarding_texto
    assert primeiro.onboarding_acao_url == FILA
    assert primeiro.onboarding_falhou is False

    assert segundo.onboarding_elo == 3
    assert "registrar o número" in segundo.onboarding_texto
    assert segundo.onboarding_falhou is True
    assert segundo.pode_tentar_de_novo is True
    assert segundo.onboarding_acao_url == CONECTAR


def test_a_tela_renderiza_o_passo_que_parou_e_o_clique_de_tentar():
    html = _render([
        _bruto(
            "cloud_pendente",
            waba_id="waba-1",
            onboarding_elo=3,
            onboarding_erro="timeout ao chamar o registro",
        )
    ])

    assert "Parou ao registrar o n" in html
    assert f'href="{CONECTAR}"' in html
    assert "Tentar de novo" in html


def test_a_tela_renderiza_o_que_falta_e_o_atalho_da_fila():
    html = _render([
        _bruto("cloud_pendente", waba_id="waba-1", onboarding_elo=5)
    ])

    assert "falta a libera" in html
    assert f'href="{FILA}"' in html


def test_no_teto_a_tela_nao_renderiza_clique_nenhum():
    """A prova final do teto: nao basta a view dizer que nao pode — a tela nao
    pode imprimir o link."""
    html = _render([
        _bruto(
            "cloud_pendente",
            waba_id="waba-1",
            onboarding_elo=3,
            onboarding_erro=ERRO_CRU_TETO,
        )
    ])

    assert "Parou ao registrar o n" in html
    assert "72 horas" in html
    assert "Tentar de novo" not in html
    assert CONECTAR not in html
    assert "133016" not in html
    # Nem um link morto: no teto, o unico caminho e falar com a Revy.
    assert "<a " not in html
