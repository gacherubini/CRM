"""A tela de WhatsApp da Loja opera o modo que o Control gravou (spec §5.8).

Modo 1 (Baileys + grupo): QR, vários números, grupo do estoque.
Modo 2 (central Cloud): sem QR, sem grupo; número central + fila de vendedores.
O modo é 1 XOR 2 e chega pela projeção do Control (`whatsapp_modo`).
"""
from conftest import login, seed_whatsapp_modo

from app.loja.navigation import build_nav, flatten_nav
from app.loja.types import EntitlementState, StoreContext
from app.loja.whatsapp_canais import montar_canais_view
from app.loja.whatsapp_modo import MODO_BAILEYS, MODO_CLOUD, modo_da_loja

TELA = "/app/loja/whatsapp"
TELA_FILA = "/app/loja/whatsapp/fila"
TELA_DECIDIR = "/app/loja/whatsapp/conectar"


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


def _projetar_modo(db, modo, loja_slug="loja-teste"):
    seed_whatsapp_modo(db, modo, loja_slug=loja_slug)


def _store(roles=("dono",), slug="loja-teste"):
    return StoreContext(loja_slug=slug, roles=frozenset(roles), loja_state="ativa")


def _ents(slug="loja-teste"):
    return EntitlementState(
        loja_slug=slug,
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
    )


def _canal_evolution():
    return {
        "id": "c1",
        "e164_or_label": "linha 1",
        "evolution_instance": "i1",
        "ativo": True,
        "estado": "conectado",
    }


# --- Fonte do modo -----------------------------------------------------------


def test_sem_projecao_a_loja_opera_o_modo_1():
    """Legado é o default: loja sem envelope do Control segue no Baileys."""
    from app.db import SessionLocal

    sessao = SessionLocal()
    try:
        assert modo_da_loja(sessao, "loja-sem-projecao") == MODO_BAILEYS
    finally:
        sessao.close()


def test_projecao_do_control_define_o_modo_2(db):
    _projetar_modo(db, 2, loja_slug="loja-cloud")
    assert modo_da_loja(db, "loja-cloud") == MODO_CLOUD


# --- Read-model dos canais ---------------------------------------------------


def test_modo_1_mantem_qr_grupo_e_adicionar_numero():
    view = montar_canais_view([_canal_evolution()], modo=MODO_BAILEYS)
    assert view.modo == MODO_BAILEYS
    assert view.pode_adicionar is True
    assert view.baileys is True
    # O convite para a nuvem é do Modo 2: no Modo 1 nem aparece.
    assert view.mostrar_link_conectar is False


def test_modo_2_nao_oferece_qr_nem_grupo_do_estoque():
    view = montar_canais_view([_canal_evolution()], modo=MODO_CLOUD)
    assert view.pode_adicionar is False
    assert view.baileys is False
    canal = view.canais[0]
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is False
    assert canal.pode_marcar_principal_estoque is False


def test_modo_2_convida_a_conectar_a_central_enquanto_nao_ha_canal_cloud():
    view = montar_canais_view([], modo=MODO_CLOUD)
    assert view.mostrar_link_conectar is True


def test_modo_2_com_canal_cloud_nao_convida_de_novo():
    view = montar_canais_view(
        [{"id": "c9", "e164_or_label": "central", "ativo": True,
          "estado": "cloud_ativo", "waba_id": "w1"}],
        modo=MODO_CLOUD,
    )
    assert view.mostrar_link_conectar is False


# --- Menu --------------------------------------------------------------------


def test_menu_do_modo_1_tem_grupo_do_estoque_e_nao_tem_fila():
    sections = build_nav(
        _store(), _ents(), whatsapp_enabled=True, whatsapp_modo=MODO_BAILEYS
    )
    labels = [i.label for i in flatten_nav(sections)]
    assert "Grupo do estoque" in labels
    assert "Fila de atendimento" not in labels


def test_menu_do_modo_2_tem_fila_e_nao_tem_grupo_do_estoque():
    sections = build_nav(
        _store(), _ents(), whatsapp_enabled=True, whatsapp_modo=MODO_CLOUD
    )
    labels = [i.label for i in flatten_nav(sections)]
    assert "Fila de atendimento" in labels
    assert "Grupo do estoque" not in labels


# --- Gate de backend (não só menu) -------------------------------------------


def test_fila_nao_abre_no_modo_1(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get(TELA_FILA, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == TELA


def test_fila_abre_no_modo_2(client, db, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    r = client.get(TELA_FILA, follow_redirects=False)
    assert r.status_code == 200


def test_tela_de_decidir_nao_abre_no_modo_1(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get(TELA_DECIDIR, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == TELA


def test_modo_2_nao_cadastra_numero_por_qr(client, chatbot_fake, db, monkeypatch):
    """O número do Modo 2 vem da janela da Meta, não de um label + QR."""
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    from conftest import csrf_da_resposta

    csrf = csrf_da_resposta(client.get(TELA))
    antes = len(chatbot_fake.canais)
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"label": "linha nova", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert len(chatbot_fake.canais) == antes


def test_fila_nao_aceita_cadastro_no_modo_1(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    from conftest import csrf_da_resposta

    csrf = csrf_da_resposta(client.get(TELA))
    r = client.post(
        TELA_FILA,
        data={"usuario_id": "x", "telefone": "5511999990000", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == TELA


# --- Shell: o menu renderizado segue o modo da loja --------------------------


def test_menu_renderizado_no_modo_1_nao_traz_fila(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    html = client.get(TELA).text
    assert "Fila de atendimento" not in html
    assert "Grupo do estoque" in html


def test_menu_renderizado_no_modo_2_traz_fila_e_esconde_grupo(
    client, db, monkeypatch
):
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    html = client.get(TELA).text
    assert "Fila de atendimento" in html
    assert "Grupo do estoque" not in html


def test_tela_do_modo_1_fala_de_qr_e_grupo(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    html = client.get(TELA).text
    assert "leia o qr" in html.casefold()
    assert "principal do estoque" in html.casefold()


def test_tela_do_modo_2_nao_fala_de_qr_nem_de_grupo(client, db, monkeypatch):
    """No Modo 2 o número é a central da Meta: sem QR, sem grupo do estoque."""
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    html = client.get(TELA).text
    assert "leia o qr" not in html.casefold()
    assert "principal do estoque" not in html.casefold()


# --- Grupo do estoque: existe só no Modo 1 -----------------------------------


def test_grupo_do_estoque_abre_no_modo_1(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/operacao/numeros", follow_redirects=False)
    assert r.status_code == 200


def test_grupo_do_estoque_nao_abre_no_modo_2(client, chatbot_fake, db, monkeypatch):
    """Modo 2 não passa por grupo: esconder no menu e deixar a URL aberta
    é o mesmo bug do menu que promete tela que não existe."""
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    r = client.get("/app/operacao/numeros", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == TELA


def test_modo_2_ainda_apaga_canal_evolution_que_sobrou(client, chatbot_fake, db, monkeypatch):
    """Migrar de modo não pode deixar número velho preso na lista.

    E apagar é a única saída de quem conectou o número errado na janela da
    Meta: sem canal Cloud a tela volta a convidar a conectar.
    """
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    html = client.get(TELA).text
    assert "/inativar" in html


def test_menu_segue_o_modo_tambem_onde_a_rota_nao_passa_o_db(
    client, chatbot_fake, db, monkeypatch
):
    """O menu é o mesmo em toda página, ou vira dois menus.

    ``/app/leads`` chama ``contexto`` sem ``db``; se o shell só descobrisse o
    modo quando a rota passa sessão, a mesma loja veria Fila numa tela e
    Grupo do estoque na outra.
    """
    _ligar(monkeypatch)
    login(client)
    _projetar_modo(db, 2)
    html = client.get("/app/leads").text
    assert "Fila de atendimento" in html
    assert "Grupo do estoque" not in html


# --- Loja selecionada x loja de origem -------------------------------------


def _trocar_para_loja(client, monkeypatch, slug="loja-teste"):
    """Troca a loja ativa na sessão pelo caminho público (seletor).

    O `select_store_slug` é gabaritado só aqui, no setup: o ator do teste tem
    membership só na loja de origem, e o que está sob teste é a tela — não o
    seletor.
    """
    from app.loja import identity
    from conftest import csrf_da_resposta

    monkeypatch.setattr(identity, "select_store_slug", lambda actor, pedido: slug)
    csrf = csrf_da_resposta(client.get(TELA))
    r = client.post(
        "/app/loja/selecionar",
        data={"loja_slug": slug, "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_tela_usa_a_loja_selecionada_e_nao_a_de_origem(client, db, monkeypatch):
    """Regressão: menu em Modo 2 com corpo em Modo 1.

    A rota calculava o modo por `usuario.loja_slug` (origem do login) em vez
    da loja selecionada na sessão — trocar de loja no seletor não trocava a
    tela, e o convite da Meta sumia.
    """
    _ligar(monkeypatch)
    login(client, email="dono@origem.test", loja_slug="loja-origem")
    _projetar_modo(db, 2, loja_slug="loja-teste")
    _trocar_para_loja(client, monkeypatch)
    html = client.get(TELA).text
    assert "leia o qr" not in html.casefold()
    assert "Conectar o WhatsApp pela Revy" in html


def test_decidir_abre_na_loja_selecionada_mesmo_com_origem_modo_1(
    client, db, monkeypatch
):
    _ligar(monkeypatch)
    login(client, email="dono@origem.test", loja_slug="loja-origem")
    _projetar_modo(db, 2, loja_slug="loja-teste")
    _trocar_para_loja(client, monkeypatch)
    r = client.get(TELA_DECIDIR, follow_redirects=False)
    assert r.status_code == 200


def test_grupo_redireciona_na_loja_selecionada_mesmo_com_origem_modo_1(
    client, chatbot_fake, db, monkeypatch
):
    _ligar(monkeypatch)
    login(client, email="dono@origem.test", loja_slug="loja-origem")
    _projetar_modo(db, 2, loja_slug="loja-teste")
    _trocar_para_loja(client, monkeypatch)
    r = client.get("/app/operacao/numeros", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == TELA
