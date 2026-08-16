import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Loja


def test_loja_nasce_no_modo_1():
    with SessionLocal() as db:
        loja = Loja(slug="loja-modo", nome="Loja Modo", status="ativa", versao=1)
        db.add(loja)
        db.commit()
        assert loja.whatsapp_modo == 1


def test_modo_2_e_aceito():
    with SessionLocal() as db:
        loja = Loja(
            slug="loja-cloud", nome="Loja Cloud", status="ativa",
            versao=1, whatsapp_modo=2,
        )
        db.add(loja)
        db.commit()
        assert loja.whatsapp_modo == 2


def test_modo_invalido_e_rejeitado_pelo_banco():
    """1 XOR 2 é restrição de banco, não só de UI (spec §2)."""
    with SessionLocal() as db:
        db.add(Loja(slug="loja-x", nome="X", status="ativa", versao=1, whatsapp_modo=3))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
