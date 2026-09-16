"""Painel ao vivo do rodízio em `/app/loja/whatsapp/fila`.

O agora é estado vivo do motor (ofertas abertas do Chatbot), não cadastro:
quem está com lead, há quanto tempo, e para quem passa quando o prazo real
estourar. Nada aqui é fictício — a tela lê `/v1/ofertas` a cada abertura e o
countdown parte do `prazo_em` que o motor gravou.
"""
from datetime import datetime, timedelta, timezone

from conftest import ligar_modo_2, login

from app.loja.rodizio_agora import (
    formatar_decorrido,
    formatar_restante,
    montar_agora,
    proximo_livre,
)

TELA = "/app/loja/whatsapp/fila"
ESTADO = "/app/loja/whatsapp/fila/estado.json"


def _ligar(monkeypatch, whatsapp="1", shell="1"):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", shell)
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", whatsapp)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


def _entrar(client, **kwargs):
    resposta = login(client, **kwargs)
    ligar_modo_2(kwargs.get("loja_slug", "loja-teste"))
    return resposta


def _fila_ana_bruno(chatbot_fake):
    chatbot_fake.fila_vendedores = [
        {"id": "f0", "nome": "Ana", "telefone": "5511999990000", "ordem": 0,
         "ativo": True, "usuario_id": "u-ana"},
        {"id": "f1", "nome": "Bruno", "telefone": "5511988887777", "ordem": 1,
         "ativo": True, "usuario_id": None},
    ]


def _oferta_aberta(vendedor_id, nome, minutos_atras=5, minutos_prazo=5):
    agora = datetime.now(timezone.utc)
    return {
        "id": f"of-{vendedor_id}",
        "telefone_cliente": "5511977776666",
        "vendedor_id": vendedor_id,
        "vendedor_nome": nome,
        "vendedor_usuario_id": None,
        "estado": "aberta",
        "prazo_em": (agora + timedelta(minutes=minutos_prazo)).isoformat(),
        "criado_em": (
            agora - timedelta(minutes=minutos_atras, seconds=10)
        ).isoformat(),
    }


def test_agora_mostra_quem_esta_com_lead(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    chatbot_fake.ofertas = [_oferta_aberta("f0", "Ana")]
    corpo = client.get(TELA).text
    assert "Agora no rodízio" in corpo
    assert "com o lead agora" in corpo
    assert "há 5 min" in corpo
    # O próximo é quem segue na ordem — e o prazo real chega ao countdown.
    assert "passa para" in corpo and "Bruno" in corpo
    assert "data-prazo=" in corpo
    # Ordem da fila preservada no carrossel: Ana antes de Bruno.
    assert corpo.index("1º: Ana") < corpo.index("2º: Bruno")


def test_agora_calmo_aponta_o_primeiro_da_vez(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    corpo = client.get(TELA).text
    assert "Nenhum cliente pedindo atendimento agora" in corpo
    assert "primeiro da vez" in corpo


def test_proximo_pula_quem_ja_tem_lead(client, chatbot_fake, monkeypatch):
    """Dois leads abertos: o próximo livre de cada um é quem não tem nenhum."""
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    chatbot_fake.fila_vendedores.append(
        {"id": "f2", "nome": "Carlos", "telefone": "5511977776666", "ordem": 2,
         "ativo": True, "usuario_id": None},
    )
    chatbot_fake.ofertas = [
        _oferta_aberta("f0", "Ana"),
        _oferta_aberta("f1", "Bruno"),
    ]
    corpo = client.get(TELA).text
    assert corpo.count("com o lead agora") == 2
    assert "passa para <strong>Carlos</strong>" in corpo


def test_oferta_de_quem_saiu_nao_some_da_tela(client, chatbot_fake, monkeypatch):
    """Remoção é lógica: a oferta continua viva e a tela mostra fora da fila."""
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    chatbot_fake.ofertas = [_oferta_aberta("fx", "Zé")]
    corpo = client.get(TELA).text
    assert "Fora da fila" in corpo


def test_esperando_vendedor_linka_o_atendimento(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    esgotada = _oferta_aberta("f0", "Ana")
    esgotada["estado"] = "esgotada"
    chatbot_fake.ofertas = [esgotada]
    corpo = client.get(TELA).text
    assert "espera um vendedor" in corpo
    assert "/app/loja/atendimento?estado=aguardando_vendedor" in corpo


def test_ofertas_fora_do_ar_nao_derrubam_a_tela(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    chatbot_fake.ofertas_indisponivel = True
    resposta = client.get(TELA)
    assert resposta.status_code == 200
    assert "Não deu para ver o agora" in resposta.text
    # O cadastro continua renderizando — só o ao vivo some.
    assert "Quem atende" in resposta.text


def test_estado_json_assinatura_muda_com_oferta(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    _entrar(client)
    _fila_ana_bruno(chatbot_fake)
    antes = client.get(ESTADO)
    assert antes.status_code == 200
    assert antes.json()["abertas"] == 0
    chatbot_fake.ofertas = [_oferta_aberta("f0", "Ana")]
    depois = client.get(ESTADO)
    assert depois.json()["abertas"] == 1
    assert depois.json()["assinatura"] != antes.json()["assinatura"]


def test_estado_json_negado_para_quem_nao_e_gestao(
    client, chatbot_fake, monkeypatch
):
    _ligar(monkeypatch)
    _entrar(client, papel="vendedor", email="vend@loja.test")
    resposta = client.get(ESTADO)
    assert resposta.status_code == 403
    assert resposta.json() == {"erro": "nao_autorizado"}


def test_estado_json_503_com_chatbot_fora(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    _entrar(client)
    chatbot_fake.fila_indisponivel = True
    resposta = client.get(ESTADO)
    assert resposta.status_code == 503


# View-model puro: determinístico, sem HTTP.


def _fila3():
    return [
        {"id": "a", "nome": "Ana"},
        {"id": "b", "nome": "Bruno"},
        {"id": "c", "nome": "Carlos"},
    ]


def test_proximo_livre_e_circular():
    assert proximo_livre(_fila3(), depois_de="c", ocupados=set())["id"] == "a"


def test_proximo_livre_pula_ocupado():
    fila = _fila3()
    assert proximo_livre(fila, depois_de="a", ocupados={"b"})["id"] == "c"
    assert proximo_livre(fila, depois_de="a", ocupados={"b", "c"})["id"] == "a"


def test_proximo_livre_todo_mundo_ocupado():
    assert (
        proximo_livre(_fila3(), depois_de="a", ocupados={"a", "b", "c"}) is None
    )


def test_formatos_de_tempo():
    assert formatar_decorrido(40) == "há 40 s"
    assert formatar_decorrido(300) == "há 5 min"
    assert formatar_decorrido(3700) == "há 1 h 01 min"
    assert formatar_restante(272) == "4:32"
    assert formatar_restante(-3) == "0:00"


def test_montar_agora_calcula_restante_e_progresso():
    agora = datetime(2026, 9, 16, 12, 5, tzinfo=timezone.utc)
    ofertas = [
        {
            "id": "of-a",
            "telefone_cliente": "5511977776666",
            "vendedor_id": "a",
            "vendedor_nome": "Ana",
            "estado": "aberta",
            "criado_em": "2026-09-16T12:00:00+00:00",
            "prazo_em": "2026-09-16T12:10:00+00:00",
        }
    ]
    visao = montar_agora(_fila3(), ofertas, agora=agora)
    assert visao["abertas"] == 1
    ana, bruno, _carlos = visao["cartoes"]
    assert ana["estado"] == "com_lead"
    (linha,) = ana["ofertas"]
    assert linha["decorrido"] == "há 5 min"
    assert linha["restante"] == "5:00"
    assert linha["progresso_pct"] == 50.0
    assert linha["proximo_nome"] == "Bruno"
    assert linha["cliente_curto"] == "6666"
    assert bruno["estado"] == "aguardando"
    assert visao["orfas"] == []
