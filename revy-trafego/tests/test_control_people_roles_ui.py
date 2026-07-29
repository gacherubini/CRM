from dataclasses import replace
import re

from app.auth import hash_senha
from app.config import settings
from app.control.access import AccessControl
from app.control.stores import StoreControl
from app.control.types import (
    Actor,
    CreateStore,
    GrantTrafficAccess,
    StoreRef,
    TrafficRole,
)
from app.db import SessionLocal
from app.models import AcessoControl, GestorRevy, Pessoa, agora
from app.web import control_ui as control_ui_mod
from tests.conftest import csrf_da_resposta


def _enable_control_ui(monkeypatch) -> None:
    monkeypatch.setattr(
        control_ui_mod,
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


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def test_admin_cadastra_pessoa_e_atribui_cargos_pelo_detalhe_da_loja(
    client,
    monkeypatch,
):
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Pessoas UI", slug="loja-pessoas-ui"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail_url = f"/app/control/lojas/{store.id}"
    detail = client.get(detail_url)

    assert detail.status_code == 200
    assert 'id="form-atribuir-cargo"' in detail.text

    owner = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf_da_resposta(detail),
            "email": "  ANA.PESSOA@EXAMPLE.COM  ",
            "nome": "  Ana Pessoa  ",
            "cargo": "dono",
        },
        follow_redirects=False,
    )

    assert owner.status_code == 303
    assert "ok=cargo" in owner.headers["location"]
    owner_page = client.get(owner.headers["location"])
    assert "Cargo atribuído à Pessoa Revy." in owner_page.text
    assert "Ana Pessoa" in owner_page.text
    assert "ana.pessoa@example.com" in owner_page.text
    assert "dono" in owner_page.text
    assert 'name="senha"' not in owner_page.text
    assert ">Origem<" not in owner_page.text

    manager = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf_da_resposta(owner_page),
            "email": "ANA.PESSOA@EXAMPLE.COM",
            "nome": "",
            "cargo": "gerente",
        },
        follow_redirects=False,
    )

    assert manager.status_code == 303
    final_page = client.get(manager.headers["location"])
    assert "dono" in final_page.text
    assert "gerente" in final_page.text


def test_admin_revoga_cargo_pela_linha_e_segunda_revogacao_falha_explicita(
    client,
    monkeypatch,
):
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Revogação UI", slug="loja-revogacao-ui"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail_url = f"/app/control/lojas/{store.id}"
    detail = client.get(detail_url)
    assigned = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf_da_resposta(detail),
            "email": "revogada@example.com",
            "nome": "Pessoa Revogada",
            "cargo": "dono",
        },
        follow_redirects=False,
    )
    assigned_page = client.get(assigned.headers["location"])
    match = re.search(
        rf'action="([^"]*/app/control/lojas/{store.id}/cargos/[^"]+/revogar)"',
        assigned_page.text,
    )
    assert match is not None
    revoke_url = match.group(1)

    revoked = client.post(
        revoke_url,
        data={
            "csrf": csrf_da_resposta(assigned_page),
            "motivo": "troca de responsável comercial",
        },
        follow_redirects=False,
    )

    assert revoked.status_code == 303
    assert "ok=cargo_revogado" in revoked.headers["location"]
    revoked_page = client.get(revoked.headers["location"])
    assert "Cargo da Pessoa Revy revogado." in revoked_page.text
    assert "Pessoa Revogada" not in revoked_page.text
    assert "Nenhum cargo ativo nesta Loja." in revoked_page.text

    missing = client.post(
        revoke_url,
        data={"csrf": csrf_da_resposta(revoked_page)},
    )

    assert missing.status_code == 404
    assert "Cargo ativo não encontrado na Loja." in missing.text


def test_loja_inexistente_nao_cadastra_pessoa_antes_de_falhar(
    client,
    monkeypatch,
):
    reference_store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja CSRF", slug="loja-csrf-pessoas"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    reference_page = client.get(f"/app/control/lojas/{reference_store.id}")

    missing_store = client.post(
        "/app/control/lojas/loja-inexistente/cargos",
        data={
            "csrf": csrf_da_resposta(reference_page),
            "email": "nao.criar@example.com",
            "nome": "Não Deve Ser Criada",
            "cargo": "dono",
        },
    )

    assert missing_store.status_code == 404
    assert "Loja não encontrada." in missing_store.text

    real_store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Real", slug="loja-real-pessoas"),
    )
    real_page = client.get(f"/app/control/lojas/{real_store.id}")
    absent_person = client.post(
        f"/app/control/lojas/{real_store.id}/cargos",
        data={
            "csrf": csrf_da_resposta(real_page),
            "email": "nao.criar@example.com",
            "nome": "",
            "cargo": "dono",
        },
    )

    assert absent_person.status_code == 422
    assert "Informe o nome para cadastrar uma nova Pessoa Revy." in absent_person.text


def test_prontidao_sem_dono_ativo_retorna_erro_no_detalhe(
    client,
    monkeypatch,
):
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja sem Dono", slug="loja-sem-dono-ui"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail_url = f"/app/control/lojas/{store.id}"
    detail = client.get(detail_url)
    configuring = client.post(
        f"{detail_url}/estado",
        data={
            "csrf": csrf_da_resposta(detail),
            "estado": "em_configuracao",
        },
        follow_redirects=False,
    )
    assert configuring.status_code == 303
    configuring_page = client.get(configuring.headers["location"])

    blocked = client.post(
        f"{detail_url}/estado",
        data={
            "csrf": csrf_da_resposta(configuring_page),
            "estado": "pronta",
        },
    )

    assert blocked.status_code == 409
    assert "Loja precisa manter ao menos um Dono ativo neste estado" in blocked.text
    assert "em_configuracao" in blocked.text


def test_formularios_de_cargo_validam_csrf_email_pessoa_e_duplicidade(
    client,
    monkeypatch,
):
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Validações", slug="loja-validacoes-cargo"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail_url = f"/app/control/lojas/{store.id}"
    detail = client.get(detail_url)
    csrf = csrf_da_resposta(detail)

    invalid_csrf = client.post(
        f"{detail_url}/cargos",
        data={
            "email": "csrf@example.com",
            "nome": "Sem CSRF",
            "cargo": "dono",
        },
    )
    invalid_email = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf,
            "email": "email-invalido",
            "nome": "E-mail Inválido",
            "cargo": "dono",
        },
    )
    absent_person = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf,
            "email": "pessoa.ausente@example.com",
            "nome": "",
            "cargo": "dono",
        },
    )
    assigned = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf,
            "email": "duplicada@example.com",
            "nome": "Pessoa Duplicada",
            "cargo": "gerente",
        },
        follow_redirects=False,
    )
    assert assigned.status_code == 303
    assigned_page = client.get(assigned.headers["location"])
    duplicate = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf_da_resposta(assigned_page),
            "email": "DUPLICADA@EXAMPLE.COM",
            "nome": "",
            "cargo": "gerente",
        },
    )
    missing_role = client.post(
        f"{detail_url}/cargos/cargo-ausente/revogar",
        data={"csrf": csrf_da_resposta(assigned_page)},
    )

    assert invalid_csrf.status_code == 403
    assert "CSRF" in invalid_csrf.text
    assert invalid_email.status_code == 422
    assert "Informe um e-mail válido para a Pessoa Revy." in invalid_email.text
    assert absent_person.status_code == 422
    assert "Informe o nome para cadastrar uma nova Pessoa Revy." in absent_person.text
    assert duplicate.status_code == 409
    assert "Essa pessoa já possui esse cargo ativo na Loja." in duplicate.text
    assert missing_role.status_code == 404
    assert "Cargo ativo não encontrado na Loja." in missing_role.text


def test_gestor_vinculado_nao_ve_pii_formularios_nem_pode_postar_cargos(
    client,
    monkeypatch,
):
    with SessionLocal() as db:
        manager = GestorRevy(
            email="gestor.pessoas.ui@revy.local",
            nome="Gestor Pessoas UI",
            senha_hash=hash_senha("senha-gestor-pessoas"),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()
        manager_id = manager.id

    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja PII Protegida", slug="loja-pii-protegida"),
    )
    AccessControl(SessionLocal).grant(
        admin,
        GrantTrafficAccess(
            store=StoreRef(id=store.id),
            manager_id=manager_id,
            role=TrafficRole.COLLABORATOR,
        ),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail_url = f"/app/control/lojas/{store.id}"
    detail = client.get(detail_url)
    assigned = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf_da_resposta(detail),
            "email": "dado.pessoal@example.com",
            "nome": "Dado Pessoal Protegido",
            "cargo": "dono",
        },
        follow_redirects=False,
    )
    admin_page = client.get(assigned.headers["location"])
    revoke_match = re.search(
        rf'action="([^"]*/app/control/lojas/{store.id}/cargos/[^"]+/revogar)"',
        admin_page.text,
    )
    assert revoke_match is not None

    client.cookies.clear()
    _login(client, "gestor.pessoas.ui@revy.local", "senha-gestor-pessoas")
    manager_page = client.get(detail_url)

    assert manager_page.status_code == 200
    assert "Dado Pessoal Protegido" not in manager_page.text
    assert "dado.pessoal@example.com" not in manager_page.text
    assert 'id="pessoas-cargos"' not in manager_page.text
    assert 'id="form-atribuir-cargo"' not in manager_page.text
    home = client.get("/app")
    csrf = csrf_da_resposta(home)
    forbidden_assign = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf,
            "email": "outra@example.com",
            "nome": "Outra Pessoa",
            "cargo": "vendedor",
        },
    )
    forbidden_revoke = client.post(
        revoke_match.group(1),
        data={"csrf": csrf},
    )

    assert forbidden_assign.status_code == 403
    assert forbidden_revoke.status_code == 403
    assert "permissão" in forbidden_assign.text
    assert "permissão" in forbidden_revoke.text


def test_revogar_ultimo_dono_de_loja_pronta_retorna_erro_no_detalhe(
    client,
    monkeypatch,
):
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Pronta UI", slug="loja-pronta-cargos-ui"),
    )
    _enable_control_ui(monkeypatch)
    _login(client, "trafego@revy.local", "secret-teste")
    detail_url = f"/app/control/lojas/{store.id}"
    detail = client.get(detail_url)
    assigned = client.post(
        f"{detail_url}/cargos",
        data={
            "csrf": csrf_da_resposta(detail),
            "email": "ultimo.dono.ui@example.com",
            "nome": "Último Dono UI",
            "cargo": "dono",
        },
        follow_redirects=False,
    )
    assigned_page = client.get(assigned.headers["location"])
    revoke_match = re.search(
        rf'action="([^"]*/app/control/lojas/{store.id}/cargos/[^"]+/revogar)"',
        assigned_page.text,
    )
    assert revoke_match is not None
    now = agora()
    with SessionLocal() as db:
        person = (
            db.query(Pessoa)
            .filter(Pessoa.email == "ultimo.dono.ui@example.com")
            .one()
        )
        db.add(
            AcessoControl(
                pessoa_id=person.id,
                papel="gestor",
                estado="pendente",
                senha_hash=None,
                sessao_versao=1,
                gestor_legado_id=None,
                criada_em=now,
                atualizada_em=now,
            )
        )
        db.commit()
    configuring = client.post(
        f"{detail_url}/estado",
        data={
            "csrf": csrf_da_resposta(assigned_page),
            "estado": "em_configuracao",
        },
        follow_redirects=False,
    )
    configuring_page = client.get(configuring.headers["location"])
    ready = client.post(
        f"{detail_url}/estado",
        data={
            "csrf": csrf_da_resposta(configuring_page),
            "estado": "pronta",
        },
        follow_redirects=False,
    )
    assert ready.status_code == 303
    ready_page = client.get(ready.headers["location"])

    blocked = client.post(
        revoke_match.group(1),
        data={"csrf": csrf_da_resposta(ready_page)},
    )

    assert blocked.status_code == 409
    assert "Loja precisa manter ao menos um Dono ativo neste estado" in blocked.text
    assert "Último Dono UI" in blocked.text
