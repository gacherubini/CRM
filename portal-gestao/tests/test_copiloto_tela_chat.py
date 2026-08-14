from conftest import csrf_da_resposta, login

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


def _turno_pronto(usuario_id, pergunta="quanto vendi?", resposta="Você vendeu 2 motos."):
    db = SessionLocal()
    try:
        turno = criar_turno(
            db, loja_slug="loja-teste", usuario_id=usuario_id, pergunta=pergunta
        )
        concluir_turno(
            db,
            turno,
            resposta=resposta,
            passos=[
                {
                    "ferramenta": "vendas_resumo",
                    "argumentos": {},
                    "status": "ok",
                    "resumo": "ok",
                }
            ],
            tokens_entrada=1200,
            tokens_saida=40,
            custo_estimado="0.001",
        )
        return turno.conversa_id
    finally:
        db.close()


def test_tela_tem_campo_de_pergunta_e_csrf(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/loja/copiloto")
    assert 'name="pergunta"' in r.text
    assert csrf_da_resposta(r)


def test_tela_lista_conversas_anteriores(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _turno_pronto(_usuario_id(), pergunta="De onde veio a última venda?")
    r = client.get("/app/loja/copiloto")
    assert "De onde veio a última venda?" in r.text


def test_abrir_conversa_mostra_pergunta_e_resposta(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    conversa_id = _turno_pronto(_usuario_id())
    r = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}")
    assert "quanto vendi?" in r.text
    assert "Você vendeu 2 motos." in r.text


def test_resposta_mostra_o_bloco_de_fontes(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    conversa_id = _turno_pronto(_usuario_id())
    r = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}")
    assert "Fontes" in r.text
    assert "vendas" in r.text.lower()


def test_conversa_de_outro_usuario_nao_abre(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        alheia = criar_turno(
            db, loja_slug="loja-teste", usuario_id="outro-usuario", pergunta="segredo?"
        ).conversa_id
    finally:
        db.close()
    r = client.get(f"/app/loja/copiloto?conversa_id={alheia}")
    assert r.status_code == 200
    assert "segredo?" not in r.text


def test_tela_traz_o_endpoint_de_polling(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/loja/copiloto")
    assert "/app/loja/copiloto/turno/" in r.text
    assert "/app/loja/copiloto/perguntar" in r.text


def test_turno_sem_resposta_nao_vaza_a_string_none(client, monkeypatch):
    """I2: pendente/executando/cancelado não têm `resposta` nem
    `texto_parcial` — a rota manda None para o template, e o Jinja2Templates
    do FastAPI não tem finalize configurado, então `{{ turno.resposta }}`
    sem guarda renderiza o literal `None`."""
    _ligar(monkeypatch)
    login(client)
    usuario_id = _usuario_id()
    for estado in ("pendente", "executando", "cancelado"):
        db = SessionLocal()
        try:
            turno = criar_turno(
                db, loja_slug="loja-teste", usuario_id=usuario_id,
                pergunta=f"pergunta em estado {estado}?",
            )
            turno.estado = estado
            db.commit()
            conversa_id = turno.conversa_id
        finally:
            db.close()
        r = client.get(f"/app/loja/copiloto?conversa_id={conversa_id}")
        assert "None" not in r.text, f"estado={estado} vazou 'None' no HTML"


def test_botao_perguntar_tem_id_para_desabilitar_durante_o_turno(client, monkeypatch):
    """Hook que o JS usa para travar o composer enquanto um turno está em
    voo (fix round 1): sem este id o botão não pode ser desabilitado, e uma
    segunda pergunta poderia órfão o polling da primeira (ver template)."""
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/loja/copiloto")
    assert 'id="copiloto-enviar"' in r.text
    assert "definirPendente" in r.text


def test_js_grava_pergunta_no_formdata_antes_de_limpar_o_campo(client, monkeypatch):
    """Regressão: o JS limpava o textarea e desabilitava o campo, depois
    montava FormData. Campo vazio/disabled some do POST — o servidor
    devolve 400 'Escreva uma pergunta.' com a bolha já mostrando o texto."""
    _ligar(monkeypatch)
    login(client)
    js = client.get("/app/loja/copiloto").text
    assert "corpo.set('pergunta', pergunta)" in js
    assert js.index("corpo.set('pergunta', pergunta)") < js.index("campo.value = ''")
    assert js.index("corpo.set('pergunta', pergunta)") < js.index("definirPendente(true)")


def test_tela_nao_carrega_fonte_externa_nem_capa_claude(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert "Fraunces" not in html
    assert "copiloto-body" not in html
    assert "copiloto-page" not in html


def test_sugestoes_sao_botoes_com_a_pergunta(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    html = client.get("/app/loja/copiloto").text
    assert 'class="chip" data-pergunta=' in html
    assert "Perguntas frequentes" not in html
