"""Read-model dos canais WhatsApp da Loja: estado técnico -> linguagem de loja."""
from app.loja.whatsapp_canais import montar_canais_view


def test_view_traduz_estados_para_linguagem_de_loja():
    view = montar_canais_view(
        [
            {"id": "c1", "e164_or_label": "linha 1", "evolution_instance": "i1",
             "ativo": True, "estado": "conectado"},
            {"id": "c2", "e164_or_label": "linha 2", "evolution_instance": "i2",
             "ativo": True, "estado": "pendente"},
            {"id": "c3", "e164_or_label": "linha 3", "evolution_instance": "i3",
             "ativo": True, "estado": "desconectado"},
            {"id": "c4", "e164_or_label": "linha 4", "evolution_instance": "i4",
             "ativo": False, "estado": "inativo"},
        ]
    )
    rotulos = [c.rotulo for c in view.canais]
    assert rotulos == [
        "Conectado",
        "Aguardando leitura do QR",
        "Caiu — reconectar",
        "Desativado",
    ]


def test_view_com_erro_nao_inventa_canais():
    view = montar_canais_view(None, erro="Chatbot indisponível")
    assert view.canais == ()
    assert view.erro == "Chatbot indisponível"
    assert view.pode_adicionar is False


def test_canal_inativo_nao_pode_conectar():
    view = montar_canais_view(
        [{"id": "c4", "e164_or_label": "x", "evolution_instance": "i4",
          "ativo": False, "estado": "inativo"}]
    )
    assert view.canais[0].pode_conectar is False
    assert view.canais[0].pode_desconectar is False


def test_multi_desabilitado_impede_adicionar():
    view = montar_canais_view([], multi_habilitado=False)
    assert view.pode_adicionar is False
