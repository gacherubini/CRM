from dataclasses import replace

from app import main as main_mod
from app.auth import hash_senha
from app.config import settings
from app.control.access import AccessControl
from app.control.types import Actor, RevokeTrafficAccess, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VinculoTrafego
from tests.conftest import csrf_da_resposta


def test_rbac_ignora_loja_slug_manual_e_so_aceita_loja_id_autorizada(
    client,
    monkeypatch,
):
    """Com REVY_CONTROL_RBAC_ENABLED, slug livre não autoriza loja alheia."""
    with SessionLocal() as db:
        gestor = GestorRevy(
            email="gestor.slug.manual@revy.local",
            nome="Gestor Slug",
            senha_hash=hash_senha("segredo-gestor"),
            papel="gestor",
            ativo=True,
        )
        loja_permitida = Loja(nome="Permitida Slug", slug="permitida-slug")
        loja_alheia = Loja(nome="Alheia Slug", slug="alheia-slug")
        db.add_all([gestor, loja_permitida, loja_alheia])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=loja_permitida.id,
                gestor_id=gestor.id,
                tipo="colaborador",
            )
        )
        db.commit()
        loja_permitida_id = loja_permitida.id

    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(settings, revy_control_rbac_enabled=True),
    )
    client.post(
        "/login",
        data={
            "email": "gestor.slug.manual@revy.local",
            "senha": "segredo-gestor",
        },
        follow_redirects=False,
    )
    home = client.get("/app")
    assert home.status_code == 200
    assert "loja_slug_manual" not in home.text
    assert "Outra loja" not in home.text

    # POST legado com slug livre: caminho RBAC exige loja_id → não autoriza
    via_slug = client.post(
        "/app/loja",
        data={
            "loja_slug": "alheia-slug",
            "loja_slug_manual": "alheia-slug",
            "csrf": csrf_da_resposta(home),
        },
        follow_redirects=False,
    )
    assert via_slug.status_code == 303
    assert "erro=loja" in (via_slug.headers.get("location") or "")
    trafego = client.get("/app/trafego", follow_redirects=False)
    assert trafego.status_code in (303, 404)

    ok = client.post(
        "/app/loja",
        data={
            "loja_id": loja_permitida_id,
            "csrf": csrf_da_resposta(home),
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert client.get("/app/trafego").status_code == 200


def test_gestor_seleciona_somente_loja_com_vinculo_ativo(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        gestor = GestorRevy(
            email="gestor.escopado@revy.local",
            nome="Gestor Escopado",
            senha_hash=hash_senha("segredo-gestor"),
            papel="gestor",
            ativo=True,
        )
        loja_permitida = Loja(nome="Loja Permitida", slug="loja-permitida")
        loja_alheia = Loja(nome="Loja Alheia", slug="loja-alheia")
        db.add_all([gestor, loja_permitida, loja_alheia])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=loja_permitida.id,
                gestor_id=gestor.id,
                tipo="responsavel",
            )
        )
        db.commit()
        loja_permitida_id = loja_permitida.id
        loja_alheia_id = loja_alheia.id

    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(settings, revy_control_rbac_enabled=True),
    )
    login = client.post(
        "/login",
        data={
            "email": "gestor.escopado@revy.local",
            "senha": "segredo-gestor",
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    home = client.get("/app")
    assert home.status_code == 200
    assert "Loja Permitida" in home.text
    assert "Loja Alheia" not in home.text
    assert "Outra loja" not in home.text

    denied = client.post(
        "/app/loja",
        data={
            "loja_id": loja_alheia_id,
            "csrf": csrf_da_resposta(home),
        },
        follow_redirects=False,
    )
    assert denied.status_code == 404

    selected = client.post(
        "/app/loja",
        data={
            "loja_id": loja_permitida_id,
            "csrf": csrf_da_resposta(home),
        },
        follow_redirects=False,
    )
    assert selected.status_code == 303
    assert selected.headers["location"].endswith("/app/trafego")
    assert client.get("/app/trafego").status_code == 200


def test_revogacao_encerra_acesso_na_requisicao_seguinte(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        gestor = GestorRevy(
            email="gestor.revogado@revy.local",
            nome="Gestor Revogado",
            senha_hash=hash_senha("segredo-gestor"),
            papel="gestor",
            ativo=True,
        )
        loja = Loja(nome="Loja Revogada", slug="loja-revogada")
        db.add_all([gestor, loja])
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=loja.id,
                gestor_id=gestor.id,
                tipo="colaborador",
            )
        )
        db.commit()
        admin_actor = Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )
        gestor_id = gestor.id
        loja_id = loja.id

    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(settings, revy_control_rbac_enabled=True),
    )
    client.post(
        "/login",
        data={
            "email": "gestor.revogado@revy.local",
            "senha": "segredo-gestor",
        },
        follow_redirects=False,
    )
    home = client.get("/app")
    selected = client.post(
        "/app/loja",
        data={"loja_id": loja_id, "csrf": csrf_da_resposta(home)},
        follow_redirects=False,
    )
    assert selected.status_code == 303
    assert client.get("/app/trafego").status_code == 200

    AccessControl(SessionLocal).revoke(
        admin_actor,
        RevokeTrafficAccess(
            store=StoreRef(id=loja_id),
            manager_id=gestor_id,
            reason="fim do acesso",
        ),
    )

    assert client.get("/app/trafego").status_code == 404
