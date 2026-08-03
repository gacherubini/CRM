"""Gate de histórico no roteamento: atende só lead virgem (não salvo E sem
conversa pré-bot), mas segue atendendo conversa que o bot já iniciou.

Regra (para número NÃO salvo):
  - já existe uma saída na conversa (alguém já respondeu) -> cliente (em andamento)
  - primeiro contato:
      chat_found True (histórico pré-bot no WhatsApp) -> ignorar
      senão (virgem, ou chat_found desconhecido) -> cliente (fail-open)
Salvo (is_saved True) ou desconhecido (None) -> ignorar, como hoje.
"""
import uuid

from app import operacao
from app.models_db import Conversa, Mensagem


def _criar_conversa(db, loja_id, telefone, *, saidas=0, entradas=1, bot_ativo=True):
    conv = Conversa(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone=telefone,
        canal_id=None,
        bot_ativo=bot_ativo,
        status="aberta",
    )
    db.add(conv)
    db.flush()
    for _ in range(entradas):
        db.add(Mensagem(id=str(uuid.uuid4()), loja_id=loja_id, conversa_id=conv.id, direcao="entrada", texto="oi"))
    for _ in range(saidas):
        db.add(Mensagem(id=str(uuid.uuid4()), loja_id=loja_id, conversa_id=conv.id, direcao="saida", texto="resp"))
    db.commit()
    return conv


def test_nao_salvo_virgem_atende(client, loja_a, db):
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000100", "oi", False, chat_found=False
    )
    assert d["acao"] == "cliente"


def test_nao_salvo_com_historico_prebot_ignora(client, loja_a, db):
    # primeiro contato + histórico no WhatsApp -> não atende (incômodo do dono)
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000101", "oi", False, chat_found=True
    )
    assert d["acao"] == "ignorar"


def test_nao_salvo_conversa_em_andamento_atende(client, loja_a, db):
    # bot já respondeu (existe saída) -> segue atendendo mesmo com chat_found
    _criar_conversa(db, loja_a["loja_id"], "5511970000102", saidas=1, entradas=2)
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000102", "blz", False, chat_found=True
    )
    assert d["acao"] == "cliente"


def test_nao_salvo_historico_sem_saida_continua_ignorando(client, loja_a, db):
    # só entradas, bot nunca respondeu + chat_found -> continua ignorando
    _criar_conversa(db, loja_a["loja_id"], "5511970000103", saidas=0, entradas=2)
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000103", "de novo", False, chat_found=True
    )
    assert d["acao"] == "ignorar"


def test_nao_salvo_chat_found_desconhecido_fail_open(client, loja_a, db):
    # Evolution cega (chat_found None) -> na dúvida atende
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000104", "oi", False, chat_found=None
    )
    assert d["acao"] == "cliente"


def test_salvo_continua_ignorando(client, loja_a, db):
    d = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511970000105", "oi", True, chat_found=False
    )
    assert d["acao"] == "ignorar"


def test_endpoint_chat_found_bloqueia_historico(client, loja_a):
    inst = loja_a["instance"]
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000106", "texto": "oi", "is_saved": False, "chat_found": True},
    )
    assert r.status_code == 200 and r.json()["acao"] == "ignorar"
    r = client.post(
        "/v1/operacao/roteamento",
        json={"instance": inst, "telefone": "5511970000107", "texto": "oi", "is_saved": False, "chat_found": False},
    )
    assert r.status_code == 200 and r.json()["acao"] == "cliente"
