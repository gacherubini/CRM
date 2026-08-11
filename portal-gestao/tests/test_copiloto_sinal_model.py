import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import CopilotoSinal


def test_grava_e_le_sinal_com_dados_json(db):
    sinal = CopilotoSinal(
        loja_slug="loja-teste",
        regra="estoque_parado",
        entidade_ref="v1",
        severidade="atencao",
        titulo="3 motos passaram de 60 dias",
        detalhe="R$ 38.400 de capital preso.",
        dados_json=json.dumps({"capital_preso": "38400.00", "total": 3}),
    )
    db.add(sinal)
    db.commit()
    db.refresh(sinal)
    assert sinal.id
    assert sinal.estado == "novo"
    assert json.loads(sinal.dados_json)["total"] == 3
    assert sinal.criado_em is not None


def test_estado_invalido_e_recusado_pelo_banco(db):
    db.add(
        CopilotoSinal(
            loja_slug="loja-teste",
            regra="estoque_parado",
            severidade="atencao",
            titulo="x",
            detalhe="y",
            estado="inventado",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_severidade_invalida_e_recusada_pelo_banco(db):
    db.add(
        CopilotoSinal(
            loja_slug="loja-teste",
            regra="estoque_parado",
            severidade="apocaliptico",
            titulo="x",
            detalhe="y",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
