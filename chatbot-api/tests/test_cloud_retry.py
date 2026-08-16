"""O "processar depois" da §6.1.

Antes disto, falha no processamento virava `logger.exception` e o lead sumia:
a Meta ja tinha recebido 200 do n8n, entao nao reentregava, e ninguem ficava
sabendo. Estes testes cobrem o caminho inteiro — falhou, guardou, tentou de
novo, deu certo — e o teto de tentativas.
"""
import hashlib
import hmac
import json

import pytest

from app.cloud_retry import MAX_TENTATIVAS, reprocessar_pendentes
from app.models_db import CloudEventoFalho

SEGREDO = "app-secret-retry"
CLIENTE = "5511955550001"
WAMID = "wamid.RETRY1"


@pytest.fixture(autouse=True)
def _cloud_ligado(monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)


def _assinar(corpo: bytes) -> dict:
    mac = hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={mac}", "Content-Type": "application/json"}


def _inbound(phone_number_id: str, wamid: str = WAMID) -> bytes:
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone_number_id},
            "messages": [{
                "from": CLIENTE,
                "id": wamid,
                "type": "text",
                "text": {"body": "oi, tem biz 125?"},
            }],
        }}]}],
    }).encode()


def test_falha_no_processamento_guarda_o_evento_cru(client, db, loja_a, monkeypatch):
    """Estourou? A mensagem nao pode evaporar num log."""
    def _explode(*a, **k):
        raise RuntimeError("banco caiu no meio")

    monkeypatch.setattr("app.main.processar_evento_cloud", _explode)

    corpo = _inbound("pnid-retry")
    resposta = client.post("/webhook/cloud", data=corpo, headers=_assinar(corpo))

    # 200 mesmo assim: a §6.1 nao quer a Meta reentregando.
    assert resposta.status_code == 200
    assert resposta.json()["mensagens"] == []

    linha = db.query(CloudEventoFalho).filter(CloudEventoFalho.wamid == WAMID).one()
    assert linha.estado == "pendente"
    assert linha.tentativas == 0
    assert json.loads(linha.corpo_cru)["entry"][0]["changes"][0]["field"] == "messages"


def test_reprocesso_roda_o_que_falhou_e_marca_processado(db, monkeypatch):
    # wamid proprio: o SQLite dos testes e StaticPool compartilhado, sem limpeza
    # entre casos, e o pendente do teste vizinho entraria neste reprocesso.
    meu = "wamid.RETRY_OK"
    vistos = []

    def _ok(_db, evento):
        vistos.append(evento.wamid)
        return None

    monkeypatch.setattr("app.main.processar_evento_cloud", _ok)

    db.add(CloudEventoFalho(
        id="cef-1", wamid=meu, phone_number_id="pnid-retry",
        corpo_cru=_inbound("pnid-retry", wamid=meu).decode(),
        estado="pendente", tentativas=0,
    ))
    db.commit()

    reprocessar_pendentes(db)

    assert meu in vistos
    linha = db.query(CloudEventoFalho).filter(CloudEventoFalho.wamid == meu).one()
    assert linha.estado == "processado"
    assert linha.ultimo_erro is None


def test_evento_que_falha_sempre_desiste_no_teto(db, monkeypatch):
    """Evento defeituoso nao pode girar para sempre."""
    def _explode(*a, **k):
        raise RuntimeError("continua quebrado")

    monkeypatch.setattr("app.main.processar_evento_cloud", _explode)

    db.add(CloudEventoFalho(
        id="cef-2", wamid="wamid.RUIM", phone_number_id="pnid-retry",
        corpo_cru=_inbound("pnid-retry", wamid="wamid.RUIM").decode(),
        estado="pendente", tentativas=0,
    ))
    db.commit()

    for _ in range(MAX_TENTATIVAS + 2):
        reprocessar_pendentes(db)
        db.commit()

    linha = db.query(CloudEventoFalho).filter(CloudEventoFalho.wamid == "wamid.RUIM").one()
    assert linha.estado == "desistiu"
    assert linha.tentativas == MAX_TENTATIVAS
    assert "continua quebrado" in (linha.ultimo_erro or "")


def test_corpo_ilegivel_desiste_na_primeira(db):
    db.add(CloudEventoFalho(
        id="cef-3", wamid="wamid.LIXO", phone_number_id="pnid-retry",
        corpo_cru="{isso nao e json", estado="pendente", tentativas=0,
    ))
    db.commit()

    reprocessar_pendentes(db)
    db.commit()

    linha = db.query(CloudEventoFalho).filter(CloudEventoFalho.wamid == "wamid.LIXO").one()
    assert linha.estado == "desistiu"
    assert "corpo inválido" in (linha.ultimo_erro or "")


def test_registrar_e_idempotente_por_wamid(db):
    from app.cloud_retry import registrar_evento_falho

    for _ in range(3):
        registrar_evento_falho(
            db, wamid="wamid.DUP", phone_number_id="pnid",
            corpo_cru=_inbound("pnid", wamid="wamid.DUP"),
        )
    db.commit()

    assert db.query(CloudEventoFalho).filter(CloudEventoFalho.wamid == "wamid.DUP").count() == 1
