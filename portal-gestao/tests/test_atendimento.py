"""Atendimento unificado (Revy Loja Fase 4 lean)."""
from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import csrf_da_resposta, login

from app.config import settings as portal_settings
from app.financeiro_calc import identidade_telefone
from app.loja.attendance import (
    AttendanceState,
    mapear_estado_de_lead,
    unificar_lista,
)
from app.loja.human_messaging import InMemoryHumanMessagingPort
from app.loja import routes as loja_routes
from app.main import app
from app.models import AtendimentoAtribuicao, Usuario, agora


@pytest.fixture
def atendimento_on(monkeypatch):
    enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)
    yield


@pytest.fixture
def messaging_fake(atendimento_on):
    fake = InMemoryHumanMessagingPort()
    app.dependency_overrides[loja_routes.get_human_messaging_port] = lambda: fake
    yield fake
    app.dependency_overrides.pop(loja_routes.get_human_messaging_port, None)


def test_flag_off_retorna_404(client, chatbot_fake):
    login(client)
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 404
    assert "não está habilitado" in r.text


def test_lista_unifica_leads_e_conversas(client, chatbot_fake, atendimento_on):
    login(client)
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "Atendimento" in r.text
    assert "Maria Silva" in r.text
    # telefone completo só no href do workspace; UI mascara o display
    assert "•••• 4321" in r.text
    assert 'href="/app/loja/atendimento/5511987654321' in r.text
    assert ">5511987654321<" not in r.text


def test_leads_e_conversas_permanecem(client, chatbot_fake, atendimento_on):
    login(client)
    assert client.get("/app/leads").status_code == 200
    assert client.get("/app/conversas").status_code == 200


def test_workspace_detalhe(client, chatbot_fake, atendimento_on):
    login(client)
    r = client.get("/app/loja/atendimento/5511987654321")
    assert r.status_code == 200
    assert "Maria Silva" in r.text
    assert "Tem Civic disponível?" in r.text
    assert "Temos sim!" in r.text
    assert 'action="/app/loja/atendimento/5511987654321/mensagem"' in r.text


def test_vendedor_ve_fila_e_atribuidos(client, chatbot_fake, atendimento_on, db):
    # l1 Maria: sem atribuição → fila (visível)
    # l2 Joao: atribuído a outro vendedor → oculto
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511911112222"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="vendedor", email="vendedor@loja.test")
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert "Maria Silva" in r.text
    assert "Joao Oculto" not in r.text


def test_vendedor_fora_de_escopo_403(client, chatbot_fake, atendimento_on, db):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="vendedor", email="vendedor@loja.test")
    r = client.get("/app/loja/atendimento/5511987654321")
    assert r.status_code == 403
    assert "fora do seu escopo" in r.text


def test_vendedor_nao_envia_fora_de_escopo(
    client, chatbot_fake, messaging_fake, atendimento_on, db
):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/leads")
    r = client.post(
        "/app/loja/atendimento/5511987654321/mensagem",
        data={"csrf": csrf_da_resposta(pagina), "texto": "não devo enviar"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert messaging_fake.enviadas == []


def test_envio_humano_idempotente(
    client, chatbot_fake, messaging_fake, atendimento_on
):
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    csrf = csrf_da_resposta(pagina)
    payload = {
        "csrf": csrf,
        "texto": "Oi Maria, sou o vendedor.",
        "idempotency_key": "idem-fix-1",
    }
    r1 = client.post(
        "/app/loja/atendimento/5511987654321/mensagem",
        data=payload,
        follow_redirects=False,
    )
    assert r1.status_code == 303
    assert "ok=enviada" in r1.headers["location"]

    r2 = client.post(
        "/app/loja/atendimento/5511987654321/mensagem",
        data=payload,
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "ok=duplicada" in r2.headers["location"]
    assert len(messaging_fake.enviadas) == 1


def test_poll_mensagens_json_autenticado(client, chatbot_fake, atendimento_on):
    login(client)
    r = client.get("/app/loja/atendimento/5511987654321/mensagens.json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["telefone"] == "5511987654321"
    assert len(body["mensagens"]) == 2
    assert body["mensagens"][0]["id"] == "msg-m1"
    assert body["mensagens"][0]["texto"] == "Tem Civic disponível?"
    # Não vaza token do Chatbot
    assert "Bearer" not in r.text
    assert "CHATBOT_API_TOKEN" not in r.text


def test_poll_mensagens_json_after_id(client, chatbot_fake, atendimento_on):
    login(client)
    r = client.get(
        "/app/loja/atendimento/5511987654321/mensagens.json"
        "?after_id=msg-m1&canal_id=canal-principal"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert [m["id"] for m in body["mensagens"]] == ["msg-m2"]
    assert body["after_id"] == "msg-m1"
    assert body["last_id"] == "msg-m2"


def test_poll_mensagens_json_cursor_inexistente(
    client, chatbot_fake, atendimento_on
):
    login(client)
    r = client.get(
        "/app/loja/atendimento/5511987654321/mensagens.json?after_id=nao-existe"
    )
    assert r.status_code == 404
    assert r.json()["error"] == "cursor"


def test_poll_mensagens_json_vendedor_fora_escopo(
    client, chatbot_fake, atendimento_on, db
):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()
    login(client, papel="vendedor", email="vendedor@loja.test")
    r = client.get("/app/loja/atendimento/5511987654321/mensagens.json")
    assert r.status_code == 403
    assert r.json()["error"] == "scope"


def test_poll_mensagens_json_sem_login(client, chatbot_fake, atendimento_on):
    r = client.get("/app/loja/atendimento/5511987654321/mensagens.json")
    assert r.status_code == 401


def test_envio_json_sem_reload(
    client, chatbot_fake, messaging_fake, atendimento_on
):
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    csrf = csrf_da_resposta(pagina)
    r = client.post(
        "/app/loja/atendimento/5511987654321/mensagem",
        data={
            "csrf": csrf,
            "texto": "Resposta async",
            "idempotency_key": "idem-json-1",
            "canal_id": "canal-principal",
        },
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["duplicada"] is False
    assert body["bot_ativo"] is False
    assert body["mensagem"]["direcao"] == "saida"
    assert body["mensagem"]["texto"] == "Resposta async"
    assert body["mensagem"]["id"]
    assert len(messaging_fake.enviadas) == 1
    # Workspace HTML inclui hooks de poll/composer
    assert (
        'data-poll-url="/app/loja/atendimento/5511987654321/mensagens.json"'
        in pagina.text
    )
    assert "atendimento_workspace.js" in pagina.text
    assert "data-msg-id=" in pagina.text


def test_auditor_sem_permissao_403(client, chatbot_fake, atendimento_on):
    login(client, papel="auditor", email="auditor@loja.test")
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 403


def test_mapear_estados_lead():
    assert mapear_estado_de_lead("novo") == AttendanceState.NOVO
    assert mapear_estado_de_lead("qualificado") == AttendanceState.AGUARDANDO_SIMULACAO
    assert mapear_estado_de_lead("convertido") == AttendanceState.VENDIDO
    assert mapear_estado_de_lead("perdido") == AttendanceState.PERDIDO


def test_unificar_isola_por_visibilidade():
    dono = Usuario(
        email="dono@x", nome="D", senha_hash="x", papel="dono", loja_slug="l"
    )
    vendedor = Usuario(
        email="v@x", nome="V", senha_hash="x", papel="vendedor", loja_slug="l"
    )
    leads = [
        {"id": "l1", "telefone": "5511111111111", "nome": "A", "etapa": "novo"},
        {"id": "l2", "telefone": "5511222222222", "nome": "B", "etapa": "novo"},
    ]
    itens_v = unificar_lista(
        leads=leads, conversas=[], atribuicoes={}, usuario=vendedor
    )
    itens_d = unificar_lista(
        leads=leads, conversas=[], atribuicoes={}, usuario=dono
    )
    assert len(itens_v) == 2
    assert len(itens_d) == 2


def test_filtro_canal_id_na_lista(client, chatbot_fake, atendimento_on):
    """F6: ?canal_id= isola conversas do canal; dropdown só se multi-canal."""
    chatbot_fake.conversas.append(
        {
            "id": "c3",
            "telefone": "5511933334444",
            "bot_ativo": True,
            "status": "aberta",
            "atualizada_em": "2026-07-12T15:00:00+00:00",
            "ultima_mensagem": {
                "texto": "Oi no canal 2",
                "criada_em": "2026-07-12T15:00:00+00:00",
                "direcao": "entrada",
            },
            "canal_id": "canal-secundario",
            "evolution_instance": "loja-teste-wa-2",
            "canal_label": "linha-2",
            "canal_ativo": True,
            "canal_estado": "conectado",
        }
    )
    login(client)
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 200
    assert 'name="canal_id"' in r.text
    assert "linha-2" in r.text or "canal-secundario" in r.text
    assert "***0001" in r.text

    r2 = client.get("/app/loja/atendimento?canal_id=canal-secundario")
    assert r2.status_code == 200
    assert "Oi no canal 2" in r2.text
    # Maria (canal principal) some do filtro do secundário
    assert "Tem Civic disponível?" not in r2.text


def test_badge_canal_no_workspace(client, chatbot_fake, atendimento_on):
    login(client)
    r = client.get("/app/loja/atendimento/5511987654321?canal_id=canal-principal")
    assert r.status_code == 200
    assert "***0001" in r.text
    assert 'name="canal_id" value="canal-principal"' in r.text
    # Sem seletor arbitrário de canal/instance no composer (etapa tem select próprio)
    assert 'name="instance"' not in r.text
    assert 'name="canal_id"' in r.text
    assert 'name="etapa"' in r.text
    assert 'name="instance"' not in r.text


def test_envio_usa_instance_da_conversa_nao_do_form(
    client, chatbot_fake, messaging_fake, atendimento_on
):
    """F6: payload não aceita canal arbitrário do form; usa o da conversa."""
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    csrf = csrf_da_resposta(pagina)
    r = client.post(
        "/app/loja/atendimento/5511987654321/mensagem",
        data={
            "csrf": csrf,
            "texto": "Resposta no canal certo",
            "idempotency_key": "idem-canal-1",
            # Tentativa de forjar outro canal — deve ser ignorada.
            "instance": "instancia-arbitraria-hack",
            "canal_id": "canal-principal",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=enviada" in r.headers["location"]
    assert len(messaging_fake.enviadas) == 1
    envio = messaging_fake.enviadas[0]
    assert envio["instance"] == "loja-teste-wa"
    assert envio["instance"] != "instancia-arbitraria-hack"
    assert envio["texto"] == "Resposta no canal certo"


def test_envio_bloqueado_canal_inativo(
    client, chatbot_fake, messaging_fake, atendimento_on
):
    chatbot_fake.conversas[0]["canal_ativo"] = False
    chatbot_fake.conversas[0]["canal_estado"] = "inativo"
    login(client)
    r = client.get("/app/loja/atendimento/5511987654321")
    assert r.status_code == 200
    assert "Envio bloqueado" in r.text
    assert 'action="/app/loja/atendimento/5511987654321/mensagem"' not in r.text

    pagina = client.get("/app/leads")
    r2 = client.post(
        "/app/loja/atendimento/5511987654321/mensagem",
        data={
            "csrf": csrf_da_resposta(pagina),
            "texto": "não deve enviar",
            "idempotency_key": "bloqueado-1",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "erro=canal" in r2.headers["location"]
    assert messaging_fake.enviadas == []


def test_unificar_dois_canais_mesmo_telefone():
    """Mesmo cliente em dois canais → duas linhas; lead único por telefone."""
    dono = Usuario(
        email="dono@x", nome="D", senha_hash="x", papel="dono", loja_slug="l"
    )
    leads = [
        {
            "id": "l1",
            "telefone": "5511988000001",
            "nome": "Cliente Dual",
            "etapa": "novo",
        }
    ]
    conversas = [
        {
            "id": "c1",
            "telefone": "5511988000001",
            "bot_ativo": True,
            "status": "aberta",
            "atualizada_em": "2026-07-12T14:00:00+00:00",
            "ultima_mensagem": {"texto": "no 1", "direcao": "entrada"},
            "canal_id": "ca",
            "canal_label": "***0001",
            "canal_ativo": True,
            "canal_estado": "conectado",
        },
        {
            "id": "c2",
            "telefone": "5511988000001",
            "bot_ativo": True,
            "status": "aberta",
            "atualizada_em": "2026-07-12T15:00:00+00:00",
            "ultima_mensagem": {"texto": "no 2", "direcao": "entrada"},
            "canal_id": "cb",
            "canal_label": "linha-2",
            "canal_ativo": True,
            "canal_estado": "conectado",
        },
    ]
    itens = unificar_lista(
        leads=leads, conversas=conversas, atribuicoes={}, usuario=dono
    )
    assert len(itens) == 2
    assert {i.canal_id for i in itens} == {"ca", "cb"}
    assert all(i.nome == "Cliente Dual" for i in itens)
    assert all(i.lead_id == "l1" for i in itens)


def test_filtrar_itens_por_canal():
    from app.loja.attendance import AttendanceListItem, filtrar_itens

    base = dict(
        id="5511",
        telefone="5511",
        nome=None,
        estado=AttendanceState.NOVO,
        interesse=None,
        lead_id=None,
        bot_ativo=True,
        status_conversa="aberta",
        ultima_mensagem=None,
        atualizada_em=None,
        atribuido_a=None,
    )
    itens = [
        AttendanceListItem(**base, canal_id="a", canal_label="A"),
        AttendanceListItem(**base, canal_id="b", canal_label="B"),
    ]
    assert len(filtrar_itens(itens, canal_id="a")) == 1
    assert filtrar_itens(itens, canal_id="a")[0].canal_id == "a"


# ---------------------------------------------------------------------------
# Handoff / etapa no workspace (F4 residual)
# ---------------------------------------------------------------------------


def test_workspace_mostra_acoes_sidebar(client, chatbot_fake, atendimento_on):
    login(client)
    r = client.get("/app/loja/atendimento/5511987654321")
    assert r.status_code == 200
    assert 'action="/app/loja/atendimento/5511987654321/handoff"' in r.text
    assert "Assumir atendimento" in r.text
    assert 'action="/app/loja/atendimento/5511987654321/etapa"' in r.text
    assert 'name="etapa"' in r.text
    assert 'href="/app/simulacoes?celular=5511987654321"' in r.text
    assert 'href="/app/vendas/nova?lead_ref=l1"' in r.text
    assert 'href="/app/leads/l1"' in r.text
    assert 'href="/app/conversas/5511987654321"' in r.text


def test_handoff_workspace_assumir(
    client, chatbot_fake, atendimento_on, db
):
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    csrf = csrf_da_resposta(pagina)
    r = client.post(
        "/app/loja/atendimento/5511987654321/handoff",
        data={
            "csrf": csrf,
            "acao": "assumir",
            "canal_id": "canal-principal",
            # Tentativa de forjar instance — servidor ignora e usa a da conversa.
            "instance": "instancia-arbitraria-hack",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=assumir" in r.headers["location"]
    assert chatbot_fake.handoffs == [("5511987654321", False)]
    assert chatbot_fake.last_handoff_instance == "loja-teste-wa"
    atr = (
        db.query(AtendimentoAtribuicao)
        .filter(
            AtendimentoAtribuicao.loja_slug == "loja-teste",
            AtendimentoAtribuicao.telefone_hmac
            == identidade_telefone("5511987654321"),
            AtendimentoAtribuicao.ativa.is_(True),
        )
        .one()
    )
    assert atr.vendedor_email == "vendedor@loja.test"


def test_handoff_workspace_devolver(client, chatbot_fake, atendimento_on, db):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="vendedor@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()
    chatbot_fake.estados["5511987654321"] = {
        "bot_ativo": False,
        "status": "handoff",
    }
    chatbot_fake.conversas[0]["bot_ativo"] = False

    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    assert "Devolver ao bot" in pagina.text
    r = client.post(
        "/app/loja/atendimento/5511987654321/handoff",
        data={
            "csrf": csrf_da_resposta(pagina),
            "acao": "devolver",
            "canal_id": "canal-principal",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=devolver" in r.headers["location"]
    assert chatbot_fake.handoffs == [("5511987654321", True)]
    ativas = (
        db.query(AtendimentoAtribuicao)
        .filter(
            AtendimentoAtribuicao.loja_slug == "loja-teste",
            AtendimentoAtribuicao.telefone_hmac
            == identidade_telefone("5511987654321"),
            AtendimentoAtribuicao.ativa.is_(True),
        )
        .all()
    )
    assert ativas == []


def test_handoff_workspace_fora_de_escopo_403(
    client, chatbot_fake, atendimento_on, db
):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/leads")
    r = client.post(
        "/app/loja/atendimento/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "assumir"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert chatbot_fake.handoffs == []


def test_handoff_workspace_chatbot_down_ainda_atribui_local(
    client, chatbot_fake, atendimento_on, db
):
    """Degradação: bot toggle falha, atribuição local ainda tenta."""
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    csrf = csrf_da_resposta(pagina)
    chatbot_fake.indisponivel = True
    r = client.post(
        "/app/loja/atendimento/5511987654321/handoff",
        data={"csrf": csrf, "acao": "assumir", "canal_id": "canal-principal"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=assumir" in r.headers["location"]
    assert "aviso=bot-indisponivel" in r.headers["location"]
    assert chatbot_fake.handoffs == []
    atr = (
        db.query(AtendimentoAtribuicao)
        .filter(
            AtendimentoAtribuicao.loja_slug == "loja-teste",
            AtendimentoAtribuicao.telefone_hmac
            == identidade_telefone("5511987654321"),
            AtendimentoAtribuicao.ativa.is_(True),
        )
        .one()
    )
    assert atr.vendedor_email == "vendedor@loja.test"


def test_etapa_workspace_atualiza_lead(client, chatbot_fake, atendimento_on):
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/loja/atendimento/5511987654321")
    r = client.post(
        "/app/loja/atendimento/5511987654321/etapa",
        data={
            "csrf": csrf_da_resposta(pagina),
            "lead_id": "l1",
            "etapa": "em_atendimento",
            "canal_id": "canal-principal",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ok=etapa-atualizada" in r.headers["location"]
    assert chatbot_fake.etapas_atualizadas == [("l1", "em_atendimento")]
    assert chatbot_fake.leads[0]["etapa"] == "em_atendimento"


def test_etapa_workspace_fora_de_escopo_403(
    client, chatbot_fake, atendimento_on, db
):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/leads")
    r = client.post(
        "/app/loja/atendimento/5511987654321/etapa",
        data={
            "csrf": csrf_da_resposta(pagina),
            "lead_id": "l1",
            "etapa": "qualificado",
        },
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert chatbot_fake.etapas_atualizadas == []


def test_etapa_workspace_rejeita_valor_invalido(
    client, chatbot_fake, atendimento_on
):
    login(client)
    pagina = client.get("/app/loja/atendimento/5511987654321")
    r = client.post(
        "/app/loja/atendimento/5511987654321/etapa",
        data={
            "csrf": csrf_da_resposta(pagina),
            "lead_id": "l1",
            "etapa": "inexistente",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro=etapa" in r.headers["location"]
    assert chatbot_fake.etapas_atualizadas == []
