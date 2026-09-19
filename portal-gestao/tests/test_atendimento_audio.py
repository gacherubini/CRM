"""Áudio do Vendedor no Atendimento (Portal → Chatbot). Só Modo 2."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from conftest import csrf_da_resposta, login

from app.config import settings as portal_settings
from app.loja import routes as loja_routes
from app.loja.human_messaging import InMemoryHumanMessagingPort
from app.main import app

TELEFONE = "5511987654321"


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


def _tornar_modo2(chatbot_fake):
    chatbot_fake.conversas[0]["canal_estado"] = "cloud_ativo"
    chatbot_fake.mensagens[TELEFONE].append(
        {
            "id": "msg-recente",
            "direcao": "entrada",
            "texto": "oi",
            "criada_em": datetime.now(timezone.utc).isoformat(),
        }
    )


def _csrf(client):
    return csrf_da_resposta(client.get(f"/app/loja/atendimento/{TELEFONE}"))


def _post_audio(client, csrf, *, key="idem-audio-1", conteudo=b"webmbytes"):
    return client.post(
        f"/app/loja/atendimento/{TELEFONE}/audio",
        data={"csrf": csrf, "idempotency_key": key, "duracao_segundos": "2"},
        files={"arquivo": ("voz.webm", conteudo, "audio/webm")},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )


def test_envia_audio_multipart(client, chatbot_fake, messaging_fake):
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = _csrf(client)

    r = _post_audio(client, csrf)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["mensagem"]["tipo"] == "audio"

    assert len(messaging_fake.enviadas) == 1
    enviada = messaging_fake.enviadas[0]
    assert enviada["tipo"] == "audio"
    assert enviada["conteudo"] == b"webmbytes"
    assert enviada["telefone"] == TELEFONE


def test_audio_idempotente(client, chatbot_fake, messaging_fake):
    login(client)
    csrf = _csrf(client)

    r1 = _post_audio(client, csrf, key="idem-fixa")
    r2 = _post_audio(client, csrf, key="idem-fixa")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    assert len(messaging_fake.enviadas) == 1


def test_audio_fora_de_escopo_403(
    client, chatbot_fake, messaging_fake, db
):
    from app.financeiro_calc import identidade_telefone
    from app.models import AtendimentoAtribuicao, agora

    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone(TELEFONE),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = _csrf(client)
    r = _post_audio(client, csrf)

    assert r.status_code == 403
    assert messaging_fake.enviadas == []


def test_workspace_esconde_mic_fora_do_modo2(client, chatbot_fake, atendimento_on):
    login(client)
    html = client.get(f"/app/loja/atendimento/{TELEFONE}").text

    assert "Gravar áudio" not in html
    assert "Cloud API (Modo 2)" in html


def test_workspace_mostra_mic_no_modo2(client, chatbot_fake, atendimento_on):
    _tornar_modo2(chatbot_fake)
    login(client)
    html = client.get(f"/app/loja/atendimento/{TELEFONE}").text

    assert "Gravar áudio" in html
