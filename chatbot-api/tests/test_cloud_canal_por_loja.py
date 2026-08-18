"""Modo 2 fala pelo número DA LOJA, não pela credencial global (spec §6.2).

O piloto saiu com ``CHATBOT_GRAPH_PHONE_NUMBER_ID`` global. Com duas lojas Cloud
no mesmo processo isso manda a mensagem de uma pelo número da outra — e template
de mensagem é recurso da WABA, então o nome aprovado numa loja não existe na
outra. Estes testes são a rede desse par de bugs.

Nenhum número ou token real aqui: tudo é rótulo sintético (``pnid-…``).
"""
import uuid

import pytest

from app.cloud_canal import (
    credenciais_cloud_da_loja,
    phone_number_id_da_loja,
    template_oferta_da_loja,
)
from app.handoff_gatilhos import disparar_handoff
from app.models_db import FilaVendedor, LojaOperacionalProjecao, WhatsAppCanal
from app.oferta_envio import enviar_oferta
from app.rodizio import abrir_oferta
from app.whatsapp_provider import (
    ESTADO_CLOUD_ATIVO,
    ESTADO_CONECTADO,
    ESTADO_DESCONECTADO,
    ESTADO_INATIVO,
    ESTADO_PENDENTE,
    ESTADOS_VALIDOS,
)

PNID_AMBIENTE = "pnid-do-ambiente"
TEMPLATE_AMBIENTE = "template_do_ambiente"


@pytest.fixture(autouse=True)
def _ambiente_cloud(monkeypatch):
    """Fallback global — é o que a loja piloto usa hoje, sem canal cadastrado."""
    monkeypatch.setattr("app.cloud_canal.config.GRAPH_PHONE_NUMBER_ID", PNID_AMBIENTE)
    monkeypatch.setattr(
        "app.cloud_canal.config.GRAPH_TEMPLATE_OFERTA", TEMPLATE_AMBIENTE
    )
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _OutboundFake:
    def __init__(self):
        self.textos = []
        self.templates = []
        self.interativas = []

    def send_text(self, **kwargs):
        self.textos.append(kwargs)
        return {"messages": [{"id": "wamid.X"}]}

    def send_template_button(self, **kwargs):
        self.templates.append(kwargs)
        return {"messages": [{"id": "wamid.T"}]}

    def send_interactive_button(self, **kwargs):
        self.interativas.append(kwargs)
        return {"messages": [{"id": "wamid.I"}]}


def _modo2(db, loja_id):
    db.add(
        LojaOperacionalProjecao(
            loja_id=loja_id,
            aggregate="whatsapp_modo",
            version=1,
            state="2",
            event_id=f"e-modo-{loja_id[:8]}",
        )
    )
    db.commit()


def _canal_cloud(db, loja_id, *, rotulo="pnid", waba_id="waba", template=None):
    """Canal Cloud: ``waba_id`` gravado e o pnid na coluna ``evolution_instance``.

    Reuso deliberado da coluna (ver ``models_db.WhatsAppCanal``) — não é engano
    de nome. Devolve ``(phone_number_id, waba_id)``: o banco da suíte é um só
    para todos os testes e ``evolution_instance`` é UNIQUE, então o valor tem de
    ser único por teste.
    """
    sufixo = uuid.uuid4().hex[:8]
    phone_number_id = f"{rotulo}-{sufixo}"
    waba = f"{waba_id}-{sufixo}"
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            e164_or_label="central",
            evolution_instance=phone_number_id,
            ativo=True,
            estado=ESTADO_CLOUD_ATIVO,
            waba_id=waba,
            template_oferta=template,
        )
    )
    db.commit()
    return phone_number_id, waba


def _vendedor(db, loja_id, *, nome="Ana", telefone="5511999990000"):
    db.add(
        FilaVendedor(
            id=f"{loja_id[:8]}-fila-0",
            loja_id=loja_id,
            nome=nome,
            telefone=telefone,
            ordem=0,
            ativo=True,
        )
    )
    db.commit()


# --------------------------------------------------------------------------
# 1. número do canal
# --------------------------------------------------------------------------


def test_envio_usa_o_numero_gravado_no_canal_da_loja(db, loja_a):
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    pnid, _ = _canal_cloud(db, loja_id)
    _vendedor(db, loja_id)

    oferta = abrir_oferta(db, loja_id, "5511988887777")
    fake = _OutboundFake()
    enviar_oferta(db, oferta, outbound=fake)

    assert fake.templates[0]["instance"] == pnid
    assert fake.templates[0]["instance"] != PNID_AMBIENTE


def test_aviso_ao_cliente_tambem_sai_pelo_numero_da_loja(db, loja_a):
    """O handoff manda 2 mensagens (vendedor e cliente); as duas pelo canal."""
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    pnid, _ = _canal_cloud(db, loja_id)
    _vendedor(db, loja_id)

    fake = _OutboundFake()
    assert (
        disparar_handoff(
            db, loja_id, "5511988887777", motivo="pediu_humano", outbound=fake
        )
        == "ofertado"
    )

    instancias = {m["instance"] for m in fake.textos + fake.templates}
    assert instancias == {pnid}


# --------------------------------------------------------------------------
# 2. fallback no ambiente (loja piloto)
# --------------------------------------------------------------------------


def test_sem_canal_cloud_cai_no_numero_do_ambiente(db, loja_a):
    """A loja piloto não tem canal cadastrado e não pode parar de enviar."""
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    _vendedor(db, loja_id)

    oferta = abrir_oferta(db, loja_id, "5511988887777")
    fake = _OutboundFake()
    enviar_oferta(db, oferta, outbound=fake)

    assert fake.templates[0]["instance"] == PNID_AMBIENTE


def test_canal_evolution_sem_waba_nao_e_canal_cloud(db, loja_a):
    """Canal do Modo 1 na mesma loja não pode ser confundido com a central.

    Sem isto, uma loja que já tem instância Evolution mandaria o outbound Cloud
    para o nome da instância Baileys — e a Meta responderia 404.
    """
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            e164_or_label="legado",
            evolution_instance=f"inst-baileys-{loja_id[:8]}",
            ativo=True,
            estado=ESTADO_CONECTADO,
        )
    )
    db.commit()

    assert phone_number_id_da_loja(db, loja_id) == PNID_AMBIENTE


# --------------------------------------------------------------------------
# 3. template por WABA
# --------------------------------------------------------------------------


def test_template_de_oferta_vem_do_canal(db, loja_a):
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    _canal_cloud(db, loja_id, template="chama_vendedor_a")
    _vendedor(db, loja_id)

    oferta = abrir_oferta(db, loja_id, "5511988887777")
    fake = _OutboundFake()
    assert enviar_oferta(db, oferta, outbound=fake) == "template"

    assert fake.templates[0]["template"] == "chama_vendedor_a"
    assert fake.templates[0]["template"] != TEMPLATE_AMBIENTE


def test_canal_sem_template_cai_no_do_ambiente(db, loja_a):
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    pnid, _ = _canal_cloud(db, loja_id, template=None)
    _vendedor(db, loja_id)

    oferta = abrir_oferta(db, loja_id, "5511988887777")
    fake = _OutboundFake()
    enviar_oferta(db, oferta, outbound=fake)

    assert fake.templates[0]["instance"] == pnid
    assert fake.templates[0]["template"] == TEMPLATE_AMBIENTE


# --------------------------------------------------------------------------
# 4. duas lojas não se misturam
# --------------------------------------------------------------------------


def test_duas_lojas_nao_se_misturam_no_outbound(db, loja_a, loja_b):
    """O bug que motivou a tarefa: número e template cruzando entre lojas."""
    a, b = loja_a["loja_id"], loja_b["loja_id"]
    for loja_id in (a, b):
        _modo2(db, loja_id)
        _vendedor(db, loja_id)
    pnid_a, _ = _canal_cloud(db, a, rotulo="pnid-a", template="oferta_a")
    pnid_b, _ = _canal_cloud(db, b, rotulo="pnid-b", template="oferta_b")
    assert pnid_a != pnid_b

    fake = _OutboundFake()
    enviar_oferta(db, abrir_oferta(db, a, "5511988887777"), outbound=fake)
    enviar_oferta(db, abrir_oferta(db, b, "5511966665555"), outbound=fake)

    assert [t["instance"] for t in fake.templates] == [pnid_a, pnid_b]
    assert [t["template"] for t in fake.templates] == ["oferta_a", "oferta_b"]


def test_credenciais_sao_por_loja(db, loja_a, loja_b):
    a, b = loja_a["loja_id"], loja_b["loja_id"]
    pnid_a, waba_a = _canal_cloud(db, a, rotulo="pnid-a", template="oferta_a")
    pnid_b, waba_b = _canal_cloud(db, b, rotulo="pnid-b", template="oferta_b")

    cred_a = credenciais_cloud_da_loja(db, a)
    cred_b = credenciais_cloud_da_loja(db, b)

    assert (cred_a.phone_number_id, cred_a.waba_id) == (pnid_a, waba_a)
    assert (cred_b.phone_number_id, cred_b.waba_id) == (pnid_b, waba_b)
    assert template_oferta_da_loja(db, a) == "oferta_a"
    assert template_oferta_da_loja(db, b) == "oferta_b"


# --------------------------------------------------------------------------
# vocabulário de estado: Cloud entra, Modo 1 fica
# --------------------------------------------------------------------------


def test_estados_do_modo_1_continuam_validos():
    """Acréscimo, não troca: o Modo 1 depende dos quatro estados do QR."""
    for estado in (
        ESTADO_PENDENTE,
        ESTADO_CONECTADO,
        ESTADO_DESCONECTADO,
        ESTADO_INATIVO,
    ):
        assert estado in ESTADOS_VALIDOS


def test_estados_cloud_nao_colidem_com_os_do_qr():
    from app.whatsapp_provider import ESTADOS_MODO1, ESTADOS_MODO2

    assert ESTADOS_MODO1 & ESTADOS_MODO2 == frozenset()
    assert ESTADOS_MODO2 <= ESTADOS_VALIDOS
    # Cabe na coluna String(20).
    assert max(len(e) for e in ESTADOS_MODO2) <= 20
