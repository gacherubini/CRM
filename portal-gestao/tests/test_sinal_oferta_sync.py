from app.copiloto_sinais_job import sincronizar_ofertas
from app.loja.copiloto.sinais_store import contar_sinais_novos


class _ChatbotFake:
    def __init__(self, ofertas):
        self._ofertas = ofertas

    def listar_ofertas(self, estado=None):
        return self._ofertas


def test_oferta_aberta_vira_sinal_so_do_vendedor(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])

    assert sincronizar_ofertas(db, "loja-a", chatbot)["criados"] == 1
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 0


def test_rodar_duas_vezes_nao_duplica(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    assert sincronizar_ofertas(db, "loja-a", chatbot)["criados"] == 0
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1


def test_rodizio_avancou_transfere_o_sinal(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    chatbot._ofertas[0]["vendedor_id"] = "u-v2"
    chatbot._ofertas[0]["vendedor_nome"] = "Bruno"

    assert sincronizar_ofertas(db, "loja-a", chatbot)["transferidos"] == 1
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 0
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 1


def test_sinal_nunca_guarda_telefone_do_cliente(db):
    """Disciplina do model: sinal de lead é agregado, telefone não entra."""
    from app.models import CopilotoSinal

    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    sinal = db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "of-1").one()
    conteudo = f"{sinal.titulo}{sinal.detalhe}{sinal.dados_json or ''}"
    assert "5511988887777" not in conteudo
