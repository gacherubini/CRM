from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.db import SessionLocal
from app.models import GestorRevy, ModuloRevy, VinculoTrafego
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
            ]
        )
        db.commit()


def _create_store(client, name: str, slug: str) -> dict[str, str]:
    response = client.post(
        "/control/v1/lojas",
        json={"nome": name, "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


def test_cobranca_atrasada_alerta_sem_suspender_loja_ou_modulo(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _seed_catalog()
    _login_admin(client)
    store = _create_store(
        client,
        "Loja Contrato",
        "loja-contrato-http",
    )
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


def test_contrato_http_exige_sessao_e_valida_ausencia_e_payload(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)

    unauthenticated = client.get(
        "/control/v1/lojas/loja-inexistente/contrato"
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"]["code"] == (
        "authentication_required"
    )

    _login_admin(client)
    store = _create_store(
        client,
        "Loja Contrato Vazio",
        "loja-contrato-vazio",
    )
    missing = client.get(f"/control/v1/lojas/{store['id']}/contrato")
    invalid = client.put(
        f"/control/v1/lojas/{store['id']}/contrato",
        json={
            "valor_mensal": "100.00",
            "vigencia_inicio": "2026-08-01",
            "vigencia_fim": "2026-07-31",
            "vencimento_dia": 10,
            "situacao_cobranca": "em_dia",
        },
    )

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "contract_not_found"
    assert invalid.status_code == 422


def test_gestor_consulta_contrato_vinculado_sem_poder_alterar(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login_admin(client)
    linked = _create_store(
        client,
        "Loja Contrato Vinculado",
        "loja-contrato-vinculado",
    )
    hidden = _create_store(
        client,
        "Loja Contrato Oculto",
        "loja-contrato-oculto-http",
    )
    contract = {
        "valor_mensal": "500.00",
        "vigencia_inicio": "2026-08-01",
        "vigencia_fim": None,
        "vencimento_dia": 15,
        "situacao_cobranca": "em_dia",
    }
    for store in (linked, hidden):
        response = client.put(
            f"/control/v1/lojas/{store['id']}/contrato",
            json=contract,
        )
        assert response.status_code == 200

    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.contrato.http@revy.local",
            nome="Gestor Contrato HTTP",
            senha_hash=hash_senha("segredo-contrato-http"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=linked["id"],
                gestor_id=manager.id,
                tipo="colaborador",
            )
        )
        db.commit()

    login = client.post(
        "/login",
        data={
            "email": "gestor.contrato.http@revy.local",
            "senha": "segredo-contrato-http",
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    allowed = client.get(f"/control/v1/lojas/{linked['id']}/contrato")
    denied = client.get(f"/control/v1/lojas/{hidden['id']}/contrato")
    write = client.put(
        f"/control/v1/lojas/{linked['id']}/contrato",
        json=contract,
    )

    assert allowed.status_code == 200
    assert allowed.json()["loja_id"] == linked["id"]
    assert denied.status_code == 404
    assert denied.json()["detail"]["code"] == "store_not_found"
    assert write.status_code == 403
    assert write.json()["detail"]["code"] == "access_denied"
