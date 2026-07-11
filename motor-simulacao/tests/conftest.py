"""Fixtures de teste: banco isolado em memória e override da dependência get_db."""
import os

os.environ["MOTOR_SKIP_INIT"] = "1"  # não tocar no engine default ao importar o app

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models_db  # noqa: E402,F401 (registra os modelos antes do create_all)
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Base.metadata.create_all(_engine)
_TestSession = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
