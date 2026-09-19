"""GET /v1/conversas/{telefone}/mensagens/{id}/midia — leitura do áudio da Loja."""
import uuid

import pytest

from app.audio_humano import AudioArmazenado, FakeAudioMedia, get_audio_media_port
from app.main import app
from app.models_db import Mensagem

TELEFONE = "5511987000301"


@pytest.fixture
def media():
    fake = FakeAudioMedia()
    app.dependency_overrides[get_audio_media_port] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_audio_media_port, None)


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


def test_le_audio_da_propria_loja(client, db, loja_a, media):
    media.armazenados.append(
        AudioArmazenado(
            media_ref="r1", conteudo=b"OGG123", mime="audio/ogg", duracao_segundos=2
        )
    )
    mid = _criar_audio(db, loja_a["loja_id"])

    r = client.get(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/midia",
        headers=loja_a["headers"],
    )

    assert r.status_code == 200
    assert r.content == b"OGG123"
    assert r.headers["content-type"].startswith("audio/ogg")
    assert r.headers["accept-ranges"] == "bytes"


def test_requisicao_parcial(client, db, loja_a, media):
    media.armazenados.append(
        AudioArmazenado(
            media_ref="r1", conteudo=b"OGG123", mime="audio/ogg", duracao_segundos=2
        )
    )
    mid = _criar_audio(db, loja_a["loja_id"])

    r = client.get(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/midia",
        headers={**loja_a["headers"], "Range": "bytes=0-2"},
    )

    assert r.status_code == 206
    assert r.content == b"OGG"
    assert r.headers["content-range"] == "bytes 0-2/6"


def test_audio_de_outra_loja_404(client, db, loja_a, loja_b, media):
    media.armazenados.append(
        AudioArmazenado(
            media_ref="r1", conteudo=b"OGG123", mime="audio/ogg", duracao_segundos=2
        )
    )
    mid = _criar_audio(db, loja_a["loja_id"])

    r = client.get(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/midia",
        headers=loja_b["headers"],
    )

    assert r.status_code == 404


def test_midia_de_mensagem_de_texto_404(client, db, loja_a, media):
    mid = f"m-{uuid.uuid4().hex}"
    db.add(
        Mensagem(
            id=mid,
            loja_id=loja_a["loja_id"],
            conversa_id="conversa-1",
            direcao="saida",
            provider_message_id=f"human:{mid}",
            texto="oi",
        )
    )
    db.commit()

    r = client.get(
        f"/v1/conversas/{TELEFONE}/mensagens/{mid}/midia",
        headers=loja_a["headers"],
    )

    assert r.status_code == 404
