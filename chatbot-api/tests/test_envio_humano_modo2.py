"""O envio humano do Atendimento tem de respeitar o modo da loja (spec §6.3).

`_enviar_texto_evolution` chamava `get_whatsapp_outbound()` — o singleton do
Modo 1 — em vez de `outbound_para_loja`. Numa loja Modo 2 o `evolution_instance`
do canal guarda o `phone_number_id` da Meta, então a resposta do vendedor saía
para o Evolution com um nome de instância que não existe lá.

Consequência em produção: **numa loja Modo 2 o vendedor não conseguia responder
pelo portal**. Passou despercebido porque o handoff entrega a conversa ao
WhatsApp do próprio vendedor, então a caixa de texto do Atendimento quase não
era usada.

Mesmo defeito de `2026-08-24-outbound-por-loja-quer-loja-id`, que consertou o
`modo2_workers.py` e não olhou para este caminho.

Nenhum número real: telefones sintéticos e rótulos `pnid-…`.
"""
import uuid

import pytest

from app import servico
from app.models_db import LojaOperacionalProjecao, WhatsAppCanal
from app.whatsapp_provider import ESTADO_CLOUD_ATIVO

CLIENTE = "5511988887777"


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _CloudEspiao:
    """Dublê do transporte Cloud. Registra na classe: o código instancia sozinho."""

    envios: list[dict] = []

    def send_text(self, **kwargs):
        type(self).envios.append(kwargs)
        return {"messages": [{"id": "wamid.X"}]}


@pytest.fixture
def cloud(monkeypatch):
    _CloudEspiao.envios = []
    monkeypatch.setattr("app.whatsapp_outbound.CloudWhatsAppOutbound", _CloudEspiao)
    return _CloudEspiao


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


def _canal_cloud(db, loja_id):
    """No Modo 2 `evolution_instance` guarda o phone_number_id da Meta."""
    sufixo = uuid.uuid4().hex[:8]
    phone_number_id = f"pnid-{sufixo}"
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            e164_or_label="central",
            evolution_instance=phone_number_id,
            ativo=True,
            estado=ESTADO_CLOUD_ATIVO,
            waba_id=f"waba-{sufixo}",
            template_oferta="chama_vendedor",
        )
    )
    db.commit()
    return phone_number_id


def test_loja_modo2_envia_pela_cloud(db, loja_a, cloud, _fake_whatsapp_outbound):
    """O defeito: isto ia para o Evolution com um phone_number_id como instância."""
    _projetar_modo2(db, loja_a["loja_id"])
    phone_number_id = _canal_cloud(db, loja_a["loja_id"])

    servico.enviar_mensagem_humana(
        db,
        loja_a["loja_id"],
        CLIENTE,
        "a CG 160 2022 esta disponivel",
        idempotency_key=f"portal:{uuid.uuid4().hex}",
        instance=phone_number_id,
        ator="vendedor@loja.com",
    )

    assert len(cloud.envios) == 1
    assert cloud.envios[0]["text"] == "a CG 160 2022 esta disponivel"
    assert _fake_whatsapp_outbound.calls == []


def test_loja_modo1_continua_no_evolution(db, loja_b, cloud, _fake_whatsapp_outbound):
    """Guarda de regressão: o conserto não pode desviar o Modo 1."""
    servico.enviar_mensagem_humana(
        db,
        loja_b["loja_id"],
        CLIENTE,
        "oi",
        idempotency_key=f"portal:{uuid.uuid4().hex}",
        ator="vendedor@loja.com",
    )

    assert cloud.envios == []
    assert len(_fake_whatsapp_outbound.calls) == 1
