from app.loja.copiloto.sinais_store import contar_sinais_novos
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
