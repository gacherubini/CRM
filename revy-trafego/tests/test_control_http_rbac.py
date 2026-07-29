from dataclasses import replace

from app import main as main_mod
from app.auth import hash_senha
from app.config import settings
from app.control.access import AccessControl
from app.control.types import Actor, RevokeTrafficAccess, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VinculoTrafego
from tests.conftest import csrf_da_resposta


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
