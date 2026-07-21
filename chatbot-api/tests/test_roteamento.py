"""Roteamento WhatsApp: cliente / ignorar / cadastro / controle de sessão."""
from datetime import datetime, timedelta, timezone

from app import operacao
from app.models_db import NumeroAutorizado


def _autorizar(client, loja, telefone, ativo=True):
    r = client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": telefone, "ativo": ativo},
        headers=loja["headers"],
    )
    assert r.status_code == 201, r.text


def test_nao_salvo_vai_para_cliente(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000000", "oi", False)
    assert d["acao"] == "cliente"


def test_salvo_nao_autorizado_ignora(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000001", "oi", True)
    assert d["acao"] == "ignorar"


def test_autorizado_sem_sessao_texto_normal_ignora(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000002")
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000002", "bom dia", True)
    assert d["acao"] == "ignorar"


def test_autorizado_gatilho_abre_sessao(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000003")
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000003", " Cadastro ", True)
    assert d["acao"] == "cadastro_controle"
    assert "aberto" in d["resposta"].lower()
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000003")
        .first()
    )
    assert row.cadastro_expira_em is not None


def test_dados_dentro_da_sessao_vao_para_cadastro(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000004")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000004", "cadastro", True)
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000004", "Honda CG 160 2023 placa ABC1D23", True
    )
    assert d["acao"] == "cadastro"


def test_fim_encerra_sessao(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000005")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000005", "cadastro", True)
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000005", "fim", True)
    assert d["acao"] == "cadastro_controle"
    assert "encerrado" in d["resposta"].lower()
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000005")
        .first()
    )
    assert row.cadastro_expira_em is None


def test_sessao_expirada_volta_a_ignorar(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000006")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000006", "cadastro", True)
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000006")
        .first()
    )
    row.cadastro_expira_em = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000006", "Honda CG 160", True
    )
    assert d["acao"] == "ignorar"


def test_is_saved_desconhecido_trata_como_salvo(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000007", "oi", None)
    assert d["acao"] == "ignorar"
