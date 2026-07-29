from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VinculoTrafego
from app.web import control as control_mod


def _enable_control(monkeypatch):
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _login(client, email: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"email": email, "senha": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_control_api_fica_oculta_por_padrao(client):
    assert settings.revy_control_enabled is False

    response = client.get("/control/v1/lojas")

    assert response.status_code == 404


def test_control_api_exige_sessao_quando_habilitada(client, monkeypatch):
    _enable_control(monkeypatch)

    response = client.get("/control/v1/lojas")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_listagem_respeita_escopo_do_admin_e_do_gestor(client, monkeypatch):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.api@revy.local",
            nome="Gestor API",
            senha_hash=hash_senha("senha-gestor-api"),
            papel="gestor",
            ativo=True,
        )
        allowed = Loja(nome="Loja API Permitida", slug="loja-api-permitida")
        other = Loja(nome="Loja API Alheia", slug="loja-api-alheia")
        db.add_all([manager, allowed, other])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=allowed.id,
                gestor_id=manager.id,
                tipo="responsavel",
            )
        )
        db.commit()
        allowed_id = allowed.id
        other_id = other.id

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    admin_response = client.get("/control/v1/lojas")

    assert admin_response.status_code == 200
    assert {
        (item["id"], item["vinculo"])
        for item in admin_response.json()["items"]
    } == {(allowed_id, None), (other_id, None)}

    client.cookies.clear()
    _login(client, "gestor.api@revy.local", "senha-gestor-api")
    manager_response = client.get("/control/v1/lojas")

    assert manager_response.status_code == 200
    assert manager_response.json()["items"] == [
        {
            "id": allowed_id,
            "nome": "Loja API Permitida",
            "slug": "loja-api-permitida",
            "estado": "rascunho",
            "vinculo": "responsavel",
        }
    ]


def test_admin_cria_loja_e_gestor_nao_pode_criar(client, monkeypatch):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.sem-mutar@revy.local",
            nome="Gestor Sem Mutar",
            senha_hash=hash_senha("senha-sem-mutar"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    created = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Criada pela API", "slug": "loja-criada-api"},
    )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["nome"] == "Loja Criada pela API"
    assert created_body["slug"] == "loja-criada-api"
    assert created_body["estado"] == "rascunho"
    assert created_body["id"]

    client.cookies.clear()
    _login(client, "gestor.sem-mutar@revy.local", "senha-sem-mutar")
    forbidden = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Negada", "slug": "loja-negada"},
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "access_denied"


def test_admin_edita_somente_loja_em_rascunho(client, monkeypatch):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.sem-editar@revy.local",
            nome="Gestor Sem Editar",
            senha_hash=hash_senha("senha-sem-editar"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Antes API", "slug": "loja-antes-api"},
    ).json()

    updated = client.patch(
        f"/control/v1/lojas/{store['id']}",
        json={"nome": "Loja Depois API"},
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "id": store["id"],
        "nome": "Loja Depois API",
        "slug": "loja-antes-api",
        "estado": "rascunho",
    }
    immutable_slug = client.patch(
        f"/control/v1/lojas/{store['id']}",
        json={"nome": "Loja Depois API", "slug": "loja-nova-api"},
    )
    assert immutable_slug.status_code == 422

    client.cookies.clear()
    _login(client, "gestor.sem-editar@revy.local", "senha-sem-editar")
    forbidden = client.patch(
        f"/control/v1/lojas/{store['id']}",
        json={"nome": "Loja Negada"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "access_denied"

    client.cookies.clear()
    _login(client, "trafego@revy.local", "secret-teste")
    transitioned = client.post(
        f"/control/v1/lojas/{store['id']}/estado",
        json={"estado": "em_configuracao"},
    )
    assert transitioned.status_code == 200
    blocked = client.patch(
        f"/control/v1/lojas/{store['id']}",
        json={"nome": "Loja Tardia"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "store_edit_conflict"


def test_gestor_consulta_somente_loja_do_proprio_escopo(client, monkeypatch):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.consulta@revy.local",
            nome="Gestor Consulta",
            senha_hash=hash_senha("senha-consulta"),
            papel="gestor",
            ativo=True,
        )
        allowed = Loja(nome="Loja Consultável", slug="loja-consultavel")
        denied = Loja(nome="Loja Não Consultável", slug="loja-nao-consultavel")
        db.add_all([manager, allowed, denied])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=allowed.id,
                gestor_id=manager.id,
                tipo="colaborador",
            )
        )
        db.commit()
        allowed_id = allowed.id
        denied_id = denied.id

    _enable_control(monkeypatch)
    _login(client, "gestor.consulta@revy.local", "senha-consulta")

    visible = client.get(f"/control/v1/lojas/{allowed_id}")
    hidden = client.get(f"/control/v1/lojas/{denied_id}")

    assert visible.status_code == 200
    assert visible.json() == {
        "id": allowed_id,
        "nome": "Loja Consultável",
        "slug": "loja-consultavel",
        "estado": "rascunho",
    }
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "store_not_found"


def test_admin_transiciona_loja_e_salto_invalido_retorna_conflito(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    created = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja em Onboarding", "slug": "loja-em-onboarding"},
    ).json()

    transitioned = client.post(
        f"/control/v1/lojas/{created['id']}/estado",
        json={"estado": "em_configuracao", "motivo": "onboarding iniciado"},
    )
    invalid = client.post(
        f"/control/v1/lojas/{created['id']}/estado",
        json={"estado": "ativa"},
    )

    assert transitioned.status_code == 200
    assert transitioned.json()["estado"] == "em_configuracao"
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "invalid_store_transition"


def test_admin_reativa_loja_suspensa_sem_expor_versao(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        store = Loja(
            nome="Loja Suspensa API",
            slug="loja-suspensa-api",
            status="suspensa",
        )
        db.add(store)
        db.commit()
        store_id = store.id

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    reactivated = client.post(
        f"/control/v1/lojas/{store_id}/estado",
        json={"estado": "ativa", "motivo": "reativação explícita"},
    )

    assert reactivated.status_code == 200
    assert reactivated.json() == {
        "id": store_id,
        "nome": "Loja Suspensa API",
        "slug": "loja-suspensa-api",
        "estado": "ativa",
    }


def test_loja_encerrada_permanece_terminal_na_api(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        store = Loja(
            nome="Loja Encerrada API",
            slug="loja-encerrada-api",
            status="encerrada",
        )
        db.add(store)
        db.commit()
        store_id = store.id

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    blocked = client.post(
        f"/control/v1/lojas/{store_id}/estado",
        json={"estado": "ativa"},
    )
    current = client.get(f"/control/v1/lojas/{store_id}")

    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "invalid_store_transition"
    assert current.status_code == 200
    assert current.json()["estado"] == "encerrada"


def test_transicao_para_pronta_sem_dono_mapeia_bloqueio_de_prontidao(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja sem Dono API", "slug": "loja-sem-dono-api"},
    ).json()
    client.post(
        f"/control/v1/lojas/{store['id']}/estado",
        json={"estado": "em_configuracao"},
    )

    blocked = client.post(
        f"/control/v1/lojas/{store['id']}/estado",
        json={"estado": "pronta"},
    )
    current = client.get(f"/control/v1/lojas/{store['id']}")

    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "store_readiness_blocked"
    assert current.status_code == 200
    assert current.json()["estado"] == "em_configuracao"


def test_api_revoga_cargo_pelo_id_da_atribuicao(client, monkeypatch):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Cargo por ID", "slug": "loja-cargo-id"},
    ).json()
    person = client.post(
        "/control/v1/pessoas",
        json={"nome": "Pessoa Cargo API", "email": "cargo.api@example.com"},
    ).json()
    role = client.post(
        f"/control/v1/lojas/{store['id']}/cargos",
        json={"pessoa_id": person["id"], "cargo": "dono"},
    ).json()

    revoked = client.post(
        f"/control/v1/lojas/{store['id']}/cargos/{role['id']}/revogar",
        json={"motivo": "troca comercial"},
    )
    repeated = client.post(
        f"/control/v1/lojas/{store['id']}/cargos/{role['id']}/revogar",
        json={},
    )

    assert revoked.status_code == 200
    assert revoked.json()["id"] == role["id"]
    assert revoked.json()["ativo"] is False
    assert repeated.status_code == 404
    assert repeated.json()["detail"]["code"] == "store_role_not_found"


def test_api_nao_revela_cargo_de_outra_loja(client, monkeypatch):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    source = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Origem API", "slug": "loja-origem-api"},
    ).json()
    target = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja Destino API", "slug": "loja-destino-api"},
    ).json()
    person = client.post(
        "/control/v1/pessoas",
        json={"nome": "Pessoa Isolada", "email": "isolada.api@example.com"},
    ).json()
    role = client.post(
        f"/control/v1/lojas/{source['id']}/cargos",
        json={"pessoa_id": person["id"], "cargo": "dono"},
    ).json()

    hidden = client.post(
        f"/control/v1/lojas/{target['id']}/cargos/{role['id']}/revogar",
        json={},
    )
    source_roles = client.get(f"/control/v1/lojas/{source['id']}/cargos")

    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "store_role_not_found"
    assert [(item["id"], item["ativo"]) for item in source_roles.json()["items"]] == [
        (role["id"], True),
    ]


def test_admin_concede_revoga_e_consulta_auditoria_da_loja(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        first = GestorRevy(
            email="primeiro.api@revy.local",
            nome="Primeiro Gestor",
            senha_hash=hash_senha("senha-primeiro"),
            papel="gestor",
            ativo=True,
        )
        second = GestorRevy(
            email="segundo.api@revy.local",
            nome="Segundo Gestor",
            senha_hash=hash_senha("senha-segundo"),
            papel="gestor",
            ativo=True,
        )
        db.add_all([first, second])
        db.commit()
        first_id = first.id
        second_id = second.id

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja com Gestores", "slug": "loja-com-gestores"},
    ).json()

    granted = client.post(
        f"/control/v1/lojas/{store['id']}/gestores",
        json={"gestor_id": first_id, "tipo": "responsavel"},
    )
    conflict = client.post(
        f"/control/v1/lojas/{store['id']}/gestores",
        json={"gestor_id": second_id, "tipo": "responsavel"},
    )
    revoked = client.post(
        f"/control/v1/lojas/{store['id']}/gestores/{first_id}/revogar",
        json={"motivo": "troca operacional"},
    )
    audit = client.get(f"/control/v1/lojas/{store['id']}/auditoria")

    assert granted.status_code == 201
    assert granted.json()["tipo"] == "responsavel"
    assert granted.json()["ativo"] is True
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "active_responsible_conflict"
    assert revoked.status_code == 200
    assert revoked.json()["ativo"] is False
    assert audit.status_code == 200
    assert [event["acao"] for event in audit.json()["items"]] == [
        "store.created",
        "traffic_access.granted",
        "traffic_access.revoked",
    ]
    assert audit.json()["items"][-1]["motivo"] == "troca operacional"
