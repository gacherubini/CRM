"""Liga/desliga por loja e janela de horário (spec §4.6). Fuso: America/Sao_Paulo."""
from datetime import datetime, timezone

from app import agente_config
from app.agente_prompt import CamposAgente


def _publicar(db, loja_id, **over):
    campos = CamposAgente(nome_loja="X", cidade="Y", uf="SP", **over)
    agente_config.salvar_rascunho(db, loja_id, campos, autor="t")
    agente_config.publicar(db, loja_id, autor="t")


def test_agente_desligado_nao_responde(client, db, loja_a):
    """`instance` é obrigatório no corpo: PodeResponderInput tem extra='forbid'."""
    _publicar(db, loja_a["loja_id"], agente_ativo=False)
    r = client.post(
        "/v1/conversas/5519999999999/pode-responder",
        json={"instance": loja_a["instance"], "provider_message_id": "m1"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 200
    assert r.json()["pode_responder"] is False
    assert r.json()["motivo"] == "agente_desligado"


def test_agente_ligado_segue_o_fluxo_normal(client, db, loja_a):
    _publicar(db, loja_a["loja_id"], agente_ativo=True)
    r = client.post(
        "/v1/conversas/5519999999999/pode-responder",
        json={"instance": loja_a["instance"], "provider_message_id": "m2"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 200
    assert r.json().get("motivo") != "agente_desligado"


def test_loja_sem_config_nenhuma_responde_normalmente(client, db, loja_b):
    """Protege o default: campos_publicados cai em CAMPOS_PADRAO_REVY quando a loja
    nunca publicou config, e agente_ativo=True nesse padrão. Quebrar isto deixa o
    bot mudo em produção para toda loja que nunca configurou o agente."""
    r = client.post(
        "/v1/conversas/5519999999999/pode-responder",
        json={"instance": loja_b["instance"], "provider_message_id": "m3"},
        headers=loja_b["headers"],
    )
    assert r.status_code == 200
    assert r.json().get("motivo") != "agente_desligado"
    assert r.json().get("motivo") != "fora_de_horario"


def test_fora_do_horario_quando_a_loja_pediu_so_comercial(db):
    """14h de uma terça está dentro; 23h não. Fuso fixo America/Sao_Paulo."""
    campos = CamposAgente(
        nome_loja="X", cidade="Y", uf="SP",
        so_horario_comercial=True,
        horario={"ter": ["08:00", "18:00"]},
    )
    dentro = datetime(2026, 8, 25, 17, 0, tzinfo=timezone.utc)   # 14h em SP
    fora = datetime(2026, 8, 26, 2, 0, tzinfo=timezone.utc)      # 23h de terça em SP
    assert agente_config.esta_em_horario(campos, dentro) is True
    assert agente_config.esta_em_horario(campos, fora) is False


def test_sem_grade_de_horario_atende_sempre(db):
    campos = CamposAgente(nome_loja="X", cidade="Y", uf="SP", so_horario_comercial=True)
    assert agente_config.esta_em_horario(campos, datetime.now(timezone.utc)) is True
