"""POST /v1/whatsapp/canais/cloud/onboarding e o status do template no webhook.

A loja sai da CREDENCIAL, nunca do corpo. E a resposta nao carrega segredo: a
tela de numeros da Loja mostra este JSON.

Os ``phone_number_id`` daqui comecam em 1227059273831600 de proposito: o banco
de teste e um SQLite em memoria compartilhado pela sessao inteira de pytest, e
``WhatsAppCanal.evolution_instance`` e UNIQUE global — a faixa ...581-...597 ja
esta ocupada por outros modulos.
"""
import hashlib
import hmac
import json
import uuid

import pytest

from app import main, servico
from app.meta_onboarding import OnboardingErro
from app.models_db import WhatsAppCanal

SEGREDO = "app-secret-onboarding"

CORPO = {
    "code": "code-do-popup",
    "waba_id": "waba-onb-1",
    "phone_number_id": "1227059273831600",
    "business_id": "biz-1",
}


def _assinar(corpo: bytes) -> dict:
    mac = hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={mac}", "Content-Type": "application/json"}


@pytest.fixture
def cloud_ligado(monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)


def _canal(loja_id: str, phone_number_id: str, waba_id: str) -> WhatsAppCanal:
    return WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label="linha-cloud",
        evolution_instance=phone_number_id,
        waba_id=waba_id,
        estado="cloud_pendente",
        onboarding_elo=5,
    )


# --- a rota -------------------------------------------------------------------


def test_rota_conecta_e_devolve_o_estado(client, db, loja_a, monkeypatch):
    def _falso(db_, loja_id, **kwargs):
        assert loja_id == loja_a["loja_id"], "a loja tem de vir da credencial"
        canal = _canal(loja_id, kwargs["phone_number_id"], kwargs["waba_id"])
        db_.add(canal)
        db_.commit()
        return canal

    monkeypatch.setattr(main.onboarding_cloud, "conectar", _falso)

    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding", json=CORPO, headers=loja_a["headers"]
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["estado"] == "cloud_pendente"
    assert corpo["onboarding_elo"] == 5
    for proibido in ("token", "pin", "token_cifrado", "pin_cifrado", "code"):
        assert proibido not in corpo
    assert "code-do-popup" not in resposta.text


def test_falha_de_elo_vira_erro_com_o_elo_nomeado(client, loja_a, monkeypatch):
    """A tela precisa dizer QUAL passo parou e de quem e a vez (spec §6)."""

    def _falso(db_, loja_id, **kwargs):
        raise OnboardingErro("nao deu para registrar o numero", elo=3)

    monkeypatch.setattr(main.onboarding_cloud, "conectar", _falso)

    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding",
        json={**CORPO, "phone_number_id": "1227059273831601"},
        headers=loja_a["headers"],
    )

    assert resposta.status_code == 502
    assert resposta.json()["detail"]["elo"] == 3


def test_corpo_incompleto_nao_chega_no_orquestrador(client, loja_a):
    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding",
        json={"code": "x"},
        headers=loja_a["headers"],
    )
    assert resposta.status_code == 422


def test_credencial_de_integracao_da_400_e_nao_423(client, db, monkeypatch):
    """Sem loja no token o gate responderia 423 e engoliria o erro de verdade."""

    def _nao_deveria(*a, **k):  # pragma: no cover - o teste falha se rodar
        raise AssertionError("a cadeia nao pode rodar sem loja")

    monkeypatch.setattr(main.onboarding_cloud, "conectar", _nao_deveria)
    token = servico.criar_credencial_integracao(db)
    db.commit()

    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding",
        json={**CORPO, "phone_number_id": "1227059273831602"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resposta.status_code == 400
    assert "loja" in resposta.json()["detail"]


def test_loja_suspensa_nao_conecta_canal(client, loja_sem_projecao, monkeypatch):
    """Suspensao e gate de backend: nao se abre numero novo para loja parada."""

    def _nao_deveria(*a, **k):  # pragma: no cover - o teste falha se rodar
        raise AssertionError("a cadeia nao pode rodar com a loja suspensa")

    monkeypatch.setattr(main.onboarding_cloud, "conectar", _nao_deveria)

    resposta = client.post(
        "/v1/whatsapp/canais/cloud/onboarding",
        json={**CORPO, "phone_number_id": "1227059273831603"},
        headers=loja_sem_projecao["headers"],
    )

    assert resposta.status_code == 423


# --- o status do template, no webhook que ja existe ---------------------------


def test_webhook_aprova_o_template_do_canal(db, loja_a):
    """A aprovacao chega por webhook, no /webhook/cloud que ja existe.

    Sem isto a tela `pendente` manda o lojista olhar o painel da Meta — que e
    exatamente o que este projeto existe para acabar.
    """
    canal = _canal(loja_a["loja_id"], "1227059273831604", "waba-onb-4")
    canal.template_oferta = None
    db.add(canal)
    db.commit()

    main.aplicar_status_de_template(
        db,
        {
            "field": "message_template_status_update",
            "value": {"event": "APPROVED", "message_template_name": "chama_vendedor"},
        },
        waba_id="waba-onb-4",
    )
    db.refresh(canal)

    assert canal.template_oferta == "chama_vendedor"


def test_reprovado_nao_marca_template(db, loja_a):
    """REJECTED nao pode virar template pronto: o envio quebraria no primeiro uso."""
    canal = _canal(loja_a["loja_id"], "1227059273831605", "waba-onb-5")
    canal.template_oferta = None
    db.add(canal)
    db.commit()

    main.aplicar_status_de_template(
        db,
        {
            "field": "message_template_status_update",
            "value": {"event": "REJECTED", "message_template_name": "chama_vendedor"},
        },
        waba_id="waba-onb-5",
    )
    db.refresh(canal)

    assert canal.template_oferta is None


def test_webhook_cloud_liga_a_aprovacao_ao_canal(client, db, loja_a, cloud_ligado):
    """O gancho mora no POST /webhook/cloud — a Meta nao ganha porta nova."""
    canal = _canal(loja_a["loja_id"], "1227059273831606", "waba-onb-6")
    canal.template_oferta = None
    db.add(canal)
    db.commit()

    payload = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-onb-6",
                    "changes": [
                        {
                            "field": "message_template_status_update",
                            "value": {
                                "event": "APPROVED",
                                "message_template_name": "chama_vendedor",
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()

    resposta = client.post("/webhook/cloud", data=payload, headers=_assinar(payload))

    assert resposta.status_code == 200
    db.refresh(canal)
    assert canal.template_oferta == "chama_vendedor"


def test_webhook_ignora_evento_de_outro_field(client, db, loja_a, cloud_ligado):
    """So `message_template_status_update` mexe no template do canal."""
    canal = _canal(loja_a["loja_id"], "1227059273831607", "waba-onb-7")
    canal.template_oferta = None
    db.add(canal)
    db.commit()

    payload = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-onb-7",
                    "changes": [
                        {
                            "field": "phone_number_quality_update",
                            "value": {
                                "event": "APPROVED",
                                "message_template_name": "chama_vendedor",
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()

    resposta = client.post("/webhook/cloud", data=payload, headers=_assinar(payload))

    assert resposta.status_code == 200
    db.refresh(canal)
    assert canal.template_oferta is None


def test_aprovacao_nao_vaza_para_a_waba_de_outra_loja(db, loja_a, loja_b):
    """A WABA e por loja: aprovacao de uma nao pode marcar o canal da outra."""
    canal_a = _canal(loja_a["loja_id"], "1227059273831608", "waba-onb-8")
    canal_a.template_oferta = None
    canal_b = _canal(loja_b["loja_id"], "1227059273831609", "waba-onb-9")
    canal_b.template_oferta = None
    db.add_all([canal_a, canal_b])
    db.commit()

    main.aplicar_status_de_template(
        db,
        {
            "field": "message_template_status_update",
            "value": {"event": "APPROVED", "message_template_name": "chama_vendedor"},
        },
        waba_id="waba-onb-8",
    )
    db.refresh(canal_a)
    db.refresh(canal_b)

    assert canal_a.template_oferta == "chama_vendedor"
    assert canal_b.template_oferta is None


def test_aprovacao_de_outro_template_nao_vira_template_de_oferta(client, db, loja_a):
    """A WABA da loja pode ter outro template aprovado — dela, nao nosso.

    Aceitar qualquer nome faz a ultima aprovacao virar o template de oferta, e o
    envio passa a chamar um modelo com outra forma de corpo.
    """
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()), loja_id=loja_a["loja_id"], e164_or_label="linha-cloud",
        evolution_instance="1227059273831610", waba_id="waba-outro-template",
        estado="cloud_pendente", onboarding_elo=5, template_oferta=None,
    )
    db.add(canal)
    db.commit()

    main.aplicar_status_de_template(
        db,
        {
            "field": "message_template_status_update",
            "value": {"event": "APPROVED", "message_template_name": "promo_natal"},
        },
        waba_id="waba-outro-template",
    )
    db.refresh(canal)

    assert canal.template_oferta is None
