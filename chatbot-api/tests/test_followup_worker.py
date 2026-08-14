"""Worker do follow-up de silêncio (spec §5.9): 30 min → msg 1; +1 h → msg 2; para."""
from datetime import datetime, timedelta, timezone

import pytest

from app.followup_job import FollowupWorker
from app.models_db import Conversa, LojaOperacionalProjecao, Mensagem


def _projetar_modo2(db, loja_id):
    db.add(LojaOperacionalProjecao(
        loja_id=loja_id, aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-modo-{loja_id[:8]}",
    ))
    db.commit()


def _conversa(db, loja_id, *, telefone, ultima_direcao, minutos_atras, bot_ativo=True):
    sufixo = f"{loja_id[:8]}-{telefone}"
    c = Conversa(id=f"c-{sufixo}", loja_id=loja_id, telefone=telefone, bot_ativo=bot_ativo)
    db.add(c)
    db.add(Mensagem(
        id=f"m-{sufixo}", loja_id=loja_id, conversa_id=c.id,
        direcao=ultima_direcao, texto="oi",
        criada_em=datetime.now(timezone.utc) - timedelta(minutes=minutos_atras),
    ))
    db.commit()
    return c


class _OutboundFake:
    def __init__(self):
        self.textos = []

    def send_text(self, *, instance, number, text):
        self.textos.append((number, text))
        return {"messages": [{"id": "wamid.F"}]}


def test_silencio_de_30min_manda_o_primeiro_toque(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    c = _conversa(db, loja_a["loja_id"], telefone="5511900000001",
                  ultima_direcao="saida", minutos_atras=31)
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 1
    assert len(fake.textos) == 1
    db.refresh(c)
    assert c.followup_toques == 1


def test_silencio_curto_nao_cutuca(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    _conversa(db, loja_a["loja_id"], telefone="5511900000002",
              ultima_direcao="saida", minutos_atras=10)
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    assert fake.textos == []


def test_segundo_toque_so_uma_hora_depois_do_primeiro(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    c = _conversa(db, loja_a["loja_id"], telefone="5511900000003",
                  ultima_direcao="saida", minutos_atras=61)
    c.followup_toques = 1
    db.commit()
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 1
    db.refresh(c)
    assert c.followup_toques == 2


def test_nao_existe_terceiro_toque(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    c = _conversa(db, loja_a["loja_id"], telefone="5511900000004",
                  ultima_direcao="saida", minutos_atras=600)
    c.followup_toques = 2
    db.commit()
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    assert fake.textos == []


def test_cliente_respondeu_zera_o_relogio(db, loja_a, monkeypatch):
    """Spec §5.9: cliente responder no meio zera. A última mensagem é dele."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    c = _conversa(db, loja_a["loja_id"], telefone="5511900000005",
                  ultima_direcao="entrada", minutos_atras=90)
    c.followup_toques = 1
    db.commit()
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    db.refresh(c)
    assert c.followup_toques == 0
    assert fake.textos == []


def test_handoff_cancela_o_followup(db, loja_a, monkeypatch):
    """bot_ativo=False é o handoff: a central se cala (spec §5.9 item 4)."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    _conversa(db, loja_a["loja_id"], telefone="5511900000006",
              ultima_direcao="saida", minutos_atras=120, bot_ativo=False)
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    assert fake.textos == []


@pytest.mark.xfail(
    reason="loja_opera_modo2 ainda não checa o modo projetado; a terceira "
           "cláusula do gate é a Task 4 do card 4. Quando ela entrar, este "
           "teste vira XPASS — é o sinal de que o gate fechou.",
    strict=False,
)
def test_loja_fora_do_modo_2_nao_recebe_followup(db, loja_a, monkeypatch):
    """Follow-up é só do Modo 2 — o n8n-baileys não ganha cutucão (§13)."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _conversa(db, loja_a["loja_id"], telefone="5511900000007",
              ultima_direcao="saida", minutos_atras=120)
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    assert fake.textos == []
