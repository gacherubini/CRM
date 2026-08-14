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
