from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa


APP_DIR = Path(__file__).resolve().parents[1]


def _alembic(
    database_url: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["REVY_TRAFEGO_DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            *args,
        ],
        cwd=APP_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_recuperacoes_senha_cria_schema_aditivo_e_restritivo(
    tmp_path,
):
    banco = tmp_path / "control-recuperacoes.db"
    database_url = f"sqlite:///{banco}"
    _alembic(database_url, "upgrade", "0005_revy_control_convites")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO pessoas (
                    id, email, nome, criada_em, atualizada_em
                ) VALUES (
                    'pessoa-recuperacao', 'recuperacao@revy.test',
                    'Pessoa Recuperação', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO gestores_revy (
                    id, email, nome, senha_hash, papel, ativo, criado_em
                ) VALUES (
                    'gestor-recuperacao', 'recuperacao@revy.test',
                    'Pessoa Recuperação', 'hash-existente',
                    'gestor', 1, :agora
                )
                """
            ),
            {"agora": agora},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO acessos_control (
                    id, pessoa_id, papel, estado, senha_hash, sessao_versao,
                    gestor_legado_id, criada_em, atualizada_em
                ) VALUES (
                    'acesso-recuperacao', 'pessoa-recuperacao',
                    'gestor', 'ativo', 'hash-existente', 1,
                    'gestor-recuperacao', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )

    assert _alembic(database_url, "heads").stdout.strip() == (
        "0006_revy_control_recuperacoes (head)"
    )
    _alembic(database_url, "upgrade", "head")

    inspector = sa.inspect(engine)
    assert "recuperacoes_senha_control" in inspector.get_table_names()
    columns = {
        column["name"]: column
        for column in inspector.get_columns("recuperacoes_senha_control")
    }
    assert set(columns) == {
        "id",
        "acesso_id",
        "token_hash",
        "expira_em",
        "usado_em",
        "revogado_em",
        "criado_por_gestor_id",
        "criado_em",
    }
    assert columns["token_hash"]["type"].length == 64
    assert columns["usado_em"]["nullable"] is True
    assert columns["revogado_em"]["nullable"] is True
    assert all(
        columns[name]["nullable"] is False
        for name in {
            "id",
            "acesso_id",
            "token_hash",
            "expira_em",
            "criado_por_gestor_id",
            "criado_em",
        }
    )

    assert {
        unique["name"]: unique["column_names"]
        for unique in inspector.get_unique_constraints(
            "recuperacoes_senha_control"
        )
    } == {
        "uq_recuperacoes_senha_control_token_hash": ["token_hash"],
    }
    assert {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("recuperacoes_senha_control")
    } == {
        "ix_recuperacoes_senha_control_acesso_id": ["acesso_id"],
        "ix_recuperacoes_senha_control_criado_por_gestor_id": [
            "criado_por_gestor_id"
        ],
    }
    assert {
        foreign_key["name"]: (
            foreign_key["constrained_columns"],
            foreign_key["referred_table"],
            foreign_key["referred_columns"],
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys(
            "recuperacoes_senha_control"
        )
    } == {
        "fk_recuperacoes_senha_control_acesso_id": (
            ["acesso_id"],
            "acessos_control",
            ["id"],
            "RESTRICT",
        ),
        "fk_recuperacoes_senha_control_criado_por_gestor_id": (
            ["criado_por_gestor_id"],
            "gestores_revy",
            ["id"],
            "RESTRICT",
        ),
    }
    assert {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints(
            "recuperacoes_senha_control"
        )
    } == {
        "ck_recuperacoes_senha_control_expiracao": "expira_em >= criado_em",
        "ck_recuperacoes_senha_control_revogacao": (
            "revogado_em IS NULL OR revogado_em >= criado_em"
        ),
        "ck_recuperacoes_senha_control_uso": (
            "usado_em IS NULL OR usado_em >= criado_em"
        ),
    }

    with engine.begin() as connection:
        assert connection.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM acessos_control
                WHERE id = 'acesso-recuperacao'
                """
            )
        ).scalar_one() == 1
        assert connection.execute(
            sa.text(
                "SELECT version_num FROM alembic_version_revy_trafego"
            )
        ).scalar_one() == "0006_revy_control_recuperacoes"
