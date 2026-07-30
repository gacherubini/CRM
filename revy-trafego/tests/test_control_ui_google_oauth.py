"""Parte B: operação Google Ads no detalhe da Loja.

Cobre callback HTML, conexão, contas, vínculos de conversão, métricas, flags,
CSRF e autorização no seam HTTP. A regra "Admin Revy ou Gestor Responsável"
continua no domínio (`_assert_can_manage_connection`).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from starlette.requests import Request

from app.auth import hash_senha
from app.config import settings
from app.control.google_ads import (
    GOOGLE_ADS_SCOPES,
    FakeGoogleAdsTokenExchanger,
    FakeGoogleAdsReadPort,
    GoogleAdsAccount,
    GoogleAdsConnectionControl,
    GoogleAdsConversionAction,
    GoogleAdsMetricRow,
    OAuthTokenBundle,
)
from app.control.google_ads_conversions import GoogleAdsConversionsControl
from app.control.google_ads_metrics import GoogleAdsMetricsControl
from app.control.session import actor_from_user
from app.control.stores import StoreControl
from app.control.types import AccessDenied, Actor, CreateStore, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, VinculoTrafego
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod
from tests.conftest import csrf_da_resposta

CALLBACK_PATH = control_ui_mod.GOOGLE_ADS_OAUTH_CALLBACK_PATH
REFRESH_TOKEN_SECRETO = "rt-nunca-renderizado"
REDIRECT_URI = f"https://control.revy.test{CALLBACK_PATH}"


def _enable(
    monkeypatch,
    *,
    control: bool = True,
    google: bool = True,
    configured: bool = True,
    conversions: bool = False,
) -> None:
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=control,
            google_ads_sync_enabled=google,
            google_conversions_enabled=conversions,
            google_ads_oauth_client_id="ui-client-id" if configured else "",
            google_ads_oauth_client_secret="ui-client-secret" if configured else "",
            google_ads_oauth_redirect_uri=REDIRECT_URI if configured else "",
            google_ads_developer_token="ui-developer-token" if configured else "",
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


# --- painéis e ações Google Ads no detalhe da Loja ---


def test_detalhe_mostra_google_nao_configurado_sem_botao_que_falha(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-nao-configurado")
    _enable(monkeypatch, configured=False)
    _login(client)

    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert detalhe.status_code == 200
    assert 'id="google-ads-operacao"' in detalhe.text
    assert "Google não configurado neste ambiente" in detalhe.text
    assert 'id="form-google-oauth-start"' not in detalhe.text


def test_admin_inicia_oauth_pelo_detalhe_e_vai_para_o_google(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-iniciar")
    control = _domain_control()
    _enable(monkeypatch)
    monkeypatch.setattr(control_mod, "_google_ads_control", lambda: control)
    _login(client)
    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert detalhe.status_code == 200
    assert 'id="google-conexao"' in detalhe.text
    assert 'id="google-proximo-passo-conexao"' in detalhe.text
    assert 'id="form-google-oauth-start"' in detalhe.text

    iniciado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/oauth/start",
        data={"csrf": csrf_da_resposta(detalhe)},
        follow_redirects=False,
    )

    assert iniciado.status_code == 303
    assert iniciado.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )
    assert "refresh_token" not in iniciado.text


def test_admin_desconecta_google_sem_expor_refresh_token(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-desconectar")
    control = _domain_control()
    inicio = control.start_oauth(_admin_actor(), StoreRef(id=loja_id))
    control.complete_oauth(state=inicio.state, code="code-ok")
    _enable(monkeypatch)
    monkeypatch.setattr(control_mod, "_google_ads_control", lambda: control)
    _login(client)
    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert detalhe.status_code == 200
    assert 'id="form-google-desconectar"' in detalhe.text
    assert "Credencial disponível:" in detalhe.text
    assert REFRESH_TOKEN_SECRETO not in detalhe.text

    desconectado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/desconectar",
        data={"csrf": csrf_da_resposta(detalhe)},
        follow_redirects=False,
    )

    assert desconectado.status_code == 303
    assert desconectado.headers["location"].endswith(
        f"/app/control/lojas/{loja_id}?ok=google_desconectado"
    )
    conexao = control.get(_admin_actor(), StoreRef(id=loja_id))
    assert conexao.has_refresh_token is False
    assert REFRESH_TOKEN_SECRETO not in desconectado.text


def test_admin_sincroniza_contas_ve_mcc_desabilitada_e_seleciona_anunciante(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-contas")
    connection_control = _domain_control()
    inicio = connection_control.start_oauth(_admin_actor(), StoreRef(id=loja_id))
    connection_control.complete_oauth(state=inicio.state, code="code-ok")
    metrics_control = GoogleAdsMetricsControl(
        SessionLocal,
        read_port=FakeGoogleAdsReadPort(
            accounts=[
                GoogleAdsAccount(
                    customer_id="1112223333",
                    descriptive_name="Conta da Loja",
                    is_manager=False,
                    currency_code="BRL",
                    time_zone="America/Sao_Paulo",
                    login_customer_id="5556667777",
                ),
                GoogleAdsAccount(
                    customer_id="5556667777",
                    descriptive_name="Gestora MCC",
                    is_manager=True,
                    currency_code="BRL",
                ),
            ]
        ),
    )
    _enable(monkeypatch)
    monkeypatch.setattr(
        control_mod,
        "_google_ads_control",
        lambda: connection_control,
    )
    monkeypatch.setattr(
        control_mod,
        "_google_ads_metrics_control",
        lambda: metrics_control,
    )
    _login(client)
    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert 'id="google-conta"' in detalhe.text
    assert 'id="google-proximo-passo-conta"' in detalhe.text
    sincronizado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/accounts/sync",
        data={"csrf": csrf_da_resposta(detalhe)},
        follow_redirects=False,
    )
    assert sincronizado.status_code == 303

    contas = client.get(sincronizado.headers["location"])
    assert "Conta da Loja" in contas.text
    assert "Gestora MCC" in contas.text
    assert 'id="google-conta-5556667777"' in contas.text
    html_normalizado = " ".join(contas.text.split())
    assert 'id="google-conta-5556667777" disabled' in html_normalizado
    assert "Conta gerenciadora (MCC) não pode ser selecionada" in contas.text

    selecionada = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/accounts/select",
        data={
            "csrf": csrf_da_resposta(contas),
            "customer_id": "1112223333",
        },
        follow_redirects=False,
    )
    assert selecionada.status_code == 303
    assert selecionada.headers["location"].endswith(
        f"/app/control/lojas/{loja_id}?ok=google_conta_selecionada"
    )
    items = metrics_control.list_accounts(
        _admin_actor(),
        StoreRef(id=loja_id),
    )
    assert [item.customer_id for item in items if item.selected] == ["1112223333"]


def test_admin_vincula_evento_revy_a_conversion_action_listada(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-conversoes-ui")
    connection_control = _domain_control()
    inicio = connection_control.start_oauth(_admin_actor(), StoreRef(id=loja_id))
    connection_control.complete_oauth(state=inicio.state, code="code-ok")
    metrics_control = GoogleAdsMetricsControl(
        SessionLocal,
        read_port=FakeGoogleAdsReadPort(
            accounts=[
                GoogleAdsAccount(
                    customer_id="1112223333",
                    descriptive_name="Conta da Loja",
                    is_manager=False,
                    currency_code="BRL",
                )
            ],
            conversion_actions=[
                GoogleAdsConversionAction(
                    resource_name=(
                        "customers/1112223333/conversionActions/42"
                    ),
                    id="42",
                    name="Compra confirmada",
                    type="UPLOAD_CLICKS",
                    status="ENABLED",
                    category="PURCHASE",
                    primary_for_goal=True,
                )
            ],
        ),
    )
    metrics_control.sync_accounts(_admin_actor(), StoreRef(id=loja_id))
    metrics_control.select_account(
        _admin_actor(),
        StoreRef(id=loja_id),
        "1112223333",
    )
    conversions_control = GoogleAdsConversionsControl(SessionLocal)
    _enable(monkeypatch, conversions=True)
    monkeypatch.setattr(
        control_mod,
        "_google_ads_control",
        lambda: connection_control,
    )
    monkeypatch.setattr(
        control_mod,
        "_google_ads_metrics_control",
        lambda: metrics_control,
    )
    monkeypatch.setattr(
        control_mod,
        "_google_ads_conversions_control",
        lambda: conversions_control,
    )
    _login(client)
    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert 'id="google-conversoes"' in detalhe.text
    assert 'name="conversion_action_resource_name"' in detalhe.text
    assert "<select" in detalhe.text
    assert "Compra confirmada" in detalhe.text
    assert (
        'type="text" name="conversion_action_resource_name"'
        not in detalhe.text
    )

    vinculado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/conversion-bindings",
        data={
            "csrf": csrf_da_resposta(detalhe),
            "revy_event_type": "venda_confirmada",
            "conversion_action_resource_name": (
                "customers/1112223333/conversionActions/42"
            ),
            "customer_id": "1112223333",
        },
        follow_redirects=False,
    )

    assert vinculado.status_code == 303
    assert vinculado.headers["location"].endswith(
        f"/app/control/lojas/{loja_id}?ok=google_conversao_vinculada"
    )
    bindings = conversions_control.list_bindings(
        _admin_actor(),
        StoreRef(id=loja_id),
    )
    assert [
        (item.revy_event_type, item.conversion_action_resource_name)
        for item in bindings
    ] == [
        ("venda_confirmada", "customers/1112223333/conversionActions/42"),
    ]


def test_admin_sincroniza_metricas_e_ve_resumo_de_sete_dias(
    client,
    monkeypatch,
):
    loja_id = _create_store(slug="loja-google-metricas-ui")
    connection_control = _domain_control()
    inicio = connection_control.start_oauth(_admin_actor(), StoreRef(id=loja_id))
    connection_control.complete_oauth(state=inicio.state, code="code-ok")
    metrics_control = GoogleAdsMetricsControl(
        SessionLocal,
        read_port=FakeGoogleAdsReadPort(
            accounts=[
                GoogleAdsAccount(
                    customer_id="1112223333",
                    descriptive_name="Conta Métricas",
                    is_manager=False,
                    currency_code="BRL",
                )
            ],
            metrics=[
                GoogleAdsMetricRow(
                    customer_id="1112223333",
                    campaign_id="campanha-1",
                    date="2026-07-29",
                    impressions=1000,
                    clicks=50,
                    cost_micros=25_000_000,
                    conversions=2,
                    conversions_value=100,
                )
            ],
        ),
    )
    metrics_control.sync_accounts(_admin_actor(), StoreRef(id=loja_id))
    metrics_control.select_account(
        _admin_actor(),
        StoreRef(id=loja_id),
        "1112223333",
    )

    class DataFixa(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 30)

    _enable(monkeypatch)
    monkeypatch.setattr(control_ui_mod, "date", DataFixa)
    monkeypatch.setattr(
        control_mod,
        "_google_ads_control",
        lambda: connection_control,
    )
    monkeypatch.setattr(
        control_mod,
        "_google_ads_metrics_control",
        lambda: metrics_control,
    )
    _login(client)
    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert 'id="google-metricas"' in detalhe.text
    assert 'name="date_from" value="2026-07-24"' in detalhe.text
    assert 'name="date_to" value="2026-07-30"' in detalhe.text

    sincronizado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/metrics/sync",
        data={
            "csrf": csrf_da_resposta(detalhe),
            "date_from": "2026-07-24",
            "date_to": "2026-07-30",
        },
        follow_redirects=False,
    )

    assert sincronizado.status_code == 303
    resumo = client.get(sincronizado.headers["location"])
    assert "1.000 impressões" in resumo.text
    assert "50 cliques" in resumo.text
    assert "R$ 25,00" in resumo.text
    assert "2 conversões" in resumo.text
    assert "ROAS 4.00" in resumo.text


def test_paineis_google_ficam_ocultos_com_flag_off(client, monkeypatch):
    loja_id = _create_store(slug="loja-google-flag-off")
    _enable(monkeypatch, google=False)
    _login(client)

    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    assert detalhe.status_code == 200
    assert 'id="google-ads-operacao"' not in detalhe.text


def test_inicio_oauth_nega_csrf_invalido(client, monkeypatch):
    loja_id = _create_store(slug="loja-google-csrf")
    _enable(monkeypatch)
    _login(client)

    negado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/oauth/start",
        data={"csrf": "token-invalido"},
        follow_redirects=False,
    )

    assert negado.status_code == 403
    assert "CSRF" in negado.text


def test_gestor_responsavel_inicia_oauth_pela_tela(client, monkeypatch):
    loja_id = _create_store(slug="loja-google-responsavel-ui")
    responsavel_id = _gestor(
        "responsavel.tela.google@revy.local",
        "Responsável Google UI",
        "senha-responsavel-ui",
    )
    _vincular(loja_id, responsavel_id, "responsavel")
    control = _domain_control()
    _enable(monkeypatch)
    monkeypatch.setattr(control_mod, "_google_ads_control", lambda: control)
    _login(
        client,
        "responsavel.tela.google@revy.local",
        "senha-responsavel-ui",
    )
    detalhe = client.get(f"/app/control/lojas/{loja_id}")

    iniciado = client.post(
        f"/app/control/lojas/{loja_id}/google-ads/oauth/start",
        data={"csrf": csrf_da_resposta(detalhe)},
        follow_redirects=False,
    )

    assert iniciado.status_code == 303
    assert iniciado.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )


def test_gestor_colaborador_nao_muta_operacao_google(client, monkeypatch):
    loja_id = _create_store(slug="loja-google-colaborador-ui")
    colaborador_id = _gestor(
        "colaborador.tela.google@revy.local",
        "Colaborador Google UI",
        "senha-colaborador-ui",
    )
    _vincular(loja_id, colaborador_id, "colaborador")
    connection_control = _domain_control()
    inicio = connection_control.start_oauth(_admin_actor(), StoreRef(id=loja_id))
    connection_control.complete_oauth(state=inicio.state, code="code-ok")
    metrics_control = GoogleAdsMetricsControl(
        SessionLocal,
        read_port=FakeGoogleAdsReadPort(
            accounts=[
                GoogleAdsAccount(
                    customer_id="1112223333",
                    descriptive_name="Conta Protegida",
                    is_manager=False,
                    currency_code="BRL",
                )
            ],
            conversion_actions=[
                GoogleAdsConversionAction(
                    resource_name=(
                        "customers/1112223333/conversionActions/7"
                    ),
                    id="7",
                    name="Venda",
                    status="ENABLED",
                )
            ],
        ),
    )
    metrics_control.sync_accounts(_admin_actor(), StoreRef(id=loja_id))
    metrics_control.select_account(
        _admin_actor(),
        StoreRef(id=loja_id),
        "1112223333",
    )
    conversions_control = GoogleAdsConversionsControl(SessionLocal)
    _enable(monkeypatch, conversions=True)
    monkeypatch.setattr(
        control_mod,
        "_google_ads_control",
        lambda: connection_control,
    )
    monkeypatch.setattr(
        control_mod,
        "_google_ads_metrics_control",
        lambda: metrics_control,
    )
    monkeypatch.setattr(
        control_mod,
        "_google_ads_conversions_control",
        lambda: conversions_control,
    )
    _login(
        client,
        "colaborador.tela.google@revy.local",
        "senha-colaborador-ui",
    )
    detalhe = client.get(f"/app/control/lojas/{loja_id}")
    csrf = csrf_da_resposta(detalhe)
    requests = (
        (
            f"/app/control/lojas/{loja_id}/google-ads/oauth/start",
            {"csrf": csrf},
        ),
        (
            f"/app/control/lojas/{loja_id}/google-ads/desconectar",
            {"csrf": csrf},
        ),
        (
            f"/app/control/lojas/{loja_id}/google-ads/accounts/sync",
            {"csrf": csrf},
        ),
        (
            f"/app/control/lojas/{loja_id}/google-ads/accounts/select",
            {"csrf": csrf, "customer_id": "1112223333"},
        ),
        (
            f"/app/control/lojas/{loja_id}/google-ads/conversion-bindings",
            {
                "csrf": csrf,
                "revy_event_type": "venda_confirmada",
                "conversion_action_resource_name": (
                    "customers/1112223333/conversionActions/7"
                ),
                "customer_id": "1112223333",
            },
        ),
        (
            f"/app/control/lojas/{loja_id}/google-ads/metrics/sync",
            {
                "csrf": csrf,
                "date_from": "2026-07-24",
                "date_to": "2026-07-30",
            },
        ),
    )

    for path, data in requests:
        response = client.post(path, data=data, follow_redirects=False)
        assert response.status_code == 403, path
        assert "Acesso negado" in response.text
