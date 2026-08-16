import pytest
from sqlalchemy.exc import IntegrityError

from app.models_db import FilaVendedor


def test_vendedor_nasce_ativo(db, loja_a):
    """Precisa do commit: default de coluna só é aplicado no flush.

    Sem ele, ``v.ativo`` é ``None`` e o teste passaria mesmo se o default
    estivesse errado.
    """
    v = FilaVendedor(
        id=f"{loja_a['loja_id'][:8]}-f1", loja_id=loja_a["loja_id"], nome="João",
        telefone="5511999998888", ordem=1,
    )
    db.add(v)
    db.commit()
    assert v.ativo is True


def test_nome_e_obrigatorio(db, loja_a):
    """O nome vai no aviso ao cliente (§5.1) — sem ele o handoff fica anônimo."""
    db.add(FilaVendedor(
        id=f"{loja_a['loja_id'][:8]}-f2", loja_id=loja_a["loja_id"], nome=None,
        telefone="5511999998888", ordem=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_telefone_e_obrigatorio(db, loja_a):
    db.add(FilaVendedor(
        id=f"{loja_a['loja_id'][:8]}-f3", loja_id=loja_a["loja_id"], nome="João",
        telefone=None, ordem=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
