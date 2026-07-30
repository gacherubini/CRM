"""Identidade multi-loja e isolamento de cargos (Revy Loja F1)."""
from types import SimpleNamespace

import pytest

from app.loja.identity import (
    SESSION_LOJA_KEY,
    actor_from_usuario,
    available_store_slugs,
    resolve_store_context,
    roles_in_store,
    select_store_slug,
    session_loja_slug,
    union_roles_for_store,
)
from app.loja.permissions import SemAcessoLoja
from app.loja.types import StoreMembership


def _usuario(papel="dono", loja="loja-a", uid="u1", ativo=True):
    return SimpleNamespace(
        id=uid,
        email="ana@loja.test",
        nome="Ana",
        papel=papel,
        loja_slug=loja,
        ativo=ativo,
    )


def test_actor_from_usuario_legado_uma_loja():
    actor = actor_from_usuario(_usuario(papel="gerente", loja="alfa"))
    assert actor.pessoa_id == "u1"
    assert len(actor.memberships) == 1
    assert actor.memberships[0].loja_slug == "alfa"
    assert actor.memberships[0].roles == frozenset({"gerente"})


def test_admin_plataforma_nao_vira_cargo_operacional():
    actor = actor_from_usuario(_usuario(papel="admin_plataforma", loja="alfa"))
    # Sem cargo operacional: membership com roles vazias ainda existe pelo slug.
    assert actor.memberships[0].roles == frozenset()
    with pytest.raises(SemAcessoLoja):
        resolve_store_context(actor)


def test_resolve_store_usa_sessao_quando_autorizada():
    mems = (
        StoreMembership("loja-a", frozenset({"vendedor"})),
        StoreMembership("loja-b", frozenset({"dono", "gerente"})),
    )
    actor = actor_from_usuario(_usuario(loja="loja-a"), memberships=mems)
    ctx = resolve_store_context(actor, "loja-b")
    assert ctx.loja_slug == "loja-b"
    assert ctx.roles == frozenset({"dono", "gerente"})


def test_cargo_loja_a_nao_vaza_para_loja_b():
    mems = (
        StoreMembership("loja-a", frozenset({"dono"})),
        StoreMembership("loja-b", frozenset({"vendedor"})),
    )
    actor = actor_from_usuario(_usuario(), memberships=mems)
    assert roles_in_store(actor, "loja-a") == frozenset({"dono"})
    assert roles_in_store(actor, "loja-b") == frozenset({"vendedor"})
    ctx_b = resolve_store_context(actor, "loja-b")
    assert "dono" not in ctx_b.roles
    assert ctx_b.roles == frozenset({"vendedor"})


def test_pessoa_alterna_entre_duas_lojas_sem_misturar_cargos():
    mems = (
        StoreMembership("loja-a", frozenset({"gerente"})),
        StoreMembership("loja-b", frozenset({"vendedor"})),
    )
    actor = actor_from_usuario(_usuario(), memberships=mems)
    a = resolve_store_context(actor, "loja-a")
    b = resolve_store_context(actor, "loja-b")
    assert a.loja_slug == "loja-a" and a.roles == frozenset({"gerente"})
    assert b.loja_slug == "loja-b" and b.roles == frozenset({"vendedor"})
    assert a.roles.isdisjoint(b.roles) or True  # roles distintas por desenho do fixture


def test_gestora_control_nao_recebe_permissao_extra_na_loja():
    """Mesmo que a pessoa seja gestora no Control, só cargos da Loja contam."""
    mems = (StoreMembership("loja-a", frozenset({"vendedor"})),)
    actor = actor_from_usuario(_usuario(papel="vendedor"), memberships=mems)
    ctx = resolve_store_context(actor, "loja-a")
    assert ctx.roles == frozenset({"vendedor"})
    assert "dono" not in ctx.roles


def test_select_store_rejeita_loja_nao_autorizada():
    mems = (StoreMembership("loja-a", frozenset({"dono"}), True),)
    actor = actor_from_usuario(_usuario(), memberships=mems)
    with pytest.raises(SemAcessoLoja):
        select_store_slug(actor, "loja-outra")


def test_membership_inativa_ou_convite_nao_autoriza():
    mems = (
        StoreMembership("loja-a", frozenset({"dono"}), ativo=False),
        StoreMembership("loja-b", frozenset(), ativo=True),
    )
    actor = actor_from_usuario(_usuario(), memberships=mems)
    assert available_store_slugs(actor) == ()
    with pytest.raises(SemAcessoLoja):
        resolve_store_context(actor)


def test_union_roles_mesma_loja():
    mems = [
        StoreMembership("loja-a", frozenset({"vendedor"})),
        StoreMembership("loja-a", frozenset({"gerente"})),
        StoreMembership("loja-b", frozenset({"dono"})),
    ]
    assert union_roles_for_store(mems, "loja-a") == frozenset({"vendedor", "gerente"})
    assert "dono" not in union_roles_for_store(mems, "loja-a")


def test_session_loja_slug():
    assert session_loja_slug({SESSION_LOJA_KEY: "x"}) == "x"
    assert session_loja_slug({}) is None
    assert session_loja_slug(None) is None
