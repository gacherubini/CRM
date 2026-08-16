from app.copiloto_sinais_job import sincronizar_ofertas
from app.loja.copiloto.sinais_store import contar_sinais_novos


class _ChatbotFake:
    def __init__(self, ofertas):
        self._ofertas = ofertas

    def listar_ofertas(self, estado=None):
        return self._ofertas


def test_oferta_aberta_vira_sinal_so_do_vendedor(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "fila-1", "vendedor_usuario_id": "u-v1",
        "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])

    assert sincronizar_ofertas(db, "loja-a", chatbot)["criados"] == 1
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 0


def test_rodar_duas_vezes_nao_duplica(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "fila-1", "vendedor_usuario_id": "u-v1",
        "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    assert sincronizar_ofertas(db, "loja-a", chatbot)["criados"] == 0
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1


def test_rodizio_avancou_transfere_o_sinal(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "fila-1", "vendedor_usuario_id": "u-v1",
        "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    chatbot._ofertas[0]["vendedor_id"] = "fila-2"
    chatbot._ofertas[0]["vendedor_usuario_id"] = "u-v2"
    chatbot._ofertas[0]["vendedor_nome"] = "Bruno"

    assert sincronizar_ofertas(db, "loja-a", chatbot)["transferidos"] == 1
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 0
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 1


def test_sinal_nunca_guarda_telefone_do_cliente(db):
    """Disciplina do model: sinal de lead é agregado, telefone não entra."""
    from app.models import CopilotoSinal

    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "fila-1", "vendedor_usuario_id": "u-v1",
        "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    sinal = db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "of-1").one()
    conteudo = f"{sinal.titulo}{sinal.detalhe}{sinal.dados_json or ''}"
    assert "5511988887777" not in conteudo


def _oferta(**extra):
    base = {
        "id": "of-vinc", "vendedor_id": "fila-uuid-1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }
    base.update(extra)
    return base


def test_destinatario_e_o_usuario_da_loja_nao_o_id_da_fila(db):
    """O sino compara com `Usuario.id` do Portal.

    `vendedor_id` é UUID do chatbot e nunca bate com usuário nenhum — usar
    ele endereçaria o sinal a um id que ninguém tem, e o sino ficaria vazio
    para todo mundo, inclusive para o vendedor da vez.
    """
    chatbot = _ChatbotFake([_oferta(vendedor_usuario_id="u-ana")])

    assert sincronizar_ofertas(db, "loja-v", chatbot)["criados"] == 1
    assert contar_sinais_novos(db, "loja-v", "u-ana") == 1
    assert contar_sinais_novos(db, "loja-v", "fila-uuid-1") == 0


def test_vendedor_sem_vinculo_nao_vira_sinal(db):
    """Melhor não tocar o sino do que endereçar a ninguém."""
    chatbot = _ChatbotFake([_oferta(vendedor_usuario_id=None)])

    assert sincronizar_ofertas(db, "loja-sv", chatbot)["criados"] == 0
    assert sincronizar_ofertas(db, "loja-sv", chatbot)["ignorados_sem_vinculo"] == 1


def test_transferencia_usa_o_usuario_da_loja(db):
    chatbot = _ChatbotFake([_oferta(vendedor_usuario_id="u-ana")])
    sincronizar_ofertas(db, "loja-t", chatbot)

    chatbot._ofertas[0]["vendedor_id"] = "fila-uuid-2"
    chatbot._ofertas[0]["vendedor_usuario_id"] = "u-bruno"

    assert sincronizar_ofertas(db, "loja-t", chatbot)["transferidos"] == 1
    assert contar_sinais_novos(db, "loja-t", "u-ana") == 0
    assert contar_sinais_novos(db, "loja-t", "u-bruno") == 1
