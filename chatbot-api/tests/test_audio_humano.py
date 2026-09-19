"""POST /v1/conversas/{telefone}/audios — Áudio do Vendedor (só Modo 2).

O provedor Cloud aceita áudio; a Evolution não. O arquivo é convertido e
guardado por um port de mídia, que aqui é um fake (sem ffmpeg nem disco).
Nenhum número real: telefones sintéticos.
"""
import uuid

import pytest

from app.audio_humano import FakeAudioMedia, get_audio_media_port
from app.main import app
from app.models_db import LojaOperacionalProjecao
from app.whatsapp_outbound import WhatsAppOutboundError

CLIENTE = "5511987000201"
WEBM = b"\x1aE\xdf\xa3fake-webm-do-navegador"


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _CloudEspiao:
    """Dublê do transporte Cloud: registra na classe (o código instancia sozinho)."""

    audios: list[dict] = []
    textos: list[dict] = []
    fail: bool = False
    fail_code: str = "cloud_media_failed"

    def send_text(self, **kwargs):
        type(self).textos.append(kwargs)
        return {"messages": [{"id": "wamid.X"}]}

    def send_audio(self, **kwargs):
        type(self).audios.append(kwargs)
        if type(self).fail:
            raise WhatsAppOutboundError("Cloud recusou", code=type(self).fail_code)
        return {"messages": [{"id": "wamid.A"}]}


@pytest.fixture
def cloud(monkeypatch):
    _CloudEspiao.audios = []
    _CloudEspiao.textos = []
    _CloudEspiao.fail = False
    monkeypatch.setattr("app.whatsapp_outbound.CloudWhatsAppOutbound", _CloudEspiao)
    return _CloudEspiao


@pytest.fixture
def media():
    fake = FakeAudioMedia()
    app.dependency_overrides[get_audio_media_port] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_audio_media_port, None)


def _projetar_modo2(db, loja_id):
    db.add(
        LojaOperacionalProjecao(
            loja_id=loja_id,
            aggregate="whatsapp_modo",
            version=99,
            state="2",
            event_id=f"e-modo-{loja_id[:8]}",
        )
    )
    db.commit()


def _post_audio(client, headers, *, key=None, duracao="3", conteudo=WEBM):
    return client.post(
        f"/v1/conversas/{CLIENTE}/audios",
        headers=headers,
        data={
            "idempotency_key": key or f"portal:{uuid.uuid4().hex}",
            "ator": "vendedor@loja.test",
            **({"duracao_segundos": duracao} if duracao is not None else {}),
        },
        files={"arquivo": ("voz.webm", conteudo, "audio/webm")},
    )


def test_envia_audio_pela_cloud_e_persiste(client, db, loja_a, cloud, media):
    _projetar_modo2(db, loja_a["loja_id"])

    r = _post_audio(client, loja_a["headers"])

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tipo"] == "audio"
    assert body["texto"] is None
    assert body["media_ref"]
    assert body["duracao_segundos"] == 3
    assert body["bot_ativo"] is False
    assert body["enviado"] is True

    assert len(cloud.audios) == 1
    envio = cloud.audios[0]
    assert envio["number"] == CLIENTE
    assert envio["mime"] == "audio/ogg"
    assert envio["audio"].startswith(b"OGG")

    msgs = client.get(
        f"/v1/conversas/{CLIENTE}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    audio = [m for m in msgs if m.get("id") == body["mensagem_id"]]
    assert len(audio) == 1
    assert audio[0]["tipo"] == "audio"
    assert audio[0]["media_ref"] == body["media_ref"]

    estado = client.get(
        f"/v1/conversas/{CLIENTE}/estado", headers=loja_a["headers"]
    ).json()
    assert estado["bot_ativo"] is False


def test_audio_idempotente_nao_reenvia(client, db, loja_a, cloud, media):
    _projetar_modo2(db, loja_a["loja_id"])
    chave = f"portal:{uuid.uuid4().hex}"

    r1 = _post_audio(client, loja_a["headers"], key=chave)
    r2 = _post_audio(client, loja_a["headers"], key=chave)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["duplicada"] is False
    assert r2.json()["duplicada"] is True
    assert r1.json()["mensagem_id"] == r2.json()["mensagem_id"]
    assert len(cloud.audios) == 1


def test_audio_recusado_fora_do_modo2(client, db, loja_b, cloud, media):
    # Sem projeção whatsapp_modo=2: Loja Modo 1 recusa o microfone.
    r = _post_audio(client, loja_b["headers"])

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "audio_somente_cloud"
    assert cloud.audios == []


def test_audio_loja_nao_operacional_423(client, loja_sem_projecao, cloud, media):
    r = _post_audio(client, loja_sem_projecao["headers"])

    assert r.status_code == 423
    assert cloud.audios == []


def test_audio_acima_do_limite_recusado(client, db, loja_a, cloud, media, monkeypatch):
    monkeypatch.setattr("app.config.AUDIO_MAX_BYTES", 10)
    _projetar_modo2(db, loja_a["loja_id"])

    r = _post_audio(client, loja_a["headers"], conteudo=b"x" * 11)

    assert r.status_code == 413
    assert cloud.audios == []


def test_audio_longo_demais_recusado(client, db, loja_a, cloud, media, monkeypatch):
    monkeypatch.setattr("app.config.AUDIO_MAX_DURATION_SECONDS", 5)
    _projetar_modo2(db, loja_a["loja_id"])

    r = _post_audio(client, loja_a["headers"], duracao="10")

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "audio_muito_longo"
    assert cloud.audios == []


def test_falha_do_provedor_preserva_historico(client, db, loja_a, cloud, media):
    _projetar_modo2(db, loja_a["loja_id"])
    _CloudEspiao.fail = True

    r = _post_audio(client, loja_a["headers"])

    assert r.status_code == 502
    assert cloud.audios and cloud.audios[0]["number"] == CLIENTE

    msgs = client.get(
        f"/v1/conversas/{CLIENTE}/mensagens", headers=loja_a["headers"]
    ).json()["mensagens"]
    assert any(m.get("tipo") == "audio" for m in msgs)


def test_audio_de_outra_loja_nao_vaza(client, db, loja_a, loja_b, cloud, media):
    _projetar_modo2(db, loja_a["loja_id"])
    _projetar_modo2(db, loja_b["loja_id"])

    r_b = _post_audio(client, loja_b["headers"])
    assert r_b.status_code == 200, r_b.text
    msg_b = r_b.json()["mensagem_id"]

    resp_a = client.get(
        f"/v1/conversas/{CLIENTE}/mensagens", headers=loja_a["headers"]
    )
    # Ou a Loja A não tem conversa nesse telefone (404), ou a lista dela não
    # contém a mensagem da Loja B.
    if resp_a.status_code == 404:
        return
    msgs_a = resp_a.json().get("mensagens", [])
    assert all(m.get("id") != msg_b for m in msgs_a)
