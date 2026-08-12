import json

from app.loja.copiloto.conversas import (
    atualizar_progresso,
    cancelar_turno,
    concluir_turno,
    criar_turno,
    falhar_turno,
    listar_conversas,
    listar_turnos,
    obter_turno,
)
from app.models import CopilotoConversa, CopilotoTurno


def test_criar_turno_abre_conversa_e_titula_pela_pergunta(db):
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1",
        pergunta="De onde veio a última moto que eu vendi?",
    )
    assert turno.estado == "pendente"
    conversa = db.get(CopilotoConversa, turno.conversa_id)
    assert conversa.loja_slug == "loja-teste"
    assert conversa.titulo.startswith("De onde veio")


def test_segundo_turno_reusa_a_conversa(db):
    primeiro = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    segundo = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="e o mês passado?",
        conversa_id=primeiro.conversa_id,
    )
    assert segundo.conversa_id == primeiro.conversa_id
    assert db.query(CopilotoConversa).count() == 1
    assert len(listar_turnos(db, "loja-teste", primeiro.conversa_id)) == 2


def test_listar_turnos_de_outra_loja_nao_vaza(db):
    """conversa_id sozinho não pode autorizar leitura entre lojas."""
    turno = criar_turno(db, loja_slug="loja-a", usuario_id="u1", pergunta="segredo?")
    assert listar_turnos(db, "loja-b", turno.conversa_id) == []
    assert len(listar_turnos(db, "loja-a", turno.conversa_id)) == 1


def test_progresso_grava_passos_e_texto_parcial(db):
    turno = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    atualizar_progresso(
        db, turno, estado="executando",
        passos=[{"ferramenta": "vendas_resumo", "status": "ok"}],
        texto_parcial="Você vendeu",
    )
    db.refresh(turno)
    assert turno.estado == "executando"
    assert json.loads(turno.passos_json)[0]["ferramenta"] == "vendas_resumo"
    assert turno.texto_parcial == "Você vendeu"


def test_concluir_grava_resposta_e_tokens(db):
    turno = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    concluir_turno(
        db, turno, resposta="Você vendeu 2 motos.", passos=[],
        tokens_entrada=1200, tokens_saida=40, custo_estimado="0.0010",
    )
    db.refresh(turno)
    assert turno.estado == "pronto"
    assert turno.tokens_entrada == 1200
    assert turno.concluido_em is not None


def test_turno_que_falha_ainda_grava_tokens(db):
    """Sem isto, o log de perguntas mente sobre o consumo real."""
    turno = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    falhar_turno(db, turno, erro_code="deadline", tokens_entrada=900, tokens_saida=10)
    db.refresh(turno)
    assert turno.estado == "erro"
    assert turno.erro_code == "deadline"
    assert turno.tokens_entrada == 900


def test_obter_turno_de_outra_loja_devolve_none(db):
    turno = criar_turno(db, loja_slug="loja-a", usuario_id="u1", pergunta="a?")
    assert obter_turno(db, "loja-b", turno.id) is None
    assert obter_turno(db, "loja-a", turno.id) is not None


def test_cancelar_turno_pendente(db):
    turno = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    assert cancelar_turno(db, "loja-teste", turno.id) is True
    db.refresh(turno)
    assert turno.estado == "cancelado"


def test_cancelar_turno_ja_pronto_nao_faz_nada(db):
    turno = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    concluir_turno(
        db, turno, resposta="ok", passos=[], tokens_entrada=1, tokens_saida=1,
        custo_estimado="0",
    )
    assert cancelar_turno(db, "loja-teste", turno.id) is False


def test_listar_conversas_so_do_usuario_e_da_loja(db):
    criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    criar_turno(db, loja_slug="loja-teste", usuario_id="u2", pergunta="b?")
    criar_turno(db, loja_slug="outra", usuario_id="u1", pergunta="c?")
    assert len(listar_conversas(db, "loja-teste", "u1")) == 1


def test_pergunta_muito_longa_e_recusada(db):
    import pytest

    with pytest.raises(ValueError):
        criar_turno(
            db, loja_slug="loja-teste", usuario_id="u1", pergunta="x" * 4001
        )
