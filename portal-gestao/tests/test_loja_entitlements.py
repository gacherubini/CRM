"""Entitlements fail-open / fail-closed e projeção do Control (Revy Loja F1)."""
from conftest import login, seed_loja_operacional

from app.db import SessionLocal
from app.loja.control_projection import (
    InMemoryControlProjectionPort,
    entitlements_from_operational,
)
from app.loja.entitlements import (
    blocks_new_processing,
    fail_open,
    from_allows_processing,
    resolve_entitlements,
)
from app.loja.permissions import ModuloNaoContratado, require_module
from app.loja.types import EntitlementState, Module
from app.models import LojaOperacionalProjecao
import pytest


def test_fail_open_com_flag_off_permite_modulos_com_cargo():
    ents = resolve_entitlements(
        "loja-x",
        frozenset({"vendedor"}),
        entitlements_enabled=False,
    )
    assert ents.source == "fail_open"
    assert ents.vendas_enabled is True
    assert ents.estoque_enabled is True
    assert ents.loja_ativa is True


def test_fail_open_sem_cargo_bloqueia():
    ents = fail_open("loja-x", frozenset())
    assert ents.vendas_enabled is False
    assert ents.estoque_enabled is False


def test_flag_on_sem_projecao_fail_closed():
    ents = resolve_entitlements(
        "sem-proj",
        frozenset({"dono"}),
        entitlements_enabled=True,
        db=None,
        allows=None,
        control_entitlements=None,
    )
    assert ents.loja_ativa is False
    assert ents.vendas_enabled is False
    assert ents.estoque_enabled is False


def test_from_allows_processing_modulo_ausente():
    def allows(slug, module=None):
        if module is None:
            return True
        return module == "vendas"

    ents = from_allows_processing("loja", allows)
    assert ents.loja_ativa is True
    assert ents.vendas_enabled is True
    assert ents.estoque_enabled is False


def test_entitlement_suspenso_bloqueia_novo_processamento():
    ents = EntitlementState(
        loja_slug="loja",
        loja_ativa=True,
        vendas_enabled=False,
        estoque_enabled=True,
        source="projecao",
    )
    assert blocks_new_processing(ents, Module.VENDAS) is True
    assert blocks_new_processing(ents, Module.ESTOQUE) is False
    with pytest.raises(ModuloNaoContratado):
        require_module(ents, Module.VENDAS)


def test_loja_suspensa_bloqueia_tudo():
    ents = EntitlementState(
        loja_slug="loja",
        loja_ativa=False,
        vendas_enabled=False,
        estoque_enabled=False,
        source="projecao",
    )
    assert blocks_new_processing(ents, "vendas") is True
    assert blocks_new_processing(ents, "estoque") is True


def test_control_port_payload_idempotente():
    port = InMemoryControlProjectionPort()
    payload = {
        "schema_version": 1,
        "loja_slug": "loja-c",
        "operational": [
            {
                "aggregate": "loja",
                "version": 2,
                "state": "ativa",
                "event_id": "e1",
            },
            {
                "aggregate": "vendas",
                "version": 1,
                "state": "ativo",
                "event_id": "e2",
            },
            {
                "aggregate": "estoque",
                "version": 1,
                "state": "ativo",
                "event_id": "e3",
            },
        ],
        "people": [
            {
                "pessoa_id": "p1",
                "loja_slug": "loja-c",
                "roles": ["dono"],
                "ativo": True,
            }
        ],
    }
    r1 = port.apply_payload("loja-c", payload)
    assert r1 == ["applied", "applied", "applied"]
    r2 = port.apply_payload("loja-c", payload)
    assert r2 == ["idempotent", "idempotent", "idempotent"]
    ents = port.get_entitlements("loja-c")
    assert ents is not None
    assert ents.vendas_enabled is True
    mems = port.get_memberships("p1")
    assert any(m.loja_slug == "loja-c" and "dono" in m.roles for m in mems)


def test_entitlements_from_operational_modulo_suspenso():
    ents = entitlements_from_operational(
        "loja",
        [
            {"aggregate": "loja", "state": "ativa", "version": 1},
            {"aggregate": "vendas", "state": "suspenso", "version": 2},
            {"aggregate": "estoque", "state": "ativo", "version": 1},
        ],
    )
    assert ents.loja_ativa is True
    assert ents.vendas_enabled is False
    assert ents.estoque_enabled is True


def test_http_integration_403_estoque_quando_entitlements_on(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    login(client)
    # seed_loja_operacional só grava aggregate "loja", sem módulo estoque → bloqueia
    r = client.get("/app/estoque")
    assert r.status_code == 403


def test_http_entitlements_off_fail_open_estoque(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    login(client)
    r = client.get("/app/estoque")
    assert r.status_code == 200
    assert "Honda Civic" in r.text


def test_http_entitlements_on_com_modulos_seedados(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    db = SessionLocal()
    try:
        seed_loja_operacional(db, loja_slug="loja-teste", state="ativa")
        for agg, state in (("vendas", "ativo"), ("estoque", "ativo")):
            row = db.get(LojaOperacionalProjecao, ("loja-teste", agg))
            if row is None:
                db.add(
                    LojaOperacionalProjecao(
                        loja_slug="loja-teste",
                        aggregate=agg,
                        version=1,
                        state=state,
                        event_id=f"seed-{agg}",
                    )
                )
            else:
                row.state = state
        db.commit()
    finally:
        db.close()
    r = client.get("/app/estoque")
    assert r.status_code == 200
