"""Import push de usuários do Portal → Pessoa + CargoLoja."""

from dataclasses import replace

import pytest

from app.control.people import PeopleDirectory
from app.control.portal_import import (
    PortalUserImporter,
    PortalUserImportRow,
)
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    AssignStoreRole,
    CreateStore,
    PersonRef,
    RegisterPerson,
    StoreRef,
    StoreRole,
)
from app.db import SessionLocal
from app.models import CargoLoja, GestorRevy
from app.web import control as control_mod


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _manager_actor(email: str) -> Actor:
    with SessionLocal() as db:
        manager = GestorRevy(
            email=email,
            nome=email.split("@", 1)[0].title(),
            senha_hash="hash-nao-usado-neste-teste",
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()
        db.refresh(manager)
        return Actor(
            id=manager.id,
            email=manager.email,
            name=manager.nome,
            role=manager.papel,
        )


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(control_mod.settings, revy_control_enabled=True),
    )


def _login(client, email: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"email": email, "senha": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_importa_usuario_portal_como_pessoa_e_cargo_com_origem():
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Portal", slug="loja-portal"),
    )
    importer = PortalUserImporter(SessionLocal)

    result = importer.import_rows(
        admin,
        [
            PortalUserImportRow(
                email="  VENDEDOR@PORTAL.EXAMPLE  ",
                name="  João Vendedor  ",
                store_slug="loja-portal",
                role="vendedor",
                origem_id="portal-user-1",
            ),
        ],
    )

    person = PeopleDirectory(SessionLocal).find_by_email(
        admin, "vendedor@portal.example"
    )
    roles = StoreRoles(SessionLocal).list_for_store(
        admin, StoreRef(id=store.id)
    )
    with SessionLocal() as db:
        cargo = (
            db.query(CargoLoja)
            .filter(
                CargoLoja.origem == "portal",
                CargoLoja.origem_id == "portal-user-1",
            )
            .one()
        )

    assert result.imported == 1
    assert result.skipped == 0
    assert result.conflicts == ()
    assert person is not None
    assert person.name == "João Vendedor"
    assert person.email == "vendedor@portal.example"
    assert len(roles) == 1
    assert roles[0].person_id == person.id
    assert roles[0].role is StoreRole.SELLER
    assert roles[0].source == "portal"
    assert roles[0].source_id == "portal-user-1"
    assert cargo.pessoa_id == person.id
    assert cargo.loja_id == store.id


def test_import_idempotente_por_origem_e_por_cargo_existente():
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Idem", slug="loja-idem"),
    )
    people = PeopleDirectory(SessionLocal)
    roles = StoreRoles(SessionLocal)
    importer = PortalUserImporter(SessionLocal)
    row = PortalUserImportRow(
        email="idem@portal.example",
        name="Idem Portal",
        store_slug="loja-idem",
        role="gerente",
        origem_id="portal-idem-1",
    )

    first = importer.import_rows(admin, [row])
    second = importer.import_rows(admin, [row])

    person = people.find_by_email(admin, "idem@portal.example")
    assert person is not None
    # Mesmo papel já ativo (origem control) → skip, sem conflito.
    roles.assign(
        admin,
        AssignStoreRole(
            store=StoreRef(id=store.id),
            person=PersonRef(id=person.id),
            role=StoreRole.OWNER,
        ),
    )
    same_role_again = importer.import_rows(
        admin,
        [
            PortalUserImportRow(
                email="idem@portal.example",
                name="Idem Portal",
                store_slug="loja-idem",
                role="dono",
                origem_id="portal-idem-dono",
            ),
        ],
    )

    active = roles.list_for_store(admin, StoreRef(id=store.id))
    assert first.imported == 1
    assert second.imported == 0
    assert second.skipped == 1
    assert second.conflicts == ()
    assert same_role_again.imported == 0
    assert same_role_again.skipped == 1
    assert same_role_again.conflicts == ()
    assert {
        (item.role, item.source, item.source_id)
        for item in active
    } == {
        (StoreRole.MANAGER, "portal", "portal-idem-1"),
        (StoreRole.OWNER, "control", None),
    }


def test_import_registra_conflitos_e_pula_inativos():
    admin = _admin_actor()
    StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Conflitos", slug="loja-conflitos"),
    )
    importer = PortalUserImporter(SessionLocal)

    result = importer.import_rows(
        admin,
        [
            PortalUserImportRow(
                email="inativo@portal.example",
                name="Inativo",
                store_slug="loja-conflitos",
                role="vendedor",
                origem_id="portal-inactive",
                active=False,
            ),
            PortalUserImportRow(
                email="sem-loja@portal.example",
                name="Sem Loja",
                store_slug="loja-inexistente",
                role="vendedor",
                origem_id="portal-missing-store",
            ),
            PortalUserImportRow(
                email="email-invalido",
                name="Ruim",
                store_slug="loja-conflitos",
                role="vendedor",
                origem_id="portal-bad-email",
            ),
            PortalUserImportRow(
                email="cargo-ruim@portal.example",
                name="Cargo Ruim",
                store_slug="loja-conflitos",
                role="admin",
                origem_id="portal-bad-role",
            ),
            PortalUserImportRow(
                email="sem-nome@portal.example",
                name="  ",
                store_slug="loja-conflitos",
                role="dono",
                origem_id="portal-no-name",
            ),
        ],
    )

    person = PeopleDirectory(SessionLocal).find_by_email(
        admin, "sem-nome@portal.example"
    )
    assert result.imported == 1
    assert result.skipped == 1
    assert [
        (c.code, c.email, c.store_slug) for c in result.conflicts
    ] == [
        ("store_not_found", "sem-loja@portal.example", "loja-inexistente"),
        ("invalid_person_email", "email-invalido", "loja-conflitos"),
        ("invalid_role", "cargo-ruim@portal.example", "loja-conflitos"),
    ]
    assert person is not None
    assert person.name == "sem-nome"


def test_import_reusa_pessoa_existente_por_email():
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Reuso", slug="loja-reuso"),
    )
    existing = PeopleDirectory(SessionLocal).register(
        admin,
        RegisterPerson(name="Pessoa Já Cadastrada", email="reuso@portal.example"),
    )
    importer = PortalUserImporter(SessionLocal)

    result = importer.import_rows(
        admin,
        [
            PortalUserImportRow(
                email=" REUSO@PORTAL.EXAMPLE ",
                name="Nome Diferente",
                store_slug="loja-reuso",
                role="vendedor",
                origem_id="portal-reuso-1",
            ),
        ],
    )
    roles = StoreRoles(SessionLocal).list_for_store(
        admin, StoreRef(id=store.id)
    )

    assert result.imported == 1
    assert result.conflicts == ()
    assert len(roles) == 1
    assert roles[0].person_id == existing.id
    assert roles[0].source == "portal"
    assert roles[0].source_id == "portal-reuso-1"


def test_somente_admin_pode_importar_usuarios_do_portal():
    admin = _admin_actor()
    manager = _manager_actor("gestor.import@revy.local")
    StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Admin Only", slug="loja-admin-only"),
    )
    importer = PortalUserImporter(SessionLocal)

    with pytest.raises(AccessDenied):
        importer.import_rows(
            manager,
            [
                PortalUserImportRow(
                    email="negado@portal.example",
                    name="Negado",
                    store_slug="loja-admin-only",
                    role="vendedor",
                    origem_id="portal-denied",
                ),
            ],
        )


def test_http_import_portal_usuarios_admin_only(client, monkeypatch):
    hidden = client.post(
        "/control/v1/imports/portal-usuarios",
        json={"usuarios": []},
    )
    assert hidden.status_code == 404

    _enable_control(monkeypatch)
    unauthenticated = client.post(
        "/control/v1/imports/portal-usuarios",
        json={"usuarios": []},
    )
    assert unauthenticated.status_code == 401

    _login(client, "trafego@revy.local", "secret-teste")
    store = client.post(
        "/control/v1/lojas",
        json={"nome": "Loja HTTP Import", "slug": "loja-http-import"},
    ).json()

    response = client.post(
        "/control/v1/imports/portal-usuarios",
        json={
            "usuarios": [
                {
                    "email": "http.portal@example.com",
                    "nome": "HTTP Portal",
                    "loja_slug": "loja-http-import",
                    "cargo": "vendedor",
                    "origem_id": "portal-http-1",
                    "ativo": True,
                },
                {
                    "email": "falha@example.com",
                    "nome": "Falha",
                    "loja_slug": "slug-inexistente",
                    "cargo": "gerente",
                    "origem_id": "portal-http-2",
                },
                {
                    "email": "off@example.com",
                    "nome": "Off",
                    "loja_slug": "loja-http-import",
                    "cargo": "dono",
                    "origem_id": "portal-http-3",
                    "ativo": False,
                },
            ]
        },
    )
    cargos = client.get(f"/control/v1/lojas/{store['id']}/cargos").json()
    person = client.get(
        "/control/v1/pessoas",
        params={"email": "http.portal@example.com"},
    ).json()

    assert response.status_code == 200
    body = response.json()
    assert body["importados"] == 1
    assert body["ignorados"] == 1
    assert body["conflitos"] == [
        {
            "email": "falha@example.com",
            "loja_slug": "slug-inexistente",
            "code": "store_not_found",
            "message": "Loja não encontrada",
        }
    ]
    assert len(cargos["items"]) == 1
    assert cargos["items"][0]["pessoa_id"] == person["id"]
    assert cargos["items"][0]["cargo"] == "vendedor"

    # Idempotência via HTTP.
    again = client.post(
        "/control/v1/imports/portal-usuarios",
        json={
            "usuarios": [
                {
                    "email": "http.portal@example.com",
                    "nome": "HTTP Portal",
                    "loja_slug": "loja-http-import",
                    "cargo": "vendedor",
                    "origem_id": "portal-http-1",
                }
            ]
        },
    )
    assert again.status_code == 200
    assert again.json() == {
        "importados": 0,
        "ignorados": 1,
        "conflitos": [],
    }
