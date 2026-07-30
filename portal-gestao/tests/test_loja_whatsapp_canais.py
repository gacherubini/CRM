"""Tela de números de WhatsApp da Loja (Ajustes): gates, ações, QR e auditoria.

Flags lidas em runtime via env (Settings é dataclass frozen — snapshot de boot).
"""
from conftest import csrf_da_resposta, login

from app.clients.chatbot import ChatbotIndisponivel
from app.loja.navigation import build_nav, flatten_nav
from app.loja.types import EntitlementState, StoreContext
from app.loja_operacao_auditoria import DOMINIO_CANAL
from app.models import LojaOperacaoAuditoria

TELA = "/app/loja/whatsapp"


def _ligar(monkeypatch, whatsapp="1", shell="1"):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", shell)
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", whatsapp)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


def _csrf(client):
    return csrf_da_resposta(client.get(TELA))


def _acoes_auditadas(db):
    linhas = (
        db.query(LojaOperacaoAuditoria)
        .filter(LojaOperacaoAuditoria.dominio == DOMINIO_CANAL)
        .all()
    )
    return linhas


# --- Gates -------------------------------------------------------------------


def test_flag_off_esconde_tela(client, monkeypatch):
    _ligar(monkeypatch, whatsapp="0")
    login(client)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"


def test_shell_off_esconde_tela(client, monkeypatch):
    _ligar(monkeypatch, shell="0")
    login(client)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303


def test_vendedor_nao_acessa(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"


def test_sem_login_vai_para_login(client, monkeypatch):
    _ligar(monkeypatch)
    r = client.get(TELA, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_vendedor_nao_escreve_e_nao_audita(client, chatbot_fake, db, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    antes = len(chatbot_fake.canais)
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"csrf": "qualquer", "label": "linha nova"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    assert len(chatbot_fake.canais) == antes
    assert _acoes_auditadas(db) == []


def test_csrf_invalido_nao_cria_canal(client, chatbot_fake, db, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    antes = len(chatbot_fake.canais)
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"csrf": "token-errado", "label": "linha 2"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    assert len(chatbot_fake.canais) == antes
    assert _acoes_auditadas(db) == []


# --- Tela e ações ------------------------------------------------------------


def test_dono_ve_canais_e_no_store(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get(TELA)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    # Rótulos humanos, não estado técnico.
    assert "Conectado" in r.text
    for canal in chatbot_fake.canais:
        assert canal["e164_or_label"] in r.text


def test_dono_adiciona_canal(client, chatbot_fake, db, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    antes = [c["e164_or_label"] for c in chatbot_fake.canais]
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"csrf": _csrf(client), "label": "linha 2"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == TELA
    depois = [c["e164_or_label"] for c in chatbot_fake.canais]
    assert depois == antes + ["linha 2"]
    assert [linha.acao for linha in _acoes_auditadas(db)] == ["criar"]


def test_label_vazio_mostra_erro_e_nao_chama_chatbot(
    client, chatbot_fake, db, monkeypatch
):
    _ligar(monkeypatch)
    login(client)
    antes = len(chatbot_fake.canais)
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"csrf": _csrf(client), "label": "   "},
        follow_redirects=True,
    )
    assert "Informe um nome para o número." in r.text
    assert len(chatbot_fake.canais) == antes
    assert _acoes_auditadas(db) == []


def test_conectar_mostra_qr_e_nao_grava_em_auditoria(
    client, chatbot_fake, db, monkeypatch
):
    _ligar(monkeypatch)
    login(client)
    canal_id = chatbot_fake.registrar_canal_whatsapp("linha 2")["id"]
    r = client.post(
        f"/app/loja/whatsapp/canais/{canal_id}/conectar",
        data={"csrf": _csrf(client)},
        follow_redirects=True,
    )
    assert "QR-FAKE" in r.text
    linhas = _acoes_auditadas(db)
    assert [linha.acao for linha in linhas] == ["conectar"]
    assert all(linha.success for linha in linhas)
    campos = [
        (linha.error_code or "") + (linha.origem or "") + (linha.provedor or "")
        for linha in linhas
    ]
    assert all("QR-FAKE" not in campo for campo in campos)


def test_qr_nao_sobrevive_ao_segundo_get(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    canal_id = chatbot_fake.registrar_canal_whatsapp("linha 2")["id"]
    client.post(
        f"/app/loja/whatsapp/canais/{canal_id}/conectar",
        data={"csrf": _csrf(client)},
        follow_redirects=True,
    )
    segundo = client.get(TELA)
    assert "QR-FAKE" not in segundo.text


def test_qr_grande_nao_vai_para_o_cookie_de_sessao(
    client, chatbot_fake, monkeypatch
):
    """QR real da Evolution tem vários KB; no cookie ele estouraria os ~4 KB.

    O cookie leva só o token opaco — senão o navegador descarta a sessão inteira
    em silêncio e a loja perde o login ao tentar parear.
    """
    _ligar(monkeypatch)
    login(client)
    canal_id = chatbot_fake.canais[0]["id"]
    grande = "R0lGODlh" + ("A" * 6000)
    monkeypatch.setattr(
        chatbot_fake,
        "conectar_canal_whatsapp",
        lambda cid: {"id": cid, "estado": "pendente", "qr_payload": grande},
    )
    r = client.post(
        f"/app/loja/whatsapp/canais/{canal_id}/conectar",
        data={"csrf": _csrf(client)},
        follow_redirects=True,
    )
    # O QR chega na tela...
    assert grande in r.text
    # ...mas o cookie de sessão continua pequeno e sem o payload.
    cookie = client.cookies.get("session") or ""
    assert grande not in cookie
    assert len(cookie) < 1000


def test_desconectar_e_inativar_auditam(client, chatbot_fake, db, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    canal_id = chatbot_fake.canais[0]["id"]
    csrf = _csrf(client)
    r1 = client.post(
        f"/app/loja/whatsapp/canais/{canal_id}/desconectar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r1.status_code == 303
    r2 = client.post(
        f"/app/loja/whatsapp/canais/{canal_id}/inativar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    # Remoção é lógica: o canal continua na lista, inativo.
    alvo = [c for c in chatbot_fake.canais if c["id"] == canal_id][0]
    assert alvo["ativo"] is False
    assert alvo["estado"] == "inativo"
    assert sorted(linha.acao for linha in _acoes_auditadas(db)) == [
        "desconectar",
        "inativar",
    ]


def test_chatbot_indisponivel_mostra_banner(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    chatbot_fake.indisponivel = True
    r = client.get(TELA)
    assert r.status_code == 200
    assert "não foi possível" in r.text.lower()
    # Sem canais inventados e sem formulário de adicionar.
    assert "Adicionar número" not in r.text


def test_criar_com_chatbot_fora_audita_falha(client, chatbot_fake, db, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    csrf = _csrf(client)
    chatbot_fake.indisponivel = True
    r = client.post(
        "/app/loja/whatsapp/canais",
        data={"csrf": csrf, "label": "linha 2"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    linhas = _acoes_auditadas(db)
    assert [(linha.acao, linha.success) for linha in linhas] == [("criar", False)]
    assert linhas[0].error_code == "chatbot_indisponivel"


# --- Rota fina de status -----------------------------------------------------


def test_status_devolve_rotulo_humano(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    canal_id = chatbot_fake.canais[0]["id"]
    r = client.get(f"/app/loja/whatsapp/canais/{canal_id}/status")
    assert r.status_code == 200
    assert r.json() == {"estado": "conectado", "rotulo": "Conectado"}
    assert r.headers["cache-control"] == "no-store"


def test_status_para_vendedor_e_403_json(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    canal_id = chatbot_fake.canais[0]["id"]
    r = client.get(
        f"/app/loja/whatsapp/canais/{canal_id}/status", follow_redirects=False
    )
    assert r.status_code == 403
    assert r.json() == {"erro": "nao_autorizado"}


def test_status_com_flag_off_e_403_json(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch, whatsapp="0")
    login(client)
    canal_id = chatbot_fake.canais[0]["id"]
    r = client.get(
        f"/app/loja/whatsapp/canais/{canal_id}/status", follow_redirects=False
    )
    assert r.status_code == 403


def test_status_chatbot_fora_e_503(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    canal_id = chatbot_fake.canais[0]["id"]

    # O fake de status não honra `indisponivel`; forçamos a falha no objeto.
    def _fora(_canal_id):
        raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora")

    monkeypatch.setattr(chatbot_fake, "obter_status_canal_whatsapp", _fora)
    r = client.get(f"/app/loja/whatsapp/canais/{canal_id}/status")
    assert r.status_code == 503
    assert r.json() == {"erro": "indisponivel"}


# --- Navegação ---------------------------------------------------------------


def _store(roles=("dono",)):
    return StoreContext(
        loja_slug="loja-teste", roles=frozenset(roles), loja_state="ativa"
    )


def _ents():
    return EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
    )


def test_nav_com_flag_on_mostra_item_em_ajustes():
    sections = build_nav(
        _store(), _ents(), shell_enabled=True, whatsapp_enabled=True
    )
    ajustes = [s for s in sections if s.title == "Ajustes"][0]
    assert [i.label for i in ajustes.items] == [
        "Acessos bancários",
        "Números de WhatsApp",
        "Equipe",
    ]


def test_nav_com_flag_off_nao_mostra_item():
    items = flatten_nav(
        build_nav(_store(), _ents(), shell_enabled=True, whatsapp_enabled=False)
    )
    assert not any(i.href == TELA for i in items)


def test_nav_vendedor_nunca_ve_item():
    items = flatten_nav(
        build_nav(
            _store(roles=("vendedor",)),
            _ents(),
            shell_enabled=True,
            whatsapp_enabled=True,
        )
    )
    assert not any(i.href == TELA for i in items)


def test_shell_renderiza_link_quando_flag_on(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app")
    assert r.status_code == 200
    assert f'href="{TELA}"' in r.text


def test_shell_nao_renderiza_link_com_flag_off(client, monkeypatch):
    _ligar(monkeypatch, whatsapp="0")
    login(client)
    r = client.get("/app")
    assert r.status_code == 200
    assert f'href="{TELA}"' not in r.text
