"""De quem é este pedido: do token, ou da instância? (spec §6.2)

Credencial de loja manda como sempre. Credencial de integração não tem loja —
resolve pela instância, e recusa quando não vem uma.
"""
import pytest
from fastapi import HTTPException

from app import auth
from app.auth import Contexto


def test_credencial_de_loja_ignora_instance(db, loja_a):
    """Expand-only: quem tem loja no token não muda de comportamento."""
    ctx = Contexto(loja_id=loja_a["loja_id"], papel="dono")

    assert auth.resolver_loja_id(db, ctx, None) == loja_a["loja_id"]


def test_credencial_de_loja_nao_e_sequestrada_por_instance_alheia(db, loja_a, loja_b):
    """A instância da loja B no corpo não move um token da loja A."""
    ctx = Contexto(loja_id=loja_a["loja_id"], papel="dono")

    assert auth.resolver_loja_id(db, ctx, loja_b["instance"]) == loja_a["loja_id"]


def test_integracao_resolve_pela_instance(db, loja_a):
    ctx = Contexto(loja_id=None, papel="integracao")

    assert auth.resolver_loja_id(db, ctx, loja_a["instance"]) == loja_a["loja_id"]


def test_integracao_escolhe_entre_duas_lojas(db, loja_a, loja_b):
    """O bug inteiro em uma linha: o mesmo token tem de acertar as duas."""
    ctx = Contexto(loja_id=None, papel="integracao")

    assert auth.resolver_loja_id(db, ctx, loja_a["instance"]) == loja_a["loja_id"]
    assert auth.resolver_loja_id(db, ctx, loja_b["instance"]) == loja_b["loja_id"]


def test_integracao_sem_instance_e_400(db):
    """Fail-closed: sem instância não existe 'alguma' loja para cair."""
    ctx = Contexto(loja_id=None, papel="integracao")

    with pytest.raises(HTTPException) as e:
        auth.resolver_loja_id(db, ctx, None)
    assert e.value.status_code == 400


def test_integracao_com_instance_vazia_e_400(db):
    ctx = Contexto(loja_id=None, papel="integracao")

    with pytest.raises(HTTPException) as e:
        auth.resolver_loja_id(db, ctx, "   ")
    assert e.value.status_code == 400


def test_integracao_com_instance_desconhecida_e_404(db):
    ctx = Contexto(loja_id=None, papel="integracao")

    with pytest.raises(HTTPException) as e:
        auth.resolver_loja_id(db, ctx, "instancia-que-nao-existe")
    assert e.value.status_code == 404
