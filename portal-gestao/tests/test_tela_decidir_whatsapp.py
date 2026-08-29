"""A tela de decisao do WhatsApp na nuvem (Modo 2).

Ela existe para que ninguem perca o historico do WhatsApp sem ter entendido.
Usar o numero que a loja ja anuncia e a unica escolha irreversivel do fluxo:
o historico do celular fica para tras e aquele numero vira bot-only.

Flags lidas em runtime via env (Settings e dataclass frozen — snapshot de boot).
"""
from conftest import login

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
