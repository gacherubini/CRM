from dataclasses import replace

from app.config import settings
from app.db import SessionLocal
from app.models import ModuloRevy
from app.web import control as control_mod


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _login_admin(client) -> None:
    response = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _seed_catalog() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
            ]
        )
        db.commit()


def test_cobranca_atrasada_alerta_sem_suspender_loja_ou_modulo(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _seed_catalog()
    _login_admin(client)
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Contrato", "slug": "loja-contrato-http"},
    ).json()
    modules = client.put(
        f"/control/v1/lojas/{store['id']}/modulos",
        json={"modulos": ["vendas"]},
    )
    assert modules.status_code == 200

    current = {
        "valor_mensal": "1299.90",
        "vigencia_inicio": "2026-08-01",
        "vigencia_fim": None,
        "vencimento_dia": 12,
        "situacao_cobranca": "em_dia",
    }
    created = client.put(
        f"/control/v1/lojas/{store['id']}/contrato",
        json=current,
    )

    assert created.status_code == 200
    assert created.json() == {
        "id": created.json()["id"],
        "loja_id": store["id"],
        "valor_mensal": "1299.90",
        "moeda": "BRL",
        "vigencia_inicio": "2026-08-01",
        "vigencia_fim": None,
        "vencimento_dia": 12,
        "situacao_cobranca": "em_dia",
    }

    overdue = client.put(
        f"/control/v1/lojas/{store['id']}/contrato",
        json={**current, "situacao_cobranca": "atrasada"},
    )
    listed_contract = client.get(
        f"/control/v1/lojas/{store['id']}/contrato"
    )
    listed_modules = client.get(
        f"/control/v1/lojas/{store['id']}/modulos"
    )
    listed_store = client.get(f"/control/v1/lojas/{store['id']}")

    assert overdue.status_code == 200
    assert overdue.json()["id"] == created.json()["id"]
    assert overdue.json()["situacao_cobranca"] == "atrasada"
    assert listed_contract.json() == overdue.json()
    assert listed_modules.json()["items"] == [
        {
            "codigo": "vendas",
            "nome": "Vendas",
            "estado": "ativo",
            "versao": 1,
        }
    ]
    assert listed_store.json()["estado"] == "rascunho"
