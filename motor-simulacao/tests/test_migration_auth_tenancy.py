import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_migration_0004_preserva_dados_e_reverte(monkeypatch):
    caminho = Path.cwd() / f".migration-test-{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{caminho.as_posix()}")
    alembic = Config("alembic.ini")
    try:
        command.upgrade(alembic, "0003")
        with closing(sqlite3.connect(caminho)) as db:
            db.execute("INSERT INTO simulacoes (id, status) VALUES (?, ?)", ("antiga", "recebida"))
            db.execute(
                "INSERT INTO idempotencia (chave, request_hash, simulacao_id) VALUES (?, ?, ?)",
                ("chave-antiga", "hash", "antiga"),
            )
            db.commit()

        command.upgrade(alembic, "head")
        with closing(sqlite3.connect(caminho)) as db:
            row = db.execute(
                "SELECT s.cliente_id, i.cliente_id, i.chave "
                "FROM simulacoes s JOIN idempotencia i ON i.simulacao_id = s.id"
            ).fetchone()
        assert row is not None
        assert row[0] == row[1]
        assert row[2] == "chave-antiga"

        command.downgrade(alembic, "0003")
        with closing(sqlite3.connect(caminho)) as db:
            row = db.execute("SELECT chave, simulacao_id FROM idempotencia").fetchone()
        assert row == ("chave-antiga", "antiga")
    finally:
        if caminho.exists():
            caminho.unlink()
