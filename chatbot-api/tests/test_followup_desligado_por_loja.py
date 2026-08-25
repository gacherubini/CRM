"""Interruptor do follow-up por loja (spec §4.4.2). Só Modo 2, como o worker já era."""
from datetime import datetime, timedelta, timezone

from app import agente_config
from app.agente_prompt import CamposAgente
from app.followup_job import FollowupWorker
from app.models_db import Conversa, LojaOperacionalProjecao, Mensagem


def _projetar_modo2(db, loja_id):
    db.add(LojaOperacionalProjecao(
        loja_id=loja_id, aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-modo-{loja_id[:8]}",
    ))
    db.commit()


def _conversa_calada(db, loja_id, telefone):
    sufixo = f"{loja_id[:8]}-{telefone}"
    c = Conversa(id=f"c-{sufixo}", loja_id=loja_id, telefone=telefone, bot_ativo=True)
    db.add(c)
    db.add(Mensagem(
        id=f"m-{sufixo}", loja_id=loja_id, conversa_id=c.id,
        direcao="saida", texto="oi",
        criada_em=datetime.now(timezone.utc) - timedelta(minutes=31),
    ))
    db.commit()
    return c


class _OutboundFake:
    def __init__(self):
        self.textos = []

    def send_text(self, *, instance, number, text):
        self.textos.append((number, text))
        return {"messages": [{"id": "wamid.F"}]}


def _config(db, loja_id, *, ligado: bool):
    campos = CamposAgente(nome_loja="X", cidade="Y", uf="SP", followup_ativo=ligado)
    agente_config.salvar_rascunho(db, loja_id, campos, autor="t")
    agente_config.publicar(db, loja_id, autor="t")


def test_loja_com_followup_desligado_nao_recebe_toque(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    _conversa_calada(db, loja_a["loja_id"], "5511900000010")
    _config(db, loja_a["loja_id"], ligado=False)
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    assert fake.textos == []


def test_loja_sem_config_continua_recebendo(db, loja_a, monkeypatch):
    """Default é ligado: nenhuma loja perde follow-up por não ter configurado."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    _conversa_calada(db, loja_a["loja_id"], "5511900000011")
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 1
    assert len(fake.textos) == 1
