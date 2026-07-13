import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_migration_0006_cria_tabelas_e_reverte(monkeypatch):
    caminho = Path.cwd() / f".migration-test-{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{caminho.as_posix()}")
    alembic = Config("alembic.ini")
    try:
        command.upgrade(alembic, "head")
        with closing(sqlite3.connect(caminho)) as db:
            tabelas = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "credenciais_provedor" in tabelas
        assert "auditoria" in tabelas

        # downgrade da última migration remove só o que ela criou
        command.downgrade(alembic, "0005")
        with closing(sqlite3.connect(caminho)) as db:
            tabelas = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "credenciais_provedor" not in tabelas
        assert "auditoria" not in tabelas
        assert "clientes_api" in tabelas  # migrations anteriores intactas
    finally:
        if caminho.exists():
            caminho.unlink()
