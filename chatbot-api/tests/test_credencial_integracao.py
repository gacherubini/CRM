"""Credencial de integração: token da plataforma, sem loja (spec §6.2).

A loja de cada pedido vem da instância, não do token — ver o card
docs/fila/2026-08-23-modo2-multiloja-credencial-de-integracao.md.
"""
from app import servico
from app.auth import hash_token
from app.models_db import CredencialServico


def test_credencial_integracao_nasce_sem_loja(db):
    token = servico.criar_credencial_integracao(db)

    cred = db.get(CredencialServico, hash_token(token))
    assert cred is not None
    assert cred.loja_id is None
    assert cred.papel == "integracao"


def test_token_da_integracao_nao_se_repete(db):
    """Duas chamadas, dois tokens: o segredo é por credencial, não global."""
    assert servico.criar_credencial_integracao(db) != servico.criar_credencial_integracao(db)


def test_credencial_de_loja_continua_apontando_para_a_loja(db, loja_a):
    """Expand-only: o que já existia não muda de forma."""
    cred = (
        db.query(CredencialServico)
        .filter(CredencialServico.loja_id == loja_a["loja_id"])
        .one()
    )
    assert cred.papel == "dono"
