from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.control.access_backfill import backfill_acessos_control


APP_DIR = Path(__file__).resolve().parents[1]
HASH_ADMIN = "hash-argon2-admin-legado"
HASH_GESTOR = "hash-argon2-gestor-legado"


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


def _snapshot_acessos_e_pessoas(connection) -> tuple[list[tuple], list[tuple]]:
    acessos = connection.execute(
        sa.text(
            """
            SELECT
                id, pessoa_id, papel, estado, senha_hash, sessao_versao,
                gestor_legado_id, criada_em, atualizada_em
            FROM acessos_control
            ORDER BY id
            """
        )
    ).all()
    pessoas = connection.execute(
        sa.text(
            """
            SELECT id, email, nome, criada_em, atualizada_em
            FROM pessoas
            ORDER BY id
            """
        )
    ).all()
    return acessos, pessoas


def _inserir_acesso(
    connection,
    *,
    acesso_id: str,
    pessoa_id: str,
    papel: str = "gestor",
    estado: str = "pendente",
    gestor_legado_id: str | None = None,
    sessao_versao: int | None = None,
    agora: datetime,
) -> None:
    campos_sessao = (
        ", sessao_versao" if sessao_versao is not None else ""
    )
    valor_sessao = ", :sessao_versao" if sessao_versao is not None else ""
    connection.execute(
        sa.text(
            f"""
            INSERT INTO acessos_control (
                id, pessoa_id, papel, estado, senha_hash, gestor_legado_id,
                criada_em, atualizada_em{campos_sessao}
            ) VALUES (
                :id, :pessoa_id, :papel, :estado, NULL, :gestor_legado_id,
                :agora, :agora{valor_sessao}
            )
            """
        ),
        {
            "id": acesso_id,
            "pessoa_id": pessoa_id,
            "papel": papel,
            "estado": estado,
            "gestor_legado_id": gestor_legado_id,
            "sessao_versao": sessao_versao,
            "agora": agora,
        },
    )


def test_migration_acesso_control_reconcilia_identidade_e_preserva_legado(tmp_path):
    banco = tmp_path / "control-acessos.db"
    database_url = f"sqlite:///{banco}"
    _alembic_upgrade(database_url, "0003_revy_control_pessoas_cargos")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO pessoas (
                    id, email, nome, criada_em, atualizada_em
                ) VALUES (
                    'pessoa-existente', 'admin@revy.test',
                    'Nome Canônico Preservado', :agora, :agora
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
                ) VALUES
                    (
                        'gestor-admin', '  ADMIN@REVY.TEST  ', 'Admin Legado',
                        :hash_admin, 'admin', 1, :agora
                    ),
                    (
                        'gestor-inativo', ' INATIVO@REVY.TEST ', 'Gestor Inativo',
                        :hash_gestor, 'gestor', 0, :agora
                    )
                """
            ),
            {
                "hash_admin": HASH_ADMIN,
                "hash_gestor": HASH_GESTOR,
                "agora": agora,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO lojas (
                    id, slug, nome, status, criada_em, atualizada_em
                ) VALUES (
                    'loja-acesso', 'loja-acesso', 'Loja Acesso',
                    'rascunho', :agora, :agora
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
                    'cargo-preservado', 'loja-acesso', 'pessoa-existente',
                    'dono', :agora, NULL, 'control', NULL
                )
                """
            ),
            {"agora": agora},
        )
        gestores_antes = connection.execute(
            sa.text(
                """
                SELECT id, email, nome, senha_hash, papel, ativo, criado_em
                FROM gestores_revy
                ORDER BY id
                """
            )
        ).all()
        cargo_antes = connection.execute(
            sa.text(
                """
                SELECT
                    id, loja_id, pessoa_id, cargo, iniciado_em,
                    encerrado_em, origem, origem_id
                FROM cargos_loja
                WHERE id = 'cargo-preservado'
                """
            )
        ).one()

    _alembic_upgrade(database_url, "head")

    inspector = sa.inspect(engine)
    assert "acessos_control" in inspector.get_table_names()
    assert {
        "id",
        "pessoa_id",
        "papel",
        "estado",
        "senha_hash",
        "sessao_versao",
        "gestor_legado_id",
        "criada_em",
        "atualizada_em",
    } == {
        column["name"]
        for column in inspector.get_columns("acessos_control")
    }

    with engine.begin() as connection:
        pessoas = connection.execute(
            sa.text(
                """
                SELECT id, email, nome
                FROM pessoas
                ORDER BY email
                """
            )
        ).all()
        assert pessoas == [
            (
                "pessoa-existente",
                "admin@revy.test",
                "Nome Canônico Preservado",
            ),
            (
                connection.execute(
                    sa.text(
                        "SELECT id FROM pessoas "
                        "WHERE email = 'inativo@revy.test'"
                    )
                ).scalar_one(),
                "inativo@revy.test",
                "Gestor Inativo",
            ),
        ]

        acessos = connection.execute(
            sa.text(
                """
                SELECT
                    id, pessoa_id, papel, estado, senha_hash, sessao_versao,
                    gestor_legado_id
                FROM acessos_control
                ORDER BY gestor_legado_id
                """
            )
        ).all()
        pessoa_inativa_id = connection.execute(
            sa.text(
                "SELECT id FROM pessoas WHERE email = 'inativo@revy.test'"
            )
        ).scalar_one()
        assert acessos == [
            (
                "gestor-admin",
                "pessoa-existente",
                "admin",
                "ativo",
                HASH_ADMIN,
                1,
                "gestor-admin",
            ),
            (
                "gestor-inativo",
                pessoa_inativa_id,
                "gestor",
                "desativado",
                HASH_GESTOR,
                1,
                "gestor-inativo",
            ),
        ]
        assert all(
            acesso.senha_hash not in {
                "senha-admin-em-texto",
                "senha-gestor-em-texto",
            }
            for acesso in connection.execute(
                sa.text(
                    "SELECT senha_hash FROM acessos_control "
                    "WHERE gestor_legado_id IS NOT NULL"
                )
            ).all()
        )

        assert connection.execute(
            sa.text(
                """
                SELECT id, email, nome, senha_hash, papel, ativo, criado_em
                FROM gestores_revy
                ORDER BY id
                """
            )
        ).all() == gestores_antes
        assert connection.execute(
            sa.text(
                """
                SELECT
                    id, loja_id, pessoa_id, cargo, iniciado_em,
                    encerrado_em, origem, origem_id
                FROM cargos_loja
                WHERE id = 'cargo-preservado'
                """
            )
        ).one() == cargo_antes

        antes = _snapshot_acessos_e_pessoas(connection)
        backfill_acessos_control(connection)
        backfill_acessos_control(connection)
        depois = _snapshot_acessos_e_pessoas(connection)
        assert depois == antes

        for pessoa_id, email in (
            ("pessoa-convite", "convite@revy.test"),
            ("pessoa-outro-legado", "outro-legado@revy.test"),
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO pessoas (
                        id, email, nome, criada_em, atualizada_em
                    ) VALUES (
                        :id, :email, 'Pessoa de Teste', :agora, :agora
                    )
                    """
                ),
                {"id": pessoa_id, "email": email, "agora": agora},
            )
        _inserir_acesso(
            connection,
            acesso_id="acesso-convite",
            pessoa_id="pessoa-convite",
            agora=agora,
        )
        convite = connection.execute(
            sa.text(
                """
                SELECT estado, senha_hash, sessao_versao, gestor_legado_id
                FROM acessos_control
                WHERE id = 'acesso-convite'
                """
            )
        ).one()
        assert convite == ("pendente", None, 1, None)

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            _inserir_acesso(
                connection,
                acesso_id="acesso-pessoa-duplicada",
                pessoa_id="pessoa-convite",
                agora=agora,
            )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            _inserir_acesso(
                connection,
                acesso_id="acesso-legado-duplicado",
                pessoa_id="pessoa-outro-legado",
                gestor_legado_id="gestor-admin",
                agora=agora,
            )

    for campo, valor in (
        ("papel", "dono"),
        ("estado", "suspenso"),
        ("sessao_versao", 0),
    ):
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        f"""
                        UPDATE acessos_control
                        SET {campo} = :valor
                        WHERE id = 'acesso-convite'
                        """
                    ),
                    {"valor": valor},
                )


def test_migration_acesso_control_aborta_identidade_legada_ambigua(tmp_path):
    banco = tmp_path / "control-acessos-conflito.db"
    database_url = f"sqlite:///{banco}"
    _alembic_upgrade(database_url, "0003_revy_control_pessoas_cargos")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO gestores_revy (
                    id, email, nome, senha_hash, papel, ativo, criado_em
                ) VALUES
                    (
                        'gestor-conflito-1', 'CONFLITO@REVY.TEST',
                        'Primeiro Gestor', 'hash-1', 'gestor', 1, :agora
                    ),
                    (
                        'gestor-conflito-2', ' conflito@revy.test ',
                        'Segundo Gestor', 'hash-2', 'gestor', 1, :agora
                    )
                """
            ),
            {"agora": agora},
        )

    with pytest.raises(subprocess.CalledProcessError):
        _alembic_upgrade(database_url, "head")

    inspector = sa.inspect(engine)
    assert "acessos_control" not in inspector.get_table_names()
    with engine.begin() as connection:
        assert connection.execute(
            sa.text(
                "SELECT version_num FROM alembic_version_revy_trafego"
            )
        ).scalar_one() == "0003_revy_control_pessoas_cargos"
        assert connection.execute(
            sa.text(
                """
                SELECT id, email, nome, senha_hash, papel, ativo
                FROM gestores_revy
                ORDER BY id
                """
            )
        ).all() == [
            (
                "gestor-conflito-1",
                "CONFLITO@REVY.TEST",
                "Primeiro Gestor",
                "hash-1",
                "gestor",
                1,
            ),
            (
                "gestor-conflito-2",
                " conflito@revy.test ",
                "Segundo Gestor",
                "hash-2",
                "gestor",
                1,
            ),
        ]
