"""POST /v1/conversas/{telefone}/mensagens/{id}/transcrever — sob demanda."""
import uuid

import pytest

from app.audio_humano import (
    AudioArmazenado,
    FakeAudioMedia,
    get_audio_media_port,
    get_transcription_provider,
)
from app.main import app
from app.models_db import Mensagem

TELEFONE = "5511987000401"


class _Provider:
    def __init__(self):
        self.chamadas = 0
        self.falha = False

    def transcrever(self, arquivo, mime):
        self.chamadas += 1
        if self.falha:
            raise RuntimeError("provider caiu")
        assert arquivo.is_file()
        return "bom dia, tudo certo com a moto?"


@pytest.fixture
def media():
    fake = FakeAudioMedia()
    app.dependency_overrides[get_audio_media_port] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_audio_media_port, None)


@pytest.fixture
def provider():
    fake = _Provider()
    app.dependency_overrides[get_transcription_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_transcription_provider, None)


def _criar_audio(db, loja_id, *, ref="r1"):
    mensagem_id = f"m-{uuid.uuid4().hex}"
    db.add(
        Mensagem(
            id=mensagem_id,
            loja_id=loja_id,
            conversa_id="conversa-1",
            direcao="saida",
            provider_message_id=f"human:{mensagem_id}",
            texto=None,
            tipo="audio",
            media_ref=ref,
            duracao_segundos=2,
        )
    )
    db.commit()
    return mensagem_id


def _armazenar(media):
    media.armazenados.append(
        AudioArmazenado(
            media_ref="r1", conteudo=b"OGG123", mime="audio/ogg", duracao_segundos=2
        )
    )


def test_transcreve_sob_demanda_e_nao_repete(client, db, loja_a, media, provider):
    _armazenar(media)
    mid = _criar_audio(db, loja_a["loja_id"])

    r1 = client.post(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/transcrever",
        headers=loja_a["headers"],
    )
    r2 = client.post(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/transcrever",
        headers=loja_a["headers"],
    )

    assert r1.status_code == 200, r1.text
    assert r1.json()["transcricao"] == "bom dia, tudo certo com a moto?"
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    assert provider.chamadas == 1

    # Persistiu na mensagem.
    db.expire_all()
    assert db.get(Mensagem, mid).transcricao == "bom dia, tudo certo com a moto?"


def test_transcricao_indisponivel_503(client, db, loja_a, media):
    _armazenar(media)
    mid = _criar_audio(db, loja_a["loja_id"])
    app.dependency_overrides[get_transcription_provider] = lambda: None
    try:
        r = client.post(
            f"/v1/conversas/{TELEFONE}/mensagens/{mid}/transcrever",
            headers=loja_a["headers"],
        )
    finally:
        app.dependency_overrides.pop(get_transcription_provider, None)

    assert r.status_code == 503


def test_falha_do_provider_502(client, db, loja_a, media, provider):
    _armazenar(media)
    mid = _criar_audio(db, loja_a["loja_id"])
    provider.falha = True

    r = client.post(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/transcrever",
        headers=loja_a["headers"],
    )

    assert r.status_code == 502


def test_transcricao_de_outra_loja_404(client, db, loja_a, loja_b, media, provider):
    _armazenar(media)
    mid = _criar_audio(db, loja_a["loja_id"])

    r = client.post(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/transcrever",
        headers=loja_b["headers"],
    )

    assert r.status_code == 404
