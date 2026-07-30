"""Parte B (fundação): callback OAuth Google em HTML + seam de autorização.

Cobre a rota HTML `/app/control/google-ads/oauth/callback` (o `redirect_uri`
que um humano alcança) e `_actor_for_store_mutation`, o gate que os painéis
Google vão consumir. A regra "Admin Revy ou Gestor Responsável" continua no
domínio (`_assert_can_manage_connection`), então aqui ela é exercida via
composição: gate da UI + chamada de domínio.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from starlette.requests import Request

from app.auth import hash_senha
from app.config import settings
from app.control.google_ads import (
    GOOGLE_ADS_SCOPES,
    FakeGoogleAdsTokenExchanger,
    GoogleAdsConnectionControl,
    OAuthTokenBundle,
)
from app.control.session import actor_from_user
from app.control.stores import StoreControl
from app.control.types import AccessDenied, Actor, CreateStore, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, VinculoTrafego
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod

CALLBACK_PATH = control_ui_mod.GOOGLE_ADS_OAUTH_CALLBACK_PATH
REFRESH_TOKEN_SECRETO = "rt-nunca-renderizado"
REDIRECT_URI = f"https://control.revy.test{CALLBACK_PATH}"


def _enable(
    monkeypatch,
    *,
    control: bool = True,
    google: bool = True,
    configured: bool = True,
) -> None:
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=control,
            google_ads_sync_enabled=google,
            google_ads_oauth_client_id="ui-client-id" if configured else "",
            google_ads_oauth_client_secret="ui-client-secret" if configured else "",
            google_ads_oauth_redirect_uri=REDIRECT_URI if configured else "",
        ),
    )


def _login(client, email: str = "trafego@revy.local", senha: str = "secret-teste") -> None:
    response = client.post(
        "/login",
        data={"email": email, "senha": senha},
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


def _create_store(slug: str = "loja-google-ui", nome: str = "Loja Google UI") -> str:
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name=nome, slug=slug),
    )
    return store.id


def _gestor(email: str, nome: str, senha: str) -> str:
    with SessionLocal() as db:
        manager = GestorRevy(
            email=email,
            nome=nome,
            senha_hash=hash_senha(senha),
            papel="gestor",
            ativo=True,
        )
        db.add(manager)
        db.commit()
        return manager.id


def _vincular(loja_id: str, gestor_id: str, tipo: str) -> None:
    with SessionLocal() as db:
        db.add(
            VinculoTrafego(loja_id=loja_id, gestor_id=gestor_id, tipo=tipo)
        )
        db.commit()


def _domain_control(
    *,
    exchanger: FakeGoogleAdsTokenExchanger | None = None,
) -> GoogleAdsConnectionControl:
    return GoogleAdsConnectionControl(
        SessionLocal,
        client_id="ui-client-id",
        client_secret="ui-client-secret",
        redirect_uri=REDIRECT_URI,
        token_exchanger=exchanger
        or FakeGoogleAdsTokenExchanger(
            default_bundle=OAuthTokenBundle(
                refresh_token=REFRESH_TOKEN_SECRETO,
                access_token="at-valor",
                scopes=GOOGLE_ADS_SCOPES,
            )
        ),
    )


def _start_state(loja_id: str, actor: Actor | None = None) -> str:
    return _domain_control().start_oauth(
        actor or _admin_actor(),
        StoreRef(id=loja_id),
    ).state


def _request_com_sessao(sessao: dict) -> Request:
    """Request mínimo: `gestor_atual` só precisa de `scope["session"]`."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": CALLBACK_PATH,
            "root_path": "",
            "headers": [],
            "query_string": b"",
            "session": sessao,
        }
    )


# --- callback HTML ---


def test_callback_html_conecta_e_redireciona_para_o_detalhe_da_loja(
    client,
    monkeypatch,
):
    loja_id = _create_store()
    state = _start_state(loja_id)
    _enable(monkeypatch)
    _login(client)

    response = client.get(
        CALLBACK_PATH,
        params={"state": state, "code": "authorization-code-ok"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/app/control/lojas/{loja_id}?ok=google_conectado"
    )
    assert "refresh_token" not in response.text
    # Ports vêm de build_google_ads_ports sem credenciais (fake exchanger).
    assert "fake-refresh-token" not in response.text

    conexao = _domain_control().get(_admin_actor(), StoreRef(id=loja_id))
    assert conexao.loja_id == loja_id
    assert conexao.has_refresh_token is True

    detalhe = client.get(response.headers["location"])
    assert detalhe.status_code == 200
    assert "fake-refresh-token" not in detalhe.text
    assert REFRESH_TOKEN_SECRETO not in detalhe.text


def test_callback_html_nunca_renderiza_o_refresh_token_da_troca(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-token")
    state = _start_state(loja_id)
    _enable(monkeypatch)
    monkeypatch.setattr(control_mod, "_google_ads_control", _domain_control)
    _login(client)

    response = client.get(
        CALLBACK_PATH,
        params={"state": state, "code": "authorization-code-ok"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert REFRESH_TOKEN_SECRETO not in response.text
    for historico in response.history:
        assert REFRESH_TOKEN_SECRETO not in historico.text


def test_callback_html_com_state_invalido_mostra_erro_e_nao_500(
    client,
    monkeypatch,
):
    _create_store(slug="loja-google-state")
    _enable(monkeypatch)
    _login(client)

    response = client.get(
        CALLBACK_PATH,
        params={"state": "state-que-nao-existe", "code": "qualquer"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Conexão com o Google Ads não concluída" in response.text
    assert "expirado ou já utilizado" in response.text
    assert "/app/control/lojas" in response.text


def test_callback_html_com_falha_na_troca_mostra_banner_no_detalhe(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-falha")
    state = _start_state(loja_id)
    _enable(monkeypatch)
    quebrado = _domain_control(exchanger=FakeGoogleAdsTokenExchanger())
    monkeypatch.setattr(control_mod, "_google_ads_control", lambda: quebrado)
    _login(client)

    response = client.get(
        CALLBACK_PATH,
        params={"state": state, "code": "code-que-falha"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "O Google não confirmou a autorização" in response.text
    assert "Loja Google UI" in response.text  # banner no detalhe da Loja
    assert REFRESH_TOKEN_SECRETO not in response.text


def test_callback_html_sem_client_oauth_configurado_nao_estoura(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-sem-config")
    state = _start_state(loja_id)
    _enable(monkeypatch, configured=False)
    _login(client)

    response = client.get(
        CALLBACK_PATH,
        params={"state": state, "code": "qualquer"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Google Ads não está configurado neste ambiente." in response.text


def test_callback_html_respeita_flags_e_exige_sessao(client, monkeypatch):
    loja_id = _create_store(slug="loja-google-flags")
    state = _start_state(loja_id)
    params = {"state": state, "code": "qualquer"}

    sem_flags = client.get(CALLBACK_PATH, params=params, follow_redirects=False)
    assert sem_flags.status_code == 404

    _enable(monkeypatch, control=True, google=False)
    google_off = client.get(CALLBACK_PATH, params=params, follow_redirects=False)
    assert google_off.status_code == 404

    _enable(monkeypatch, control=False, google=True)
    control_off = client.get(CALLBACK_PATH, params=params, follow_redirects=False)
    assert control_off.status_code == 404

    _enable(monkeypatch)
    sem_sessao = client.get(CALLBACK_PATH, params=params, follow_redirects=False)
    assert sem_sessao.status_code == 303
    assert sem_sessao.headers["location"].endswith("/login")


# --- seam de autorização (_actor_for_store_mutation) ---


def test_seam_autoriza_admin_e_gestor_responsavel_e_dominio_bloqueia_colaborador(
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-seam")
    responsavel_id = _gestor(
        "responsavel.google@revy.local",
        "Gestor Responsável",
        "senha-responsavel",
    )
    colaborador_id = _gestor(
        "colaborador.google@revy.local",
        "Gestor Colaborador",
        "senha-colaborador",
    )
    _vincular(loja_id, responsavel_id, "responsavel")
    _vincular(loja_id, colaborador_id, "colaborador")
    _enable(monkeypatch)
    control = _domain_control()
    store = StoreRef(id=loja_id)

    with SessionLocal() as db:
        for gestor_id in (_admin_actor().id, responsavel_id):
            manager, denied = control_ui_mod._actor_for_store_mutation(
                _request_com_sessao({"gestor_id": gestor_id}),
                db,
            )
            assert denied is None
            resultado = control.start_oauth(actor_from_user(manager), store)
            assert "accounts.google.com" in resultado.auth_url

        manager, denied = control_ui_mod._actor_for_store_mutation(
            _request_com_sessao({"gestor_id": colaborador_id}),
            db,
        )
        # O gate deixa passar; a recusa é do domínio, num lugar só.
        assert denied is None
        with pytest.raises(AccessDenied):
            control.start_oauth(actor_from_user(manager), store)

    negado = control_ui_mod._access_denied()
    assert negado.status_code == 403
    assert "Acesso negado" in negado.body.decode()


def test_admin_for_mutation_continua_bloqueando_gestor_responsavel(monkeypatch):
    loja_id = _create_store(slug="loja-google-admin-gate")
    responsavel_id = _gestor(
        "responsavel.gate@revy.local",
        "Gestor Responsável Gate",
        "senha-gate",
    )
    _vincular(loja_id, responsavel_id, "responsavel")
    _enable(monkeypatch)
    request = _request_com_sessao({"gestor_id": responsavel_id})

    with SessionLocal() as db:
        manager, denied = control_ui_mod._admin_for_mutation(request, db)
        assert manager is None
        assert denied is not None
        assert denied.status_code == 403

        permitido, sem_bloqueio = control_ui_mod._actor_for_store_mutation(
            request,
            db,
        )
        assert sem_bloqueio is None
        assert permitido.id == responsavel_id


def test_actor_for_store_mutation_respeita_flag_e_sessao(monkeypatch):
    gestor_id = _gestor(
        "gestor.seam@revy.local",
        "Gestor Seam",
        "senha-seam",
    )

    with SessionLocal() as db:
        _enable(monkeypatch, control=False)
        manager, denied = control_ui_mod._actor_for_store_mutation(
            _request_com_sessao({"gestor_id": gestor_id}),
            db,
        )
        assert manager is None
        assert denied.status_code == 404

        _enable(monkeypatch)
        sem_sessao, redirecionado = control_ui_mod._actor_for_store_mutation(
            _request_com_sessao({}),
            db,
        )
        assert sem_sessao is None
        assert redirecionado.status_code == 303
        assert redirecionado.headers["location"].endswith("/login")
