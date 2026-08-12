"""Migration 0023: backfill de `estado="visto"` legado + constraint nova.

Roda `alembic` de verdade (subprocesso, banco sqlite descartável em
`tmp_path`) em vez do `Base.metadata.create_all` que o resto da suíte usa
— só assim o backfill (`op.execute`) e o `CheckConstraint` novo do banco
são exercitados de fato, não só o modelo ORM. Ver revisão da Task 0
(Important #1): sem este backfill, uma linha com `estado="visto"` gravada
pelo código anterior a esta task (existe desde 641b1ae) nunca mais bate o
filtro `estado == "novo"` que `contar_sinais_novos` passou a usar — o
sinal some do contador de "novos" para TODO mundo, para sempre.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.loja.copiloto.sinais_store import contar_sinais_novos

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PORTAL_DATABASE_URL"] = f"sqlite:///{db_path}"
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return resultado


def _inserir_sinal_legado(db_path: Path, sinal_id: str, estado: str) -> None:
    conexao = sqlite3.connect(str(db_path))
    try:
        conexao.execute(
            "INSERT INTO copiloto_sinal ("
            "id, loja_slug, regra, entidade_ref, severidade, titulo, detalhe, "
            "estado, criado_em, atualizado_em"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sinal_id,
                "loja-teste",
                "estoque_parado",
                "v1",
                "atencao",
                "Parada há 70 dias",
                "R$ 25.000,00 de capital preso.",
                estado,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        conexao.commit()
    finally:
        conexao.close()


def test_backfill_reseta_visto_legado_para_novo_e_volta_a_contar(tmp_path):
    db_path = tmp_path / "migracao_0023.db"

    # Sobe só até a revisão anterior: copiloto_sinal ainda aceita "visto"
    # no CheckConstraint de antes desta task.
    _alembic(
        "upgrade", "0022_copiloto_acao_pendente_e_estado_anterior", db_path=db_path
    )
    _inserir_sinal_legado(db_path, "sinal-legado", "visto")

    # Sobe até a head — é aqui que o backfill roda.
    _alembic("upgrade", "head", db_path=db_path)

    conexao = sqlite3.connect(str(db_path))
    try:
        estado = conexao.execute(
            "SELECT estado FROM copiloto_sinal WHERE id = ?", ("sinal-legado",)
        ).fetchone()[0]
    finally:
        conexao.close()
    assert estado == "novo"

    # "Volta a ser contada": um usuário que nunca marcou visto este sinal
    # (a informação de quem via a semântica antiga nunca existiu) precisa
    # vê-lo no contador de novos de novo — não mais escondido para sempre.
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Sessao = sessionmaker(bind=engine)
        sessao = Sessao()
        try:
            assert (
                contar_sinais_novos(sessao, "loja-teste", "qualquer-usuario") == 1
            )
        finally:
            sessao.close()
    finally:
        engine.dispose()


def test_constraint_nova_recusa_visto_de_verdade(tmp_path):
    db_path = tmp_path / "migracao_0023_constraint.db"
    _alembic("upgrade", "head", db_path=db_path)

    with pytest.raises(sqlite3.IntegrityError):
        _inserir_sinal_legado(db_path, "sinal-novo", "visto")


def test_downgrade_restaura_constraint_antiga_mas_nao_reverte_dado(tmp_path):
    """Documenta a assimetria: constraint volta a aceitar "visto"; o dado
    já resetado para "novo" pelo upgrade NÃO volta a "visto" (não há como
    saber quais linhas eram "visto" antes — ver docstring da migration).
    """
    db_path = tmp_path / "migracao_0023_downgrade.db"
    _alembic(
        "upgrade", "0022_copiloto_acao_pendente_e_estado_anterior", db_path=db_path
    )
    _inserir_sinal_legado(db_path, "sinal-legado", "visto")
    _alembic("upgrade", "head", db_path=db_path)

    _alembic(
        "downgrade", "0022_copiloto_acao_pendente_e_estado_anterior", db_path=db_path
    )

    conexao = sqlite3.connect(str(db_path))
    try:
        estado = conexao.execute(
            "SELECT estado FROM copiloto_sinal WHERE id = ?", ("sinal-legado",)
        ).fetchone()[0]
        assert estado == "novo"  # não reverte — ver docstring do downgrade.

        # Constraint antiga restaurada: "visto" volta a ser aceito.
        conexao.execute(
            "INSERT INTO copiloto_sinal ("
            "id, loja_slug, regra, entidade_ref, severidade, titulo, detalhe, "
            "estado, criado_em, atualizado_em"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sinal-pos-downgrade",
                "loja-teste",
                "estoque_parado",
                "v2",
                "atencao",
                "x",
                "y",
                "visto",
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        conexao.commit()
    finally:
        conexao.close()
