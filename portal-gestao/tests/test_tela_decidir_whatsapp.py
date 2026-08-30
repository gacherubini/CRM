"""A tela de decisao do WhatsApp na nuvem (Modo 2).

Ela existe para que ninguem perca o historico do WhatsApp sem ter entendido.
Usar o numero que a loja ja anuncia e a unica escolha irreversivel do fluxo:
o historico do celular fica para tras e aquele numero vira bot-only.

Flags lidas em runtime via env (Settings e dataclass frozen — snapshot de boot).
"""
from app.clients.chatbot import ChatbotIndisponivel, OnboardingFalhou
from conftest import csrf_da_resposta, login

TELA = "/app/loja/whatsapp/conectar"


def _ligar(monkeypatch, whatsapp="1", shell="1"):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", shell)
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", whatsapp)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


# --- Gates -------------------------------------------------------------------


def test_flag_off_esconde_a_tela(client, monkeypatch):
    _ligar(monkeypatch, whatsapp="0")
    login(client)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"


def test_shell_off_esconde_a_tela(client, monkeypatch):
    _ligar(monkeypatch, shell="0")
    login(client)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303


def test_sem_login_vai_para_o_login(client, monkeypatch):
    _ligar(monkeypatch)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]


def test_vendedor_nao_entra(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="vendedor@loja.test")
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"] == "/app"


# --- Decisao 9: gerente ve, so o dono conecta --------------------------------


def test_gerente_ve_a_tela(client, monkeypatch):
    """Esconder a tela do gerente foi recusado: ele precisa saber responder
    'por que o WhatsApp ainda nao esta no ar'."""
    _ligar(monkeypatch)
    login(client, papel="gerente", email="gerente@loja.test")
    r = client.get(TELA)
    assert r.status_code == 200


def test_gerente_nao_ve_o_botao_de_conectar(client, monkeypatch):
    """Decisao 9: gerente ve o estado, so o dono conecta. Quem clica precisa ser
    admin do portfolio empresarial na Meta, e gerente normalmente nao e."""
    _ligar(monkeypatch)
    login(client, papel="gerente", email="gerente@loja.test")
    r = client.get(TELA)
    assert 'id="conectar-whatsapp"' not in r.text


def test_gerente_le_por_que_nao_pode_conectar(client, monkeypatch):
    """Sem explicacao, a ausencia do botao vira chamado de suporte.

    A frase inteira, e nao a palavra "dono" solta: o topo da tela ja mostra o
    cargo de quem esta logado.
    """
    _ligar(monkeypatch)
    login(client, papel="gerente", email="gerente@loja.test")
    texto = client.get(TELA).text.lower()
    assert "só o dono da loja" in texto


def test_dono_ve_o_botao(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    r = client.get(TELA)
    assert r.status_code == 200
    assert 'id="conectar-whatsapp"' in r.text


# --- O texto que torna a decisao informada -----------------------------------


def test_a_tela_diz_o_que_se_perde(client, monkeypatch):
    """O trade-off. Sem ele a decisao nao e informada.

    Frases inteiras porque as palavras soltas sobrevivem em qualquer lugar da
    pagina: "não volta" ja aparece na chamada do topo e "histórico" no caminho
    do numero novo — a perda tem de estar escrita onde ela acontece.
    """
    _ligar(monkeypatch)
    login(client)
    texto = client.get(TELA).text.lower()

    assert "histórico" in texto
    assert "fica para trás" in texto, "tem de dizer que o histórico se perde"
    assert "não volta" in texto


def test_a_tela_avisa_do_admin_antes_do_popup(client, monkeypatch):
    """Descobrir que nao e admin do portfolio dentro do popup da Meta e o pior
    lugar possivel para descobrir. Idem cartao e chip."""
    _ligar(monkeypatch)
    login(client)
    texto = client.get(TELA).text.lower()

    assert "admin do portfólio" in texto, "tem de avisar do admin do portfólio"
    assert "cartão de crédito" in texto
    assert "chip do número" in texto


def test_a_tela_oferece_as_duas_saidas(client, monkeypatch):
    """Numero novo (guarda o celular) x numero anunciado (perde o historico)."""
    _ligar(monkeypatch)
    login(client)
    texto = client.get(TELA).text.lower()

    assert "um número novo" in texto
    assert "que você já anuncia" in texto


# --- O popup da Meta: o botao acende sozinho quando o App Review sair --------
#
# O `config_id` so existe depois de o App Review dar Advanced Access ao app.
# Ate la tudo isto fica no ar sem quebrar nada: sem as duas variaveis o botao
# continua desabilitado e a tela segue dizendo que a janela esta em liberacao.
#
# ATENCAO: pytest NAO roda o popup. O que estes testes provam e o lado servidor
# (o gate, as frases, o botao aceso/apagado). O JS so se verifica no navegador.


def _config_meta(monkeypatch, app_id="1370395535203964", config_id="998877"):
    monkeypatch.setenv("PORTAL_META_APP_ID", app_id)
    monkeypatch.setenv("PORTAL_META_CONFIG_ID", config_id)


def _sem_config_meta(monkeypatch):
    monkeypatch.delenv("PORTAL_META_APP_ID", raising=False)
    monkeypatch.delenv("PORTAL_META_CONFIG_ID", raising=False)


def _botao(texto):
    """A tag do botao inteira, para olhar o `disabled` dentro dela."""
    inicio = texto.index('id="conectar-whatsapp"')
    return texto[texto.rindex("<button", 0, inicio) : texto.index(">", inicio) + 1]


def test_sem_config_o_botao_fica_desabilitado(client, monkeypatch):
    """Enquanto o App Review nao sai, o botao nao acende — e a tela diz por que."""
    _ligar(monkeypatch)
    _sem_config_meta(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    texto = client.get(TELA).text

    assert "disabled" in _botao(texto)
    assert "em liberação com a Meta" in texto


def test_so_o_app_id_nao_acende_o_botao(client, monkeypatch):
    """Meio configurado e pior que nada: o popup abriria e a Meta recusaria
    sem dizer por que."""
    _ligar(monkeypatch)
    _config_meta(monkeypatch, config_id="")
    login(client, papel="dono", email="dono@loja.test")
    texto = client.get(TELA).text

    assert "disabled" in _botao(texto)
    assert "em liberação com a Meta" in texto


def test_so_o_config_id_nao_acende_o_botao(client, monkeypatch):
    _ligar(monkeypatch)
    _config_meta(monkeypatch, app_id="")
    login(client, papel="dono", email="dono@loja.test")
    texto = client.get(TELA).text

    assert "disabled" in _botao(texto)


def test_com_as_duas_variaveis_o_botao_acende(client, monkeypatch):
    """O dia em que o App Review sair: setar as duas variaveis basta, sem
    tocar em codigo."""
    _ligar(monkeypatch)
    _config_meta(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    texto = client.get(TELA).text

    assert "disabled" not in _botao(texto)
    assert "em liberação com a Meta" not in texto


def test_o_popup_recebe_app_id_e_config_id(client, monkeypatch):
    """Os dois vao para o navegador: nao sao segredo, e sem eles o FB.login
    nao abre a variacao de Embedded Signup."""
    _ligar(monkeypatch)
    _config_meta(monkeypatch, app_id="1370395535203964", config_id="998877")
    login(client, papel="dono", email="dono@loja.test")
    texto = client.get(TELA).text

    assert "1370395535203964" in texto
    assert "998877" in texto
    assert "config_id" in texto


def test_gerente_nao_ganha_o_botao_nem_com_a_config_pronta(client, monkeypatch):
    """Decisao 9 nao depende do App Review."""
    _ligar(monkeypatch)
    _config_meta(monkeypatch)
    login(client, papel="gerente", email="gerente@loja.test")

    assert 'id="conectar-whatsapp"' not in client.get(TELA).text


def test_a_tela_tem_saida_para_o_popup_que_fecha_no_meio(client, monkeypatch):
    """O caso mais comum de falha — numero ainda ativo no aplicativo — morre
    DENTRO do popup e pode nao gerar evento nenhum. A tela nao pode ficar em
    espera infinita."""
    _ligar(monkeypatch)
    _config_meta(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    texto = client.get(TELA).text

    assert 'id="conectar-sem-retorno"' in texto
    assert "ainda estar ativo no aplicativo" in texto


# --- POST /app/loja/whatsapp/conectar ----------------------------------------

CAMPOS = {
    "code": "AQD-code-de-uso-unico",
    "waba_id": "111",
    "phone_number_id": "222",
    "business_id": "333",
}


def _conectar(client, monkeypatch, chatbot_fake, papel="dono", campos=None, csrf=True):
    _ligar(monkeypatch)
    _config_meta(monkeypatch)
    login(client, papel=papel, email=f"{papel}@loja.test")
    pagina = client.get(TELA)
    dados = dict(CAMPOS if campos is None else campos)
    if csrf:
        dados["csrf"] = csrf_da_resposta(pagina)
    return client.post(TELA, data=dados, follow_redirects=False)


def _mensagem_na_tela(client):
    """A mensagem sai da sessao no proximo GET da tela de canais."""
    return client.get("/app/loja/whatsapp").text


def test_dono_conecta_e_o_chatbot_recebe_os_quatro_campos(
    client, monkeypatch, chatbot_fake
):
    recebido = {}
    chatbot_fake.conectar_whatsapp_cloud = (
        lambda **kw: recebido.update(kw) or {"estado": "cloud_pendente"}
    )
    r = _conectar(client, monkeypatch, chatbot_fake)

    assert r.status_code == 303
    assert recebido == CAMPOS


def test_gerente_nao_conecta_mesmo_postando_na_mao(
    client, monkeypatch, chatbot_fake
):
    """Decisao 9: `_guarda` deixa o gerente passar (ROLES_GESTAO). O gate de
    dono no POST e o que impede o form de ser postado por fora da tela."""
    chamado = []
    chatbot_fake.conectar_whatsapp_cloud = lambda **kw: chamado.append(kw)
    r = _conectar(client, monkeypatch, chatbot_fake, papel="gerente")

    assert r.headers["location"] == "/app"
    assert chamado == []


def test_sem_csrf_nao_conecta(client, monkeypatch, chatbot_fake):
    chamado = []
    chatbot_fake.conectar_whatsapp_cloud = lambda **kw: chamado.append(kw)
    r = _conectar(client, monkeypatch, chatbot_fake, csrf=False)

    assert r.headers["location"] == "/app"
    assert chamado == []


def test_popup_incompleto_nao_queima_o_code(client, monkeypatch, chatbot_fake):
    """O `code` e de uso unico: mandar meia conexao ao chatbot o queimaria sem
    conectar nada. E a tela precisa dizer o motivo comum, nao 'erro'."""
    chamado = []
    chatbot_fake.conectar_whatsapp_cloud = lambda **kw: chamado.append(kw)
    r = _conectar(
        client, monkeypatch, chatbot_fake, campos={"code": CAMPOS["code"]}
    )

    assert r.headers["location"] == "/app/loja/whatsapp"
    assert chamado == []
    assert "ainda estar ativo no aplicativo" in _mensagem_na_tela(client)


def test_elo_que_parou_vira_frase_e_nao_indisponibilidade(
    client, monkeypatch, chatbot_fake
):
    """`OnboardingFalhou` e `ChatbotIndisponivel` pedem acoes opostas do
    lojista: uma e problema do numero, a outra e nossa. Nao podem virar a
    mesma frase."""
    def falhar(**kw):
        raise OnboardingFalhou("a Meta recusou o registro do número", elo=3)

    chatbot_fake.conectar_whatsapp_cloud = falhar
    _conectar(client, monkeypatch, chatbot_fake)
    texto = _mensagem_na_tela(client)

    assert "a Meta recusou o registro do número" in texto
    assert "tente de novo em instantes" not in texto


def test_chatbot_fora_do_ar_manda_esperar_e_nao_refazer_a_janela(
    client, monkeypatch, chatbot_fake
):
    """A janela da Meta ja terminou. Refaze-la queimaria o code de novo e
    poderia duplicar o registro."""
    def cair(**kw):
        raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")

    chatbot_fake.conectar_whatsapp_cloud = cair
    _conectar(client, monkeypatch, chatbot_fake)
    texto = _mensagem_na_tela(client)

    assert "Não refaça a janela" in texto
    assert "parou no caminho da Meta" not in texto
