from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.db import SessionLocal
from app.models import AcessoControl, GestorRevy, Pessoa, agora
from app.web import control as control_mod


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _seed_canonical_access(
    *,
    email: str = "gestor.canonico@example.com",
    password: str = "senha-canonica-segura",
    role: str = "gestor",
) -> str:
    now = agora()
    password_hash = hash_senha(password)
    with SessionLocal() as db:
        person = Pessoa(
            email=email,
            nome="Gestor Canônico",
            criada_em=now,
            atualizada_em=now,
        )
        db.add(person)
        db.flush()
        access = AcessoControl(
            pessoa_id=person.id,
            papel=role,
            estado="ativo",
            senha_hash=password_hash,
            sessao_versao=1,
            gestor_legado_id=None,
            criada_em=now,
            atualizada_em=now,
        )
        db.add(access)
        db.commit()
        return access.id


def test_acesso_ativo_sem_gestor_legado_autentica_e_abre_sessao(client):
    access_id = _seed_canonical_access()

    with SessionLocal() as db:
        assert db.query(GestorRevy).filter(GestorRevy.email == "gestor.canonico@example.com").count() == 0

    login = client.post(
        "/login",
        data={"email": "gestor.canonico@example.com", "senha": "senha-canonica-segura"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"].endswith("/app")

    home = client.get("/app", follow_redirects=False)
    assert home.status_code == 200

    with SessionLocal() as db:
        access = db.get(AcessoControl, access_id)
        assert access is not None
        assert access.gestor_legado_id is None
        assert db.query(GestorRevy).filter(GestorRevy.id == access_id).count() == 0


def test_acesso_canonico_constroi_actor_nas_apis_control(client, monkeypatch):
    _enable_control(monkeypatch)
    _seed_canonical_access(email="admin.canonico@example.com", role="admin")

    login = client.post(
        "/login",
        data={"email": "admin.canonico@example.com", "senha": "senha-canonica-segura"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    listed = client.get("/control/v1/acessos")
    assert listed.status_code == 200
    body = listed.json()
    assert "items" in body
    assert any(
        item["pessoa"]["email"] == "admin.canonico@example.com"
        for item in body["items"]
    )
