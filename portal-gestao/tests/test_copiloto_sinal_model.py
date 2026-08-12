import ast
import json
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.loja.copiloto import sinais as sinais_mod
from app.models import SINAL_REGRAS, CopilotoSinal


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


def _regras_registradas_em_sinais() -> set[str]:
    """Mesma técnica de ``tests/test_copiloto_notificacoes_shell.py``
    (F4/Task 5): lê o AST de ``sinais.py`` e extrai todo ``regra=...``
    passado a ``SinalCandidato(...)`` — não uma lista escrita à mão, para
    que uma 8ª regra nova apareça aqui sozinha."""
    caminho = Path(sinais_mod.__file__)
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    regras: set[str] = set()
    for node in ast.walk(arvore):
        if not isinstance(node, ast.Call):
            continue
        nome_chamada = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if nome_chamada != "SinalCandidato":
            continue
        for kw in node.keywords:
            if kw.arg == "regra" and isinstance(kw.value, ast.Constant):
                regras.add(kw.value.value)
    return regras


def test_sinal_regras_bate_com_as_regras_de_sinais_py():
    """Achado da revisão final da fase (minor): ``SINAL_REGRAS`` (models.py)
    é lista escrita à mão e já ficou sem a 7ª regra (``preco_fora_da_faixa``,
    a checagem de preço fora da faixa da FIPE). Sem este teste, uma regra
    nova em ``sinais.py`` pode continuar faltando aqui indefinidamente — o
    banco não tem CHECK constraint sobre ``regra`` (só sobre ``estado`` e
    ``severidade``, ver os dois testes acima), então nada mais no repositório
    apitaria."""
    esperado = _regras_registradas_em_sinais()
    assert esperado, "nenhuma regra encontrada em sinais.py — AST mudou de formato?"
    assert set(SINAL_REGRAS) == esperado
