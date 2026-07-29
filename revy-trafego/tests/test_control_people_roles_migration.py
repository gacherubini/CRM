from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


def test_migration_pessoas_e_cargos_preserva_identidade_e_historico(tmp_path):
    banco = tmp_path / "control-fase-2.db"
    database_url = f"sqlite:///{banco}"
    _alembic_upgrade(database_url, "0002_revy_control_lojas_rbac")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO lojas (
                    id, slug, nome, status, criada_em, atualizada_em
                ) VALUES (
                    'loja-1', 'loja-centro', 'Loja Centro',
                    'rascunho', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )

    _alembic_upgrade(database_url, "head")

    inspector = sa.inspect(engine)
    assert {"pessoas", "cargos_loja"} <= set(inspector.get_table_names())
    assert {
        "id",
        "email",
        "nome",
        "criada_em",
        "atualizada_em",
    } == {column["name"] for column in inspector.get_columns("pessoas")}
    assert {
        "id",
        "loja_id",
        "pessoa_id",
        "cargo",
        "iniciado_em",
        "encerrado_em",
        "origem",
        "origem_id",
    } == {column["name"] for column in inspector.get_columns("cargos_loja")}

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO pessoas (
                    id, email, nome, criada_em, atualizada_em
                ) VALUES (
                    'pessoa-1', 'ana@loja.test', 'Ana Loja', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO cargos_loja (
                    id, loja_id, pessoa_id, cargo, iniciado_em,
                    encerrado_em, origem, origem_id
                ) VALUES (
                    'cargo-dono-1', 'loja-1', 'pessoa-1', 'dono',
                    :agora, NULL, 'portal', 'usuario-portal-1'
                )
                """
            ),
            {"agora": agora},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO cargos_loja (
                    id, loja_id, pessoa_id, cargo, iniciado_em,
                    encerrado_em, origem, origem_id
                ) VALUES (
                    'cargo-gerente-1', 'loja-1', 'pessoa-1', 'gerente',
                    :agora, NULL, 'control', NULL
                )
                """
            ),
            {"agora": agora},
        )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO pessoas (
                        id, email, nome, criada_em, atualizada_em
                    ) VALUES (
                        'pessoa-2', ' ANA@LOJA.TEST ', 'Outra Ana',
                        :agora, :agora
                    )
                    """
                ),
                {"agora": agora},
            )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO cargos_loja (
                        id, loja_id, pessoa_id, cargo, iniciado_em,
                        encerrado_em, origem, origem_id
                    ) VALUES (
                        'cargo-dono-duplicado', 'loja-1', 'pessoa-1', 'dono',
                        :agora, NULL, 'control', NULL
                    )
                    """
                ),
                {"agora": agora},
            )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO cargos_loja (
                        id, loja_id, pessoa_id, cargo, iniciado_em,
                        encerrado_em, origem, origem_id
                    ) VALUES (
                        'cargo-vendedor-origem-repetida',
                        'loja-1', 'pessoa-1', 'vendedor',
                        :agora, NULL, 'portal', 'usuario-portal-1'
                    )
                    """
                ),
                {"agora": agora},
            )

    encerrado_em = agora + timedelta(minutes=1)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE cargos_loja
                SET encerrado_em = :encerrado_em
                WHERE id = 'cargo-dono-1'
                """
            ),
            {"encerrado_em": encerrado_em},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO cargos_loja (
                    id, loja_id, pessoa_id, cargo, iniciado_em,
                    encerrado_em, origem, origem_id
                ) VALUES (
                    'cargo-dono-2', 'loja-1', 'pessoa-1', 'dono',
                    :iniciado_em, NULL, 'portal', 'usuario-portal-1'
                )
                """
            ),
            {"iniciado_em": encerrado_em},
        )

        cargos = connection.execute(
            sa.text(
                """
                SELECT cargo, encerrado_em IS NULL
                FROM cargos_loja
                WHERE pessoa_id = 'pessoa-1'
                ORDER BY id
                """
            )
        ).all()
        assert cargos == [
            ("dono", False),
            ("dono", True),
            ("gerente", True),
        ]
