from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VinculoTrafego
from app.web import control as control_mod


def _enable_control(monkeypatch) -> None:
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


def test_rotas_de_pessoas_reutilizam_flag_e_autenticacao_do_control(
    client,
    monkeypatch,
):
    hidden = client.get("/control/v1/pessoas/pessoa-qualquer")

    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "not_found"

    _enable_control(monkeypatch)
    unauthenticated = client.get("/control/v1/pessoas/pessoa-qualquer")

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"]["code"] == "authentication_required"


def test_admin_registra_e_consulta_pessoa_sem_expor_acesso_ou_senha(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")

    created = client.post(
        "/control/v1/pessoas",
        json={
            "nome": "  Ana Souza  ",
            "email": "  ANA.SOUZA@EXAMPLE.COM  ",
        },
    )

    assert created.status_code == 201
    person = created.json()
    assert set(person) == {
        "id",
        "nome",
        "email",
        "criado_em",
        "atualizado_em",
    }
    assert person["nome"] == "Ana Souza"
    assert person["email"] == "ana.souza@example.com"

    retrieved = client.get(f"/control/v1/pessoas/{person['id']}")

    assert retrieved.status_code == 200
    assert retrieved.json() == person


def test_admin_atribui_lista_e_revoga_cargos_ativos_da_loja(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja de Cargos", "slug": "loja-de-cargos"},
    ).json()
    person = client.post(
        "/control/v1/pessoas",
        json={"nome": "Ana Multi Cargo", "email": "ana.cargos@example.com"},
    ).json()
    roles_url = f"/control/v1/lojas/{store['id']}/cargos"

    owner = client.post(
        roles_url,
        json={"pessoa_id": person["id"], "cargo": "dono"},
    )
    manager = client.post(
        roles_url,
        json={"pessoa_id": person["id"], "cargo": "gerente"},
    )
    duplicate = client.post(
        roles_url,
        json={"pessoa_id": person["id"], "cargo": "dono"},
    )
    listed = client.get(roles_url)

    assert owner.status_code == 201
    assert manager.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "store_role_conflict",
        "message": "a Pessoa Revy já possui este cargo ativo na Loja",
    }
    assert {
        (item["pessoa_id"], item["cargo"], item["ativo"])
        for item in listed.json()["items"]
    } == {
        (person["id"], "dono", True),
        (person["id"], "gerente", True),
    }
    assert set(owner.json()) == {
        "id",
        "loja_id",
        "pessoa_id",
        "cargo",
        "origem",
        "origem_id",
        "ativo",
        "iniciado_em",
        "encerrado_em",
    }

    revoked = client.post(
        (
            f"{roles_url}/{person['id']}/dono/revogar"
        ),
        json={"motivo": "troca de proprietário"},
    )
    active_after_revoke = client.get(roles_url)

    assert revoked.status_code == 200
    assert revoked.json()["ativo"] is False
    assert revoked.json()["encerrado_em"] is not None
    assert [
        (item["pessoa_id"], item["cargo"])
        for item in active_after_revoke.json()["items"]
    ] == [(person["id"], "gerente")]


def test_api_mapeia_erros_de_pessoa_e_cargo_sem_expor_detalhes_internos(
    client,
    monkeypatch,
):
    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja de Erros", "slug": "loja-de-erros"},
    ).json()
    person = client.post(
        "/control/v1/pessoas",
        json={"nome": "Pessoa Existente", "email": "existente@example.com"},
    ).json()

    invalid = client.post(
        "/control/v1/pessoas",
        json={"nome": "E-mail Inválido", "email": "email-invalido"},
    )
    duplicate = client.post(
        "/control/v1/pessoas",
        json={"nome": "Pessoa Duplicada", "email": " EXISTENTE@EXAMPLE.COM "},
    )
    missing_person = client.get("/control/v1/pessoas/pessoa-inexistente")
    missing_role = client.post(
        (
            f"/control/v1/lojas/{store['id']}/cargos/"
            f"{person['id']}/dono/revogar"
        ),
        json={},
    )

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == {
        "code": "invalid_person_email",
        "message": "e-mail da Pessoa Revy inválido",
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "person_email_conflict",
        "message": "já existe Pessoa Revy com este e-mail",
    }
    assert missing_person.status_code == 404
    assert missing_person.json()["detail"] == {
        "code": "person_not_found",
        "message": "Pessoa Revy não encontrada",
    }
    assert missing_role.status_code == 404
    assert missing_role.json()["detail"] == {
        "code": "store_role_not_found",
        "message": "cargo ativo não encontrado na Loja",
    }


def test_gestor_lista_cargos_so_da_loja_vinculada_e_nao_pode_mutar(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.cargos.api@revy.local",
            nome="Gestor Cargos API",
            senha_hash=hash_senha("senha-gestor-cargos"),
            papel="gestor",
            ativo=True,
        )
        allowed = Loja(nome="Loja Permitida", slug="loja-cargos-permitida")
        hidden = Loja(nome="Loja Oculta", slug="loja-cargos-oculta")
        db.add_all([manager, allowed, hidden])
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
        hidden_id = hidden.id

    _enable_control(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    person = client.post(
        "/control/v1/pessoas",
        json={"nome": "Pessoa Escopada", "email": "escopada@example.com"},
    ).json()
    allowed_roles_url = f"/control/v1/lojas/{allowed_id}/cargos"
    hidden_roles_url = f"/control/v1/lojas/{hidden_id}/cargos"
    assert client.post(
        allowed_roles_url,
        json={"pessoa_id": person["id"], "cargo": "dono"},
    ).status_code == 201
    assert client.post(
        hidden_roles_url,
        json={"pessoa_id": person["id"], "cargo": "vendedor"},
    ).status_code == 201

    client.cookies.clear()
    _login(client, "gestor.cargos.api@revy.local", "senha-gestor-cargos")

    visible = client.get(allowed_roles_url)
    hidden_response = client.get(hidden_roles_url)
    forbidden_assign = client.post(
        allowed_roles_url,
        json={"pessoa_id": person["id"], "cargo": "gerente"},
    )
    forbidden_revoke = client.post(
        f"{allowed_roles_url}/{person['id']}/dono/revogar",
        json={},
    )
    forbidden_person = client.get(f"/control/v1/pessoas/{person['id']}")

    assert visible.status_code == 200
    assert [
        (item["pessoa_id"], item["cargo"])
        for item in visible.json()["items"]
    ] == [(person["id"], "dono")]
    assert hidden_response.status_code == 404
    assert hidden_response.json()["detail"]["code"] == "store_not_found"
    for response in (forbidden_assign, forbidden_revoke, forbidden_person):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "access_denied"
