"""A tela renderiza um subconjunto de markdown em nós de DOM.

O contrato tem DUAS pontas e elas têm que casar: o prompt promete ao modelo
que negrito/lista/tabela aparecem formatados (prompt.py, FORMATO_RESPOSTA), e
o renderizador do template é quem cumpre. Se alguém ampliar um lado sem o
outro, a marcação nova vaza literal na bolha do dono.
"""
from conftest import login

from app.db import SessionLocal
from app.loja.copiloto.conversas import concluir_turno, criar_turno


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _usuario_id():
    from app.models import Usuario

    db = SessionLocal()
    try:
        return db.query(Usuario).filter(Usuario.email == "dono@loja.test").one().id
    finally:
        db.close()


def test_pagina_traz_o_renderizador_de_markdown(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "function renderizarMarkdown" in html


def test_renderizador_nunca_usa_innerhtml(client, monkeypatch):
    """Invariante de segurança: o Copiloto monta DOM com createElement +
    textContent. innerHTML reabriria o XSS que o cartão de ação fechou.

    Checa o uso real (``.innerHTML``), não o comentário do template — o
    comentário de 14 linhas cita a palavra de propósito, e o base.html também.
    """
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert ".innerHTML" not in html


def test_resposta_e_um_bloco_e_nao_um_paragrafo(client, monkeypatch):
    """Lista e tabela não podem viver dentro de <p> — o parser do navegador
    fecha o parágrafo sozinho e o CSS do avatar (::before) perde a âncora."""
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=_usuario_id(),
            pergunta="ranking?",
        )
        concluir_turno(
            db, turno, resposta="- Ana: 3\n- Bruno: 2", passos=[],
            tokens_entrada=10, tokens_saida=5, custo_estimado="0.001",
        )
        conversa_id = turno.conversa_id
    finally:
        db.close()
    html = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}").text
    assert '<div class="copiloto-resposta"' in html
    assert '<p class="copiloto-resposta"' not in html


def test_pagina_revela_a_resposta_progressivamente(client, monkeypatch):
    """A resposta não pode aparecer de uma vez: 10-45s de 'Pensando…' e um
    bloco de texto piscando é o que faz o Copiloto parecer formulário lento."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "function revelar" in html
    assert "requestAnimationFrame" in html


def test_indicador_de_pensando_vive_dentro_da_lista_de_mensagens(client, monkeypatch):
    """Bolha vazia com avatar + legenda flutuante fora do scroll = dois
    indicadores para um estado só."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert 'id="copiloto-pensando"' not in html
    assert "copiloto-resposta pensando" in html or "classList.add('pensando')" in html


def test_composer_continua_editavel_durante_o_turno(client, monkeypatch):
    """Travar o campo derruba o foco no body e impede rascunhar a proxima
    pergunta. A guarda de um-turno-por-vez passa a ser no submit."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "campo.disabled = pendente" not in html
    assert "emVoo" in html


def test_textarea_cresce_com_o_texto(client, monkeypatch):
    """rows=1 + resize:none sem auto-grow faz a pergunta longa rolar dentro
    de uma linha. O max-height: 9rem do CSS hoje e codigo morto."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "function ajustarAltura" in html


def test_polling_tolera_falha_transitoria(client, monkeypatch):
    """Uma sondagem falha nao pode declarar derrota: o worker segue rodando e
    a resposta vai cair no banco. Declarar erro ai e mentir para o dono."""
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "FALHAS_ATE_DESISTIR" in html
    assert "continua sendo processada" in html


def test_erro_tem_palavra_e_saida_nao_so_cor(client, monkeypatch):
    """PRODUCT.md, compromisso vinculante: cor nunca comunica sozinha."""
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=_usuario_id(), pergunta="e ai?",
        )
        turno.estado = "erro"
        turno.resposta = "O provedor não respondeu."
        db.commit()
        conversa_id = turno.conversa_id
    finally:
        db.close()
    html = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}").text
    assert "Não deu certo" in html
    assert "Tentar de novo" in html
