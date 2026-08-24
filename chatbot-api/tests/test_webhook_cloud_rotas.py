import hashlib
import hmac

SEGREDO = "app-secret-de-teste"
VERIFY = "verify-de-teste"


def _assinar(corpo: bytes) -> dict:
    mac = hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={mac}", "Content-Type": "application/json"}


def test_get_devolve_o_challenge_em_texto_puro(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_VERIFY_TOKEN", VERIFY)
    resposta = client.get("/webhook/cloud", params={
        "hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345",
    })
    assert resposta.status_code == 200
    # Texto puro: a Meta compara o corpo inteiro. Aspas de JSON reprovam.
    assert resposta.text == "12345"


def test_get_com_token_errado_e_403(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_VERIFY_TOKEN", VERIFY)
    resposta = client.get("/webhook/cloud", params={
        "hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "12345",
    })
    assert resposta.status_code == 403


def test_post_sem_assinatura_e_401(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    assert client.post("/webhook/cloud", content=b"{}").status_code == 401


def test_post_com_assinatura_valida_e_200(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    corpo = b'{"object":"whatsapp_business_account","entry":[]}'
    resposta = client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))
    assert resposta.status_code == 200


def test_numero_desconhecido_nao_estoura_e_responde_200(client, monkeypatch):
    """Meta reentrega em erro. Número que não é de loja nenhuma: descarta e loga."""
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    corpo = (
        b'{"object":"whatsapp_business_account","entry":[{"id":"w","changes":'
        b'[{"field":"messages","value":{"metadata":{"phone_number_id":"nao-existe"},'
        b'"messages":[{"from":"1","id":"wamid.X","type":"text","text":{"body":"oi"}}]}}]}]}'
    )
    resposta = client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))
    assert resposta.status_code == 200


def test_reentrega_do_mesmo_wamid_nao_processa_duas_vezes(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    processados = []
    monkeypatch.setattr("app.main.processar_evento_cloud", lambda *a, **k: processados.append(1))

    corpo = (
        b'{"object":"whatsapp_business_account","entry":[{"id":"w","changes":'
        b'[{"field":"messages","value":{"metadata":{"phone_number_id":"111"},'
        b'"messages":[{"from":"1","id":"wamid.DUP","type":"text","text":{"body":"oi"}}]}}]}]}'
    )
    client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))
    client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))

    assert len(processados) == 1


def test_memoria_de_wamid_nao_cresce_sem_limite():
    """O processo vive semanas; set sem despejo vazaria memória para sempre."""
    from app.main import _WAMIDS_MEMORIA_MAX, _marcar_wamid_visto, _wamids_vistos

    for i in range(_WAMIDS_MEMORIA_MAX + 500):
        _marcar_wamid_visto(f"wamid.crescimento.{i}")

    assert len(_wamids_vistos) == _WAMIDS_MEMORIA_MAX
    # FIFO: o mais recente fica, o mais antigo saiu.
    assert "wamid.crescimento.0" not in _wamids_vistos
    assert f"wamid.crescimento.{_WAMIDS_MEMORIA_MAX + 499}" in _wamids_vistos


def test_wamid_no_banco_mas_fora_do_cache_nao_estoura(db, loja_a):
    """Reentrega depois de restart: o wamid está em `mensagens`, o cache não.

    Era o único ramo de `_wamid_ja_visto` sem cobertura, e derrubava o webhook
    com 500 — a Meta então reentregava e o 500 se repetia em laço.
    """
    import uuid

    from app.main import _wamid_ja_visto, _wamids_vistos
    from app.models_db import Conversa, Mensagem

    wamid = "wamid.REENTREGA"
    conversa = Conversa(
        id=str(uuid.uuid4()), loja_id=loja_a["loja_id"], telefone="5551999999999"
    )
    db.add(conversa)
    db.add(
        Mensagem(
            id=str(uuid.uuid4()),
            loja_id=loja_a["loja_id"],
            conversa_id=conversa.id,
            direcao="entrada",
            provider_message_id=wamid,
            texto="oi",
        )
    )
    db.commit()
    _wamids_vistos.pop(wamid, None)  # cache vazio, como depois de um restart

    assert _wamid_ja_visto(db, wamid) is True
    assert wamid in _wamids_vistos
