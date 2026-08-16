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
                ModuloRevy(id="copiloto", codigo="copiloto", nome="Copiloto de Vendas"),
                ModuloRevy(id="financeiro", codigo="financeiro", nome="Financeiro"),
            ]
        )
        db.commit()


def _create_store(client) -> dict[str, str]:
    response = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Portfólio", "slug": "loja-portfolio"},
    )
    assert response.status_code == 201
    return response.json()


def test_admin_configura_vendas_e_estoque_e_suspende_sem_apagar(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _seed_catalog()
    _login_admin(client)
    store = _create_store(client)

    configured = client.put(
        f"/control/v1/lojas/{store['id']}/modulos",
        json={"modulos": ["vendas", "estoque"]},
    )

    assert configured.status_code == 200
    assert configured.json() == {
        "items": [
            {"codigo": "estoque", "nome": "Estoque", "estado": "ativo", "versao": 1},
            {"codigo": "vendas", "nome": "Vendas", "estado": "ativo", "versao": 1},
        ]
    }

    suspended = client.post(
        f"/control/v1/lojas/{store['id']}/modulos/vendas/suspender",
        json={"motivo": "contrato reduzido"},
    )
    listed = client.get(f"/control/v1/lojas/{store['id']}/modulos")

    assert suspended.status_code == 200
    assert suspended.json() == {
        "codigo": "vendas",
        "nome": "Vendas",
        "estado": "suspenso",
        "versao": 2,
    }
    assert listed.json() == {
        "items": [
            {"codigo": "estoque", "nome": "Estoque", "estado": "ativo", "versao": 1},
            {"codigo": "vendas", "nome": "Vendas", "estado": "suspenso", "versao": 2},
        ]
    }
