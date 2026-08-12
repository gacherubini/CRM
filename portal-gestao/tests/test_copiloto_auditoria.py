from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.loja_operacao_auditoria import (
    DOMINIO_COPILOTO,
    registrar_auditoria_copiloto,
    registrar_auditoria_operacao,
)
from app.models import CopilotoAcao, LojaOperacaoAuditoria


def test_dominio_copiloto_e_aceito(db):
    registrar_auditoria_copiloto(
        db, loja_slug="loja-teste", acao="ajustar_preco",
        ator_email="dono@loja.test", success=True, commit=True,
    )
    linha = db.query(LojaOperacaoAuditoria).one()
    assert linha.dominio == DOMINIO_COPILOTO
    assert linha.acao == "ajustar_preco"


def test_acao_invalida_no_dominio_copiloto_e_recusada(db):
    with pytest.raises(ValueError):
        registrar_auditoria_operacao(
            db, loja_slug="loja-teste", dominio=DOMINIO_COPILOTO,
            acao="apagar_estoque", ator_email="dono@loja.test",
        )


def test_dominio_desconhecido_continua_recusado(db):
    with pytest.raises(ValueError):
        registrar_auditoria_operacao(
            db, loja_slug="loja-teste", dominio="inventado", acao="x",
            ator_email="dono@loja.test",
        )


def test_grava_acao_com_valor_anterior_e_novo(db):
    agora = datetime.now(timezone.utc)
    db.add(
        CopilotoAcao(
            loja_slug="loja-teste",
            turno_id=None,
            ator_email="dono@loja.test",
            acao="ajustar_preco",
            entidade_ref="v1",
            valor_anterior=Decimal("28000.00"),
            valor_novo=Decimal("25000.00"),
            estado="executada",
            executada_em=agora,
            desfazer_ate=agora + timedelta(minutes=30),
        )
    )
    db.commit()
    linha = db.query(CopilotoAcao).one()
    assert linha.valor_anterior == Decimal("28000.00")
    assert linha.estado == "executada"


def test_estado_invalido_de_acao_e_recusado_pelo_banco(db):
    from sqlalchemy.exc import IntegrityError

    db.add(
        CopilotoAcao(
            loja_slug="loja-teste", ator_email="d@l.test", acao="ajustar_preco",
            entidade_ref="v1", estado="inventado",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_auditoria_do_copiloto_nunca_aceita_telefone_em_claro(db):
    with pytest.raises(ValueError):
        registrar_auditoria_operacao(
            db, loja_slug="loja-teste", dominio=DOMINIO_COPILOTO,
            acao="ajustar_preco", ator_email="d@l.test",
            telefone_hmac="5511987654321",
        )
