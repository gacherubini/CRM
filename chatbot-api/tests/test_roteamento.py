"""Roteamento WhatsApp: cliente / ignorar / menu de operação / cadastro."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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


def test_autorizado_gatilho_abre_menu(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000003")
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000003", " Cadastro ", True)
    assert d["acao"] == "cadastro_controle"
    assert "1 -" in d["resposta"] or "Cadastrar" in d["resposta"]
    row = (
        db.query(NumeroAutorizado)
        .filter(NumeroAutorizado.telefone == "5511970000003")
        .first()
    )
    assert row.cadastro_expira_em is not None
    assert row.operacao_modo == "menu"


def test_menu_comando_abre_igual(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000014")
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000014", "menu", True)
    assert d["acao"] == "cadastro_controle"
    assert "Despublicar" in d["resposta"] or "4 -" in d["resposta"]


def test_opcao_1_entra_modo_cadastrar(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000004")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000004", "cadastro", True)
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000004", "1", True)
    assert d["acao"] == "cadastro_controle"
    assert "cadastrar" in d["resposta"].lower() or "dados" in d["resposta"].lower()
    d2 = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000004", "Honda CG 160 2023 placa ABC1D23", True
    )
    assert d2["acao"] == "cadastro"


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
    assert row.operacao_modo is None


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


def test_is_saved_desconhecido_nao_autorizado_ignora(client, loja_a, db):
    d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000007", "oi", None)
    assert d["acao"] == "ignorar"


def test_autorizado_bate_com_ou_sem_ddi55(client, loja_a, db):
    _autorizar(client, loja_a, "51980336365")
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "555180336365", "cadastro", True
    )
    assert d["acao"] == "cadastro_controle"


def test_listar_chama_estoque(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000020")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000020", "menu", True)
    fake = MagicMock()
    fake.listar_veiculos.return_value = [
        {
            "placa": "ABC1D23",
            "marca": "Honda",
            "modelo": "CG",
            "ano_modelo": 2020,
            "preco": 10000,
            "status": "disponivel",
            "publicado": True,
        }
    ]
    with patch.object(operacao, "get_inventory_write_client", return_value=fake):
        d = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000020", "2", True)
    assert d["acao"] == "cadastro_controle"
    assert "ABC1D23" in d["resposta"]
    assert "Honda" in d["resposta"]
    fake.listar_veiculos.assert_called_once()


def test_despublicar_com_confirmacao(client, loja_a, db):
    _autorizar(client, loja_a, "5511970000021")
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000021", "menu", True)
    operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000021", "4", True)

    fake = MagicMock()
    fake.obter_por_placa.return_value = {
        "id": "v1",
        "placa": "ABC1D23",
        "marca": "Honda",
        "modelo": "CG",
        "ano_modelo": 2020,
        "preco": 10000,
        "status": "disponivel",
        "publicado": True,
    }
    fake.acao_veiculo.return_value = {
        "id": "v1",
        "placa": "ABC1D23",
        "marca": "Honda",
        "modelo": "CG",
        "ano_modelo": 2020,
        "preco": 10000,
        "status": "disponivel",
        "publicado": False,
    }
    with patch.object(operacao, "get_inventory_write_client", return_value=fake):
        d1 = operacao.decidir_roteamento(
            db, loja_a["loja_id"], "5511970000021", "ABC1D23", True
        )
        assert "SIM" in d1["resposta"].upper()
        d2 = operacao.decidir_roteamento(db, loja_a["loja_id"], "5511970000021", "sim", True)
    assert "despublicado" in d2["resposta"].lower()
    fake.acao_veiculo.assert_called_once_with("v1", "despublicar")


def test_endpoint_roteamento_fluxo(client, loja_a):
    inst = loja_a["instance"]
    client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "5511970000010"},
        headers=loja_a["headers"],
    )
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000011", "texto": "oi", "is_saved": False},
    )
    assert r.status_code == 200 and r.json()["acao"] == "cliente"
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000012", "texto": "oi", "is_saved": True},
    )
    assert r.status_code == 200 and r.json()["acao"] == "ignorar"
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000010", "texto": "cadastro", "is_saved": True},
    )
    assert r.json()["acao"] == "cadastro_controle"
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000010", "texto": "1", "is_saved": True},
    )
    assert r.json()["acao"] == "cadastro_controle"
    r = client.post(
        "/v1/operacao/roteamento",
        json={
            "instance": inst,
            "telefone": "5511970000010",
            "texto": "Honda CG 160 2023 ABC1D23",
            "is_saved": True,
        },
    )
    assert r.json()["acao"] == "cadastro"
