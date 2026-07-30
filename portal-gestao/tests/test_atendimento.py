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


def test_auditor_sem_permissao_403(client, chatbot_fake, atendimento_on):
    login(client, papel="auditor", email="auditor@loja.test")
    r = client.get("/app/loja/atendimento")
    assert r.status_code == 403


def test_mapear_estados_lead():
    assert mapear_estado_de_lead("novo") == AttendanceState.NOVO
    assert mapear_estado_de_lead("qualificado") == AttendanceState.NEGOCIACAO
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
    # Sem seletor arbitrário de canal/instance no composer
    assert 'name="instance"' not in r.text
    assert 'name="canal_id"' in r.text
    assert r.text.count("<select") == 0


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
