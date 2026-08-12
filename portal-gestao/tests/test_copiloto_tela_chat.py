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


def test_botao_perguntar_tem_id_para_desabilitar_durante_o_turno(client, monkeypatch):
    """Hook que o JS usa para travar o composer enquanto um turno está em
    voo (fix round 1): sem este id o botão não pode ser desabilitado, e uma
    segunda pergunta poderia órfão o polling da primeira (ver template)."""
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/loja/copiloto")
    assert 'id="copiloto-enviar"' in r.text
    assert "definirPendente" in r.text
