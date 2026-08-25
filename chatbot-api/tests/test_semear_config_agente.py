"""O script de semeadura precisa achar a loja e o banco certos (spec §11).

Os dois testes daqui nasceram de defeitos reais, achados conferindo o Postgres de
produção antes do deploy do card 2:

1. o único slug que o script conhecia era `vitor-motos`, e a loja que atende em
   produção — 1.235 conversas — tem slug `moto-center`. O passo 2 do rollout
   pararia com "loja não existe", e seguir para o passo 3 sem ele estreia a loja
   se apresentando como "a loja";
2. o comando documentado era `CHATBOT_DATABASE_URL=… python -m scripts…`, mas
   `app/db.py` lê `DATABASE_URL`. Com só o primeiro definido o engine resolve
   SQLite — o mesmo "o alembic mente" que o docstring do script alerta e que o
   comando dele reproduzia.
"""
import sys

import pytest

from app import db as db_module
from app import models_db
from scripts import semear_config_agente


def test_o_slug_do_piloto_e_o_que_existe_no_banco_de_producao():
    """`moto-center` é a loja real; `vitor motos` é o nome comercial no prompt."""
    assert "moto-center" in semear_config_agente.CAMPOS_POR_SLUG
    assert (
        semear_config_agente.CAMPOS_POR_SLUG["moto-center"].nome_loja == "vitor motos"
    )


def test_sqlite_com_chatbot_database_url_definido_e_recusado(monkeypatch, capsys):
    """A armadilha do comando documentado: engine SQLite com a URL do Postgres à mão."""
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:///./chatbot.db")
    monkeypatch.setenv("CHATBOT_DATABASE_URL", "postgresql://u:p@suite-pg/chatbot")

    assert semear_config_agente.main(["semear", "moto-center"]) == 2
    erro = capsys.readouterr().err
    assert "DATABASE_URL" in erro


def test_loja_ausente_diz_quais_slugs_o_banco_tem(monkeypatch, capsys, db_sessao):
    """Sem isto o operador lê "não existe" e não sabe o que existe."""
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgresql://u:p@suite-pg/chatbot")
    monkeypatch.delenv("CHATBOT_DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "SessionLocal", db_sessao)

    sessao = db_sessao()
    sessao.add(models_db.Loja(
            id="l-1", nome="Outra", slug="outra-loja", evolution_instance="outra-1"
        ))
    sessao.commit()
    sessao.close()

    assert semear_config_agente.main(["semear", "moto-center"]) == 1
    assert "outra-loja" in capsys.readouterr().err


@pytest.fixture
def db_sessao():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db_module.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


assert sys is not None  # o módulo é importado pelo script; mantém o lint quieto
