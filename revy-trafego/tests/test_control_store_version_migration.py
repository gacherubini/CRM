from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa


APP_DIR = Path(__file__).resolve().parents[1]


def _alembic_upgrade(database_url: str, revision: str) -> None:
    env = os.environ.copy()
    env["REVY_TRAFEGO_DATABASE_URL"] = database_url
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            revision,
        ],
        cwd=APP_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_adiciona_versao_inicial_a_lojas_existentes_e_novas(
    tmp_path,
):
    banco = tmp_path / "control-store-version.db"
    database_url = f"sqlite:///{banco}"
    _alembic_upgrade(database_url, "0007_revy_control_portfolio")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO lojas (
                    id, slug, nome, status, criada_em, atualizada_em
                ) VALUES (
                    'loja-existente', 'loja-existente', 'Loja Existente',
                    'ativa', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )

    _alembic_upgrade(database_url, "0008_revy_control_loja_versao")

    inspector = sa.inspect(engine)
    versao = next(
        column
        for column in inspector.get_columns("lojas")
        if column["name"] == "versao"
    )
    assert versao["nullable"] is False
    assert str(versao["default"]).strip("()'\"") == "1"
    assert {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints("lojas")
    }["ck_lojas_versao"] == "versao >= 1"

    with engine.begin() as connection:
        assert connection.execute(
            sa.text(
                "SELECT versao FROM lojas WHERE id = 'loja-existente'"
            )
        ).scalar_one() == 1
        connection.execute(
            sa.text(
                """
                INSERT INTO lojas (
                    id, slug, nome, status, criada_em, atualizada_em
                ) VALUES (
                    'loja-nova', 'loja-nova', 'Loja Nova',
                    'rascunho', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )
        assert connection.execute(
            sa.text("SELECT versao FROM lojas WHERE id = 'loja-nova'")
        ).scalar_one() == 1

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE lojas SET versao = 0 WHERE id = 'loja-existente'"
                )
            )
