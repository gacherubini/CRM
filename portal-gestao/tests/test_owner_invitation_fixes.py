"""Correções dos bloqueadores do PR-4 (dono multi-loja).

Cobre o que faltava: e-mail com o slug convidado, ativação promovendo o vínculo,
memberships do Control sem apagar a loja legada, e o gate por flag no shell.
"""
from types import SimpleNamespace

from app.auth import hash_senha
from app.db import SessionLocal
from app.loja import identity
from app.loja.types import StoreMembership
from app.models import PessoaRevyProjetada, Usuario, VinculoLojaPessoa, agora
from app.owner_invitations import activate_owner_invitation, issue_owner_invitation
from app.web import loja_shell


def _seed_dono(db, email, loja_slug, *, ativo=True):
    user = Usuario(
        email=email,
        nome="Dono",
        senha_hash=hash_senha("x" * 20),
        papel="dono",
        loja_slug=loja_slug,
        ativo=ativo,
    )
    db.add(user)
    db.flush()
    db.add(PessoaRevyProjetada(id=user.id, email=email, nome="Dono"))
    db.flush()
    return user


# --- Fix 4: o e-mail/retorno usa a loja convidada, não a primeira (legada) ---
def test_convite_para_segunda_loja_retorna_o_slug_convidado():
    with SessionLocal() as db:
        issue_owner_invitation(db, email="dono@x.com", name="Dono", store_slug="loja-a")
        invitation = issue_owner_invitation(
            db, email="dono@x.com", name="Dono", store_slug="loja-b"
        )
        assert invitation.store_slug == "loja-b"


# --- Fix 3: ativar o convite promove o vínculo pendente para ativo ---
def test_ativacao_promove_vinculo_pendente_para_ativo():
    with SessionLocal() as db:
        invitation = issue_owner_invitation(
            db, email="dono@x.com", name="Dono", store_slug="loja-a"
        )
        activate_owner_invitation(
            db, token=invitation.token, password="senha-super-segura"
        )
        vinculo = (
            db.query(VinculoLojaPessoa)
            .filter(
                VinculoLojaPessoa.pessoa_id == invitation.user_id,
                VinculoLojaPessoa.loja_slug == "loja-a",
            )
            .one()
        )
        assert vinculo.state == "ativo"


# --- Fix 2: memberships do Control não apagam a loja legada (loja_slug) ---
def test_memberships_do_control_nao_apagam_a_loja_legada():
    usuario = SimpleNamespace(
        id="u1", email="dono@x.com", nome="Dono",
        loja_slug="loja-a", papel="dono", ativo=True,
    )
    memberships = [
        StoreMembership(loja_slug="loja-b", roles=frozenset({"dono"}), ativo=True)
    ]
    actor = identity.actor_from_usuario(usuario, memberships=memberships)
    assert set(identity.available_store_slugs(actor)) == {"loja-a", "loja-b"}


# --- Fix 5: o shell só consulta vinculo_loja_pessoa com a flag ligada ---
def test_shell_ignora_vinculo_quando_flag_off(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    with SessionLocal() as db:
        user = _seed_dono(db, "dono@x.com", "loja-a")
        db.add(
            VinculoLojaPessoa(
                pessoa_id=user.id, loja_slug="loja-b", cargo="dono",
                state="ativo", versao=0, atualizado_em=agora(),
            )
        )
        db.commit()
        request = SimpleNamespace(session={})
        _store, _ents, actor = loja_shell.resolve_store_and_entitlements(
            request, user, db
        )
        assert set(identity.available_store_slugs(actor)) == {"loja-a"}


def test_shell_une_vinculo_ativo_quando_flag_on(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    with SessionLocal() as db:
        user = _seed_dono(db, "dono@x.com", "loja-a")
        db.add(
            VinculoLojaPessoa(
                pessoa_id=user.id, loja_slug="loja-b", cargo="dono",
                state="ativo", versao=0, atualizado_em=agora(),
            )
        )
        db.commit()
        request = SimpleNamespace(session={})
        _store, _ents, actor = loja_shell.resolve_store_and_entitlements(
            request, user, db
        )
        assert set(identity.available_store_slugs(actor)) == {"loja-a", "loja-b"}
