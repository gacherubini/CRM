"""Auditoria formal de operações Loja (handoff + financeiras) — F5 residual."""
from __future__ import annotations

import pytest

from conftest import csrf_da_resposta, login
from app.db import SessionLocal
from app.financeiro_calc import identidade_telefone
from app.loja_operacao_auditoria import (
    DOMINIO_ATENDIMENTO,
    DOMINIO_CANAL,
    DOMINIO_FINANCEIRA,
    listar_auditoria_operacao,
    registrar_auditoria_canal,
    registrar_auditoria_operacao,
)
from app.models import AtendimentoAtribuicao, LojaOperacaoAuditoria, agora


def test_handoff_assumir_cria_auditoria_com_hmac(client, chatbot_fake):
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/conversas/5511987654321")
    resposta = client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "assumir"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "ok=assumir" in resposta.headers["location"]

    db = SessionLocal()
    try:
        rows = (
            db.query(LojaOperacaoAuditoria)
            .filter(LojaOperacaoAuditoria.dominio == DOMINIO_ATENDIMENTO)
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.acao == "assumir"
        assert row.ator_email == "vendedor@loja.test"
        assert row.para_email == "vendedor@loja.test"
        assert row.de_email is None
        assert row.origem == "handoff_portal"
        assert row.success is True
        expected_hmac = identidade_telefone("5511987654321")
        assert row.telefone_hmac == expected_hmac
        assert "5511987654321" not in (row.telefone_hmac or "")
        assert row.telefone_hmac.isdigit() is False
        # Nenhuma coluna deve conter o telefone em claro
        blob = " ".join(
            str(getattr(row, c) or "")
            for c in (
                "id",
                "loja_slug",
                "dominio",
                "acao",
                "ator_email",
                "telefone_hmac",
                "de_email",
                "para_email",
                "origem",
                "provedor",
                "error_code",
            )
        )
        assert "5511987654321" not in blob
    finally:
        db.close()


def test_handoff_devolver_cria_auditoria(client, chatbot_fake):
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/conversas/5511987654321")
    csrf = csrf_da_resposta(pagina)
    client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf, "acao": "assumir"},
        follow_redirects=False,
    )
    client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf, "acao": "devolver"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        rows = (
            db.query(LojaOperacaoAuditoria)
            .filter(LojaOperacaoAuditoria.dominio == DOMINIO_ATENDIMENTO)
            .order_by(LojaOperacaoAuditoria.criado_em.asc())
            .all()
        )
        assert [r.acao for r in rows] == ["assumir", "devolver"]
        devolver = rows[1]
        assert devolver.ator_email == "vendedor@loja.test"
        assert devolver.de_email == "vendedor@loja.test"
        assert devolver.para_email is None
        assert devolver.telefone_hmac == identidade_telefone("5511987654321")
        assert "5511987654321" not in (devolver.telefone_hmac or "")
    finally:
        db.close()


def test_handoff_reatribuir_registra_de_e_para(client, chatbot_fake, db):
    db.add(
        AtendimentoAtribuicao(
            loja_slug="loja-teste",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="outro@loja.test",
            origem="handoff_portal",
            iniciada_em=agora(),
            ativa=True,
        )
    )
    db.commit()

    login(client, papel="gerente", email="gerente@loja.test")
    pagina = client.get("/app/conversas/5511987654321")
    resposta = client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "assumir"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303

    sess = SessionLocal()
    try:
        row = (
            sess.query(LojaOperacaoAuditoria)
            .filter(LojaOperacaoAuditoria.dominio == DOMINIO_ATENDIMENTO)
            .one()
        )
        assert row.acao == "reatribuir"
        assert row.de_email == "outro@loja.test"
        assert row.para_email == "gerente@loja.test"
        assert row.ator_email == "gerente@loja.test"
    finally:
        sess.close()


def test_upsert_financeira_cria_auditoria_sem_segredo(client, motor_fake):
    login(client)
    pagina = client.get("/app/financeiras")
    csrf = csrf_da_resposta(pagina)
    resposta = client.post(
        "/app/financeiras/Pan",
        data={
            "csrf": csrf,
            "usuario": "loja-nova",
            "senha": "nova-senha-rotacionada-SEGREDO",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "ok=salvo" in resposta.headers["location"]

    db = SessionLocal()
    try:
        rows = (
            db.query(LojaOperacaoAuditoria)
            .filter(LojaOperacaoAuditoria.dominio == DOMINIO_FINANCEIRA)
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.acao == "upsert"
        assert row.provedor == "Pan"
        assert row.ator_email == "dono@loja.test"
        assert row.success is True
        assert row.error_code is None
        # Segredo nunca entra na linha de auditoria
        for col in (
            row.acao,
            row.provedor,
            row.ator_email,
            row.de_email,
            row.para_email,
            row.origem,
            row.error_code,
            row.telefone_hmac,
        ):
            assert col is None or "senha" not in str(col).lower()
            assert col is None or "SEGREDO" not in str(col)
            assert col is None or "nova-senha" not in str(col)
        # Serialização completa da row também sem segredo
        dump = str(row.__dict__)
        assert "nova-senha-rotacionada-SEGREDO" not in dump
        assert "SENHA-SECRETA" not in dump
    finally:
        db.close()


def test_testar_financeira_cria_auditoria(client, motor_fake):
    login(client)
    pagina = client.get("/app/financeiras")
    csrf = csrf_da_resposta(pagina)
    resposta = client.post(
        "/app/financeiras/Pan/testar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert resposta.status_code == 303

    db = SessionLocal()
    try:
        row = (
            db.query(LojaOperacaoAuditoria)
            .filter(
                LojaOperacaoAuditoria.dominio == DOMINIO_FINANCEIRA,
                LojaOperacaoAuditoria.acao == "testar",
            )
            .one()
        )
        assert row.provedor == "Pan"
        assert row.success is True
        assert row.ator_email == "dono@loja.test"
    finally:
        db.close()


def test_upsert_financeira_falha_motor_ainda_audita(client, motor_fake):
    motor_fake.indisponivel = True
    login(client)
    pagina = client.get("/app/financeiras")
    # GET falha com motor indisponível, mas CSRF de outra página
    pagina_app = client.get("/app")
    csrf = csrf_da_resposta(pagina_app)
    resposta = client.post(
        "/app/financeiras/Pan",
        data={"csrf": csrf, "usuario": "x", "senha": "y-secreta"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "erro=motor" in resposta.headers["location"]

    db = SessionLocal()
    try:
        row = (
            db.query(LojaOperacaoAuditoria)
            .filter(LojaOperacaoAuditoria.dominio == DOMINIO_FINANCEIRA)
            .one()
        )
        assert row.acao == "upsert"
        assert row.success is False
        assert row.error_code == "motor_indisponivel"
        assert "y-secreta" not in str(row.__dict__)
    finally:
        db.close()


def test_helper_recusa_telefone_em_claro(db):
    try:
        registrar_auditoria_operacao(
            db,
            loja_slug="loja-teste",
            dominio=DOMINIO_ATENDIMENTO,
            acao="assumir",
            ator_email="a@b.c",
            telefone_hmac="5511987654321",
        )
        assert False, "deveria recusar telefone em claro"
    except ValueError as exc:
        assert "claro" in str(exc).lower()


def test_listar_auditoria_helper(db):
    registrar_auditoria_operacao(
        db,
        loja_slug="loja-teste",
        dominio=DOMINIO_ATENDIMENTO,
        acao="assumir",
        ator_email="v@loja.test",
        telefone_hmac="a" * 64,
        commit=True,
    )
    registrar_auditoria_operacao(
        db,
        loja_slug="loja-teste",
        dominio=DOMINIO_FINANCEIRA,
        acao="upsert",
        ator_email="d@loja.test",
        provedor="Pan",
        success=True,
        commit=True,
    )
    todos = listar_auditoria_operacao(db, "loja-teste")
    assert len(todos) == 2
    so_fin = listar_auditoria_operacao(
        db, "loja-teste", dominio=DOMINIO_FINANCEIRA
    )
    assert len(so_fin) == 1
    assert so_fin[0].provedor == "Pan"


def test_auditoria_canal_persiste(db):
    row = registrar_auditoria_canal(
        db,
        loja_slug="loja-teste",
        acao="conectar",
        ator_email="dono@loja.test",
        success=True,
        commit=True,
    )
    assert row.dominio == DOMINIO_CANAL
    assert row.acao == "conectar"
    assert row.telefone_hmac is None


def test_auditoria_canal_recusa_acao_invalida(db):
    with pytest.raises(ValueError):
        registrar_auditoria_canal(
            db, loja_slug="loja-teste", acao="explodir", ator_email="a@b.c"
        )
