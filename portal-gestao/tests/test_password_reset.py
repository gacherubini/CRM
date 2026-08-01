from datetime import timedelta

import pytest

from app.auth import hash_senha, verifica_senha
from app.db import SessionLocal
from app.models import RedefinicaoSenha, Usuario, agora
from app.password_reset import (
    IssuedReset,
    PasswordResetInvalid,
    consume_reset,
    issue_reset,
)
from app.password_rules import SenhaInvalida
from app.tokens import token_hash


def _dono(db, email="dono@x.com", *, ativo=True):
    user = Usuario(
        email=email, nome="Dono", senha_hash=hash_senha("senha-antiga-1"),
        papel="dono", loja_slug="loja-a", ativo=ativo,
    )
    db.add(user)
    db.commit()
    return user


def test_issue_reset_usuario_ativo_gera_token():
    with SessionLocal() as db:
        _dono(db)
        issued = issue_reset(db, email="dono@x.com")
        assert isinstance(issued, IssuedReset)
        assert issued.email == "dono@x.com"
        reg = db.query(RedefinicaoSenha).one()
        assert reg.token_hash == token_hash(issued.token)


def test_issue_reset_inexistente_ou_inativo_retorna_none():
    with SessionLocal() as db:
        _dono(db, email="inativo@x.com", ativo=False)
        assert issue_reset(db, email="inativo@x.com") is None
        assert issue_reset(db, email="naoexiste@x.com") is None


def test_issue_reset_reemite_revoga_pendente_anterior():
    with SessionLocal() as db:
        _dono(db)
        primeiro = issue_reset(db, email="dono@x.com")
        # burla o rate limit recuando o criado_em do primeiro token
        reg = db.query(RedefinicaoSenha).one()
        reg.criado_em = agora() - timedelta(minutes=5)
        db.commit()
        segundo = issue_reset(db, email="dono@x.com")
        assert segundo is not None and segundo.token != primeiro.token
        pendentes = db.query(RedefinicaoSenha).filter(
            RedefinicaoSenha.usado_em.is_(None),
            RedefinicaoSenha.revogado_em.is_(None),
        ).all()
        assert len(pendentes) == 1
        assert pendentes[0].token_hash == token_hash(segundo.token)


def test_issue_reset_rate_limit_bloqueia_reemissao_rapida():
    with SessionLocal() as db:
        _dono(db)
        assert issue_reset(db, email="dono@x.com") is not None
        # token pendente recém-criado → segunda tentativa não gera novo
        assert issue_reset(db, email="dono@x.com") is None
        assert db.query(RedefinicaoSenha).count() == 1


def test_consume_reset_troca_a_senha_e_marca_usado():
    with SessionLocal() as db:
        user = _dono(db)
        issued = issue_reset(db, email="dono@x.com")
        consume_reset(
            db, token=issued.token,
            senha="senha-nova-segura", confirmacao="senha-nova-segura",
        )
        db.refresh(user)
        assert verifica_senha(user.senha_hash, "senha-nova-segura")
        reg = db.query(RedefinicaoSenha).one()
        assert reg.usado_em is not None


def test_consume_reset_token_ruim_ou_expirado_levanta_invalid():
    with SessionLocal() as db:
        _dono(db)
        with pytest.raises(PasswordResetInvalid):
            consume_reset(db, token="nao-existe", senha="senha-nova-segura", confirmacao="senha-nova-segura")
        issued = issue_reset(db, email="dono@x.com")
        reg = db.query(RedefinicaoSenha).one()
        reg.expira_em = agora() - timedelta(hours=1)
        db.commit()
        with pytest.raises(PasswordResetInvalid):
            consume_reset(db, token=issued.token, senha="senha-nova-segura", confirmacao="senha-nova-segura")


def test_consume_reset_senha_invalida_nao_consome_token():
    with SessionLocal() as db:
        _dono(db)
        issued = issue_reset(db, email="dono@x.com")
        with pytest.raises(SenhaInvalida):
            consume_reset(db, token=issued.token, senha="curta", confirmacao="curta")
        reg = db.query(RedefinicaoSenha).one()
        assert reg.usado_em is None  # token continua utilizável
