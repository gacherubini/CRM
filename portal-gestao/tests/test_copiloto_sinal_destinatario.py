from app.loja.copiloto.sinais_store import (
    contar_sinais_novos,
    criar_sinal_direcionado,
    listar_sinais_abertos,
    transferir_sinal,
)
from app.models import CopilotoSinal


def test_sinal_nasce_sem_destinatario():
    """NULL é o default: sinal continua sendo da loja inteira."""
    sinal = CopilotoSinal(
        loja_slug="loja-teste",
        regra="estoque_parado",
        severidade="info",
        titulo="t",
        detalhe="d",
    )
    assert sinal.destinatario_usuario_id is None


def test_sinal_aceita_destinatario():
    sinal = CopilotoSinal(
        loja_slug="loja-teste",
        regra="oferta_lead",
        severidade="atencao",
        titulo="t",
        detalhe="d",
        destinatario_usuario_id="u-vendedor-1",
    )
    assert sinal.destinatario_usuario_id == "u-vendedor-1"


def _sinal(db, loja, *, regra="estoque_parado", destinatario=None):
    sinal = CopilotoSinal(
        loja_slug=loja,
        regra=regra,
        severidade="info",
        titulo="t",
        detalhe="d",
        estado="novo",
        destinatario_usuario_id=destinatario,
    )
    db.add(sinal)
    db.commit()
    return sinal


def test_sinal_da_loja_conta_para_todo_mundo(db):
    _sinal(db, "loja-a")
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 1
    assert contar_sinais_novos(db, "loja-a", "u-vendedor") == 1


def test_sinal_direcionado_conta_so_para_o_dono_dele(db):
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")
    assert contar_sinais_novos(db, "loja-a", "u-vendedor") == 1
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 0


def test_direcionado_e_da_loja_somam_para_o_destinatario(db):
    _sinal(db, "loja-a")
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")
    assert contar_sinais_novos(db, "loja-a", "u-vendedor") == 2
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 1


def test_listagem_esconde_oferta_de_outro_vendedor(db):
    _sinal(db, "loja-a")
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")

    do_vendedor = listar_sinais_abertos(db, "loja-a", usuario_id="u-vendedor")
    do_dono = listar_sinais_abertos(db, "loja-a", usuario_id="u-dono")

    assert {s.regra for s in do_vendedor} == {"estoque_parado", "oferta_lead"}
    assert {s.regra for s in do_dono} == {"estoque_parado"}


def test_listagem_sem_usuario_devolve_tudo(db):
    """Compat: chamador que ainda não passa usuario_id não muda de resultado."""
    _sinal(db, "loja-a")
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")
    assert len(listar_sinais_abertos(db, "loja-a")) == 2


def test_criar_direcionado_so_aparece_para_o_destinatario(db):
    criar_sinal_direcionado(
        db,
        "loja-a",
        regra="oferta_lead",
        destinatario_usuario_id="u-v1",
        entidade_ref="oferta-123",
        titulo="Lead novo",
        detalhe="Cliente quer uma Biz 125",
    )
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 0


def test_transferir_passa_a_oferta_para_o_proximo(db):
    criar_sinal_direcionado(
        db,
        "loja-a",
        regra="oferta_lead",
        destinatario_usuario_id="u-v1",
        entidade_ref="oferta-123",
        titulo="Lead novo",
        detalhe="Cliente quer uma Biz 125",
    )

    assert transferir_sinal(
        db, "loja-a", entidade_ref="oferta-123",
        de_usuario_id="u-v1", para_usuario_id="u-v2",
    ) is True

    assert contar_sinais_novos(db, "loja-a", "u-v1") == 0
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 1


def test_transferir_sem_sinal_aberto_devolve_false(db):
    assert transferir_sinal(
        db, "loja-a", entidade_ref="oferta-inexistente",
        de_usuario_id="u-v1", para_usuario_id="u-v2",
    ) is False
