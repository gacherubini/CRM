"""Áudio do Vendedor no Atendimento (Portal → Chatbot). Só Modo 2."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from conftest import csrf_da_resposta, login

from app.config import settings as portal_settings
from app.loja import routes as loja_routes
from app.loja.audio_media import AudioMediaNaoEncontrada, AudioMidia
from app.loja.human_messaging import (
    InMemoryHumanMessagingPort,
    MensagemHumanaLojaNaoOperacional,
)
from app.main import app

TELEFONE = "5511987654321"


@pytest.fixture
def atendimento_on(monkeypatch):
    enabled = replace(
        portal_settings,
        revy_loja_atendimento_enabled=True,
        revy_loja_audio_enabled=True,
    )
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


def _abrir_janela(chatbot_fake):
    chatbot_fake.mensagens[TELEFONE].append(
        {
            "id": f"msg-recente-{datetime.now(timezone.utc).timestamp()}",
            "direcao": "entrada",
            "texto": "oi",
            "criada_em": datetime.now(timezone.utc).isoformat(),
        }
    )


def _tornar_modo2(chatbot_fake):
    chatbot_fake.conversas[0]["canal_estado"] = "cloud_ativo"
    _abrir_janela(chatbot_fake)


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
    _abrir_janela(chatbot_fake)
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
    _abrir_janela(chatbot_fake)
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


def test_audio_fora_da_janela_422(client, chatbot_fake, messaging_fake):
    # Sem entrada recente: a janela de 24h está fechada.
    login(client)
    csrf = _csrf(client)

    r = _post_audio(client, csrf, key="janela-fechada")

    assert r.status_code == 422
    assert r.json()["error"] == "janela"
    assert messaging_fake.enviadas == []


class _PortaLojaOff:
    def enviar_texto(self, *args, **kwargs):
        raise MensagemHumanaLojaNaoOperacional("loja não operacional")

    def enviar_audio(self, *args, **kwargs):
        raise MensagemHumanaLojaNaoOperacional("loja não operacional")


def test_audio_loja_nao_operacional_423(client, chatbot_fake, atendimento_on):
    _abrir_janela(chatbot_fake)
    app.dependency_overrides[loja_routes.get_human_messaging_port] = (
        lambda: _PortaLojaOff()
    )
    try:
        login(client)
        csrf = _csrf(client)
        r = _post_audio(client, csrf, key="loja-off")
    finally:
        app.dependency_overrides.pop(loja_routes.get_human_messaging_port, None)

    assert r.status_code == 423


class _MediaFake:
    def __init__(self):
        self.chamadas = []

    def baixar(self, telefone, mensagem_id, *, range_header=None):
        self.chamadas.append(
            {"telefone": telefone, "mensagem_id": mensagem_id, "range": range_header}
        )
        if mensagem_id == "sumiu":
            raise AudioMediaNaoEncontrada("áudio não encontrado")
        if range_header:
            return AudioMidia(
                status=206,
                content=b"OG",
                media_type="audio/ogg",
                content_range="bytes 0-1/6",
            )
        return AudioMidia(status=200, content=b"OGG123", media_type="audio/ogg")

    def transcrever(self, telefone, mensagem_id):
        self.chamadas.append({"transcrever": mensagem_id})
        if mensagem_id == "sumiu":
            raise AudioMediaNaoEncontrada("áudio não encontrado")
        return "bom dia, tudo certo com a moto?"


@pytest.fixture
def media_fake(atendimento_on):
    fake = _MediaFake()
    app.dependency_overrides[loja_routes.get_audio_media_port] = lambda: fake
    yield fake
    app.dependency_overrides.pop(loja_routes.get_audio_media_port, None)


def test_proxy_midia_entrega_bytes(client, chatbot_fake, media_fake):
    login(client)
    r = client.get(f"/app/loja/atendimento/{TELEFONE}/audio/msg-1")

    assert r.status_code == 200
    assert r.content == b"OGG123"
    assert r.headers["accept-ranges"] == "bytes"
    assert media_fake.chamadas[0]["mensagem_id"] == "msg-1"


def test_proxy_midia_repassa_range(client, chatbot_fake, media_fake):
    login(client)
    r = client.get(
        f"/app/loja/atendimento/{TELEFONE}/audio/msg-1",
        headers={"Range": "bytes=0-1"},
    )

    assert r.status_code == 206
    assert r.content == b"OG"
    assert r.headers["content-range"] == "bytes 0-1/6"
    assert media_fake.chamadas[0]["range"] == "bytes=0-1"


def test_proxy_midia_inexistente_404(client, chatbot_fake, media_fake):
    login(client)
    r = client.get(f"/app/loja/atendimento/{TELEFONE}/audio/sumiu")

    assert r.status_code == 404


def test_proxy_midia_fora_escopo_403(client, chatbot_fake, media_fake, db):
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
    r = client.get(f"/app/loja/atendimento/{TELEFONE}/audio/msg-1")

    assert r.status_code == 403
    assert media_fake.chamadas == []


def test_proxy_midia_sem_login_401(client, chatbot_fake, media_fake):
    r = client.get(
        f"/app/loja/atendimento/{TELEFONE}/audio/msg-1",
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 401


def test_proxy_transcricao(client, chatbot_fake, media_fake):
    login(client)
    r = client.post(
        f"/app/loja/atendimento/{TELEFONE}/audio/msg-1/transcrever",
        headers={"Accept": "application/json"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["transcricao"] == "bom dia, tudo certo com a moto?"


def test_proxy_transcricao_fora_escopo_403(client, chatbot_fake, media_fake, db):
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
    r = client.post(
        f"/app/loja/atendimento/{TELEFONE}/audio/msg-1/transcrever",
        headers={"Accept": "application/json"},
    )

    assert r.status_code == 403


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


def test_flag_de_audio_desligada_esconde_e_bloqueia(
    client, chatbot_fake, monkeypatch
):
    enabled = replace(
        portal_settings,
        revy_loja_atendimento_enabled=True,
        revy_loja_audio_enabled=False,
    )
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)
    _tornar_modo2(chatbot_fake)
    login(client)
    csrf = _csrf(client)
    html = client.get(f"/app/loja/atendimento/{TELEFONE}").text
    assert "Gravar áudio" not in html
    assert "Só texto por enquanto." in html

    r = client.post(
        f"/app/loja/atendimento/{TELEFONE}/audio",
        data={"csrf": csrf, "idempotency_key": "x"},
        files={"arquivo": ("voz.webm", b"webm", "audio/webm")},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 404
