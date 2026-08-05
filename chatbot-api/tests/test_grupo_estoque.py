from app import operacao


GRUPO = "120363001@g.us"
OUTRO_GRUPO = "120363999@g.us"


def _selecionar(client, loja):
    resposta = client.put(
        "/v1/operacao/grupo-estoque",
        json={"grupo_jid": GRUPO, "grupo_nome": "Equipe Estoque"},
        headers=loja["headers"],
    )
    assert resposta.status_code == 200, resposta.text


def test_configuracao_lista_seleciona_e_remove_grupo(
    client, loja_a, monkeypatch
):
    monkeypatch.setattr(
        "app.main.listar_grupos_whatsapp",
        lambda instance: [
            {"jid": GRUPO, "nome": "Equipe Estoque"},
            {"jid": OUTRO_GRUPO, "nome": "Vendas"},
        ],
    )

    inicial = client.get(
        "/v1/operacao/grupo-estoque", headers=loja_a["headers"]
    )
    assert inicial.status_code == 200
    assert inicial.json()["selecionado"] is None
    assert inicial.json()["grupos"][0]["nome"] == "Equipe Estoque"

    salva = client.put(
        "/v1/operacao/grupo-estoque",
        json={"grupo_jid": GRUPO},
        headers=loja_a["headers"],
    )
    assert salva.status_code == 200
    assert salva.json()["nome"] == "Equipe Estoque"

    atual = client.get(
        "/v1/operacao/grupo-estoque", headers=loja_a["headers"]
    ).json()
    assert atual["selecionado"]["jid"] == GRUPO

    removida = client.delete(
        "/v1/operacao/grupo-estoque", headers=loja_a["headers"]
    )
    assert removida.json() == {"removido": True, "jid": GRUPO}


def test_menu_funciona_no_grupo_e_sessao_e_compartilhada(client, loja_a, db):
    _selecionar(client, loja_a)

    menu = operacao.decidir_roteamento(
        db,
        loja_a["loja_id"],
        "5511999990001",
        "menu",
        None,
        grupo_jid=GRUPO,
    )
    assert menu["acao"] == "cadastro_controle"
    assert "1 -" in menu["resposta"]

    opcao_por_outro_participante = operacao.decidir_roteamento(
        db,
        loja_a["loja_id"],
        "5511999990002",
        "1",
        None,
        grupo_jid=GRUPO,
    )
    assert opcao_por_outro_participante["acao"] == "cadastro_controle"
    assert "dados" in opcao_por_outro_participante["resposta"].lower()


def test_endpoint_do_grupo_aceita_participante_lid(client, loja_a):
    _selecionar(client, loja_a)
    resposta = client.post(
        "/v1/operacao/roteamento",
        json={
            "instance": loja_a["instance"],
            "telefone": "1234567890123456@lid",
            "texto": "menu",
            "is_saved": None,
            "grupo_jid": GRUPO,
        },
    )
    assert resposta.status_code == 200
    assert resposta.json()["acao"] == "cadastro_controle"


def test_menu_ignora_privado_e_grupo_diferente_quando_configurado(
    client, loja_a, db
):
    client.post(
        "/v1/operacao/numeros-autorizados",
        json={"telefone": "5511999990001"},
        headers=loja_a["headers"],
    )
    _selecionar(client, loja_a)

    privado = operacao.decidir_roteamento(
        db, loja_a["loja_id"], "5511999990001", "menu", True
    )
    outro = operacao.decidir_roteamento(
        db,
        loja_a["loja_id"],
        "5511999990001",
        "menu",
        None,
        grupo_jid=OUTRO_GRUPO,
    )

    assert privado == {"acao": "ignorar", "resposta": None}
    assert outro == {"acao": "ignorar", "resposta": None}


def test_texto_livre_no_menu_do_grupo_nao_reenvia_menu(client, loja_a, db):
    """Anti-flood: conversa da equipe com sessão aberta não gera menu em loop."""
    _selecionar(client, loja_a)

    menu = operacao.decidir_roteamento(
        db,
        loja_a["loja_id"],
        "5511999990001",
        "menu",
        None,
        grupo_jid=GRUPO,
    )
    assert menu["acao"] == "cadastro_controle"

    livre = operacao.decidir_roteamento(
        db,
        loja_a["loja_id"],
        "5511999990002",
        "alguém viu a CG 160?",
        None,
        grupo_jid=GRUPO,
    )
    assert livre == {"acao": "ignorar", "resposta": None}

    # Opções válidas continuam respondendo com a sessão compartilhada.
    opcao = operacao.decidir_roteamento(
        db,
        loja_a["loja_id"],
        "5511999990002",
        "2",
        None,
        grupo_jid=GRUPO,
    )
    assert opcao["acao"] == "cadastro_controle"
    assert opcao["resposta"]
