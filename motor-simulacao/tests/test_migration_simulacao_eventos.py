import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_eventos_cria_timeline_e_reverte(tmp_path, monkeypatch):
    caminho = tmp_path / f"eventos-{uuid.uuid4().hex}.db"
    url = f"sqlite:///{caminho.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    assert "simulacao_eventos" in insp.get_table_names()
    colunas = {c["name"] for c in insp.get_columns("simulacao_eventos")}
    assert {"simulacao_id", "etapa", "mensagem", "screenshot_path"} <= colunas

    command.downgrade(cfg, "0010")
    assert "simulacao_eventos" not in inspect(create_engine(url)).get_table_names()
