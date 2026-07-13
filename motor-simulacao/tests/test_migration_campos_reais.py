import uuid
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_upgrade_adiciona_colunas_e_downgrade_remove(tmp_path, monkeypatch):
    caminho = tmp_path / f"m-{uuid.uuid4().hex}.db"
    url = f"sqlite:///{caminho.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")
    cols = {c["name"] for c in inspect(create_engine(url)).get_columns("simulacoes")}
    assert {"placa", "uf_licenciamento", "finalidade", "cnh", "prazos_meses"} <= cols

    command.downgrade(cfg, "0006")
    cols2 = {c["name"] for c in inspect(create_engine(url)).get_columns("simulacoes")}
    assert not (
        {"placa", "uf_licenciamento", "finalidade", "cnh", "prazos_meses"} & cols2
    )
