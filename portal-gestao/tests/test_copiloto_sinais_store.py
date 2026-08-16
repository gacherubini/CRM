import json
from datetime import datetime, timedelta, timezone

from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import (
    contar_sinais_novos,
    dispensar,
    listar_sinais_abertos,
    marcar_visto,
    sincronizar_sinais,
)
from app.models import CopilotoSinal, CopilotoSinalVisto

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _cand(entidade="v1", titulo="Parada há 70 dias", regra="estoque_parado"):
    return SinalCandidato(
        regra=regra,
        severidade="atencao",
        titulo=titulo,
        detalhe="R$ 25.000,00 de capital preso.",
        entidade_ref=entidade,
        dados={"veiculo_id": entidade},
        acao_sugerida={"acao": "ajustar_preco", "veiculo_id": entidade},
    )


def test_cria_sinal_novo(db):
    r = sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    assert r.criados == 1
    sinal = db.query(CopilotoSinal).one()
    assert sinal.estado == "novo"
    assert json.loads(sinal.acao_sugerida_json)["acao"] == "ajustar_preco"


def test_segunda_passada_atualiza_em_vez_de_duplicar(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    r = sincronizar_sinais(
        db, "loja-teste", [_cand(titulo="Parada há 71 dias")],
        agora=AGORA + timedelta(days=1),
    )
    assert r.criados == 0
    assert r.atualizados == 1
    assert db.query(CopilotoSinal).count() == 1
    assert db.query(CopilotoSinal).one().titulo == "Parada há 71 dias"


def test_condicao_que_sai_resolve_o_sinal_sozinho(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    r = sincronizar_sinais(db, "loja-teste", [], agora=AGORA + timedelta(hours=1))
    assert r.resolvidos == 1
    sinal = db.query(CopilotoSinal).one()
    assert sinal.estado == "resolvido"
    assert sinal.resolvido_em is not None


def test_resolvido_nao_reabre_dentro_do_cooldown(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    sincronizar_sinais(db, "loja-teste", [], agora=AGORA + timedelta(hours=1))
    r = sincronizar_sinais(
        db, "loja-teste", [_cand()], agora=AGORA + timedelta(hours=2),
        cooldown_horas=24,
    )
    assert r.criados == 0
    assert r.em_cooldown == 1


def test_resolvido_reabre_depois_do_cooldown(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    sincronizar_sinais(db, "loja-teste", [], agora=AGORA + timedelta(hours=1))
    r = sincronizar_sinais(
        db, "loja-teste", [_cand()], agora=AGORA + timedelta(hours=30),
        cooldown_horas=24,
    )
    assert r.criados == 1


def test_dispensado_nunca_volta(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert dispensar(db, "loja-teste", sinal.id) is True
    r = sincronizar_sinais(
        db, "loja-teste", [_cand()], agora=AGORA + timedelta(days=30)
    )
    assert r.criados == 0
    assert r.dispensados_ignorados == 1


def test_nao_mexe_em_sinal_de_outra_loja(db):
    sincronizar_sinais(db, "loja-a", [_cand()], agora=AGORA)
    r = sincronizar_sinais(db, "loja-b", [], agora=AGORA + timedelta(hours=1))
    assert r.resolvidos == 0
    assert db.query(CopilotoSinal).one().estado == "novo"


def test_dispensar_de_outra_loja_nao_funciona(db):
    sincronizar_sinais(db, "loja-a", [_cand()], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert dispensar(db, "loja-b", sinal.id) is False
    assert db.query(CopilotoSinal).one().estado == "novo"


def test_listar_abertos_ignora_resolvido_e_dispensado(db):
    sincronizar_sinais(
        db, "loja-teste", [_cand("v1"), _cand("v2"), _cand("v3")], agora=AGORA
    )
    alvo = (
        db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "v2").one()
    )
    dispensar(db, "loja-teste", alvo.id)
    sincronizar_sinais(
        db, "loja-teste", [_cand("v1")], agora=AGORA + timedelta(hours=1)
    )
    abertos = listar_sinais_abertos(db, "loja-teste")
    assert [s.entidade_ref for s in abertos] == ["v1"]


def test_contador_de_novos_cai_so_para_quem_marcou_visto(db):
    """Visto é por pessoa: A marca, a contagem de A cai e a de B não."""
    sincronizar_sinais(db, "loja-teste", [_cand("v1"), _cand("v2")], agora=AGORA)
    assert contar_sinais_novos(db, "loja-teste", "user-a") == 2
    assert contar_sinais_novos(db, "loja-teste", "user-b") == 2
    sinal = (
        db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "v1").one()
    )
    assert marcar_visto(db, "loja-teste", sinal.id, "user-a") is True
    assert contar_sinais_novos(db, "loja-teste", "user-a") == 1
    assert contar_sinais_novos(db, "loja-teste", "user-b") == 2
    # Visto continua aberto na lista — só sai do contador.
    assert len(listar_sinais_abertos(db, "loja-teste")) == 2


def test_dispensar_some_para_todos_apos_visto_de_um(db):
    """Dispensar segue sendo da loja: some do contador dos dois, não só de A."""
    sincronizar_sinais(db, "loja-teste", [_cand("v1")], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert marcar_visto(db, "loja-teste", sinal.id, "user-a") is True
    assert dispensar(db, "loja-teste", sinal.id) is True
    assert contar_sinais_novos(db, "loja-teste", "user-a") == 0
    assert contar_sinais_novos(db, "loja-teste", "user-b") == 0


def test_marcar_visto_duas_vezes_nao_duplica_linha(db):
    sincronizar_sinais(db, "loja-teste", [_cand("v1")], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert marcar_visto(db, "loja-teste", sinal.id, "user-a") is True
    assert marcar_visto(db, "loja-teste", sinal.id, "user-a") is True
    assert (
        db.query(CopilotoSinalVisto)
        .filter(
            CopilotoSinalVisto.sinal_id == sinal.id,
            CopilotoSinalVisto.usuario_id == "user-a",
        )
        .count()
        == 1
    )


def test_marcar_visto_de_sinal_de_outra_loja_nao_e_aceito(db):
    sincronizar_sinais(db, "loja-a", [_cand("v1")], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert marcar_visto(db, "loja-b", sinal.id, "user-a") is False
    assert db.query(CopilotoSinalVisto).count() == 0
    # loja-a continua sem o registro de visto — a chamada com loja errada
    # não deixa rastro nenhum, nem para a loja certa.
    assert contar_sinais_novos(db, "loja-a", "user-a") == 1


def test_contar_sinais_novos_filtra_por_regras_elegiveis(db):
    sincronizar_sinais(
        db,
        "loja-teste",
        [_cand("v1", regra="estoque_parado"), _cand("v2", regra="lead_sem_resposta")],
        agora=AGORA,
    )
    assert contar_sinais_novos(db, "loja-teste", "user-a") == 2
    assert (
        contar_sinais_novos(
            db, "loja-teste", "user-a", regras=frozenset({"estoque_parado"})
        )
        == 1
    )
