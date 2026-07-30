"""F8 — redirects graduais de rotas legadas (REVY_LOJA_REDIRECT_LEGACY)."""
from __future__ import annotations

from conftest import login

from app.loja.redirects import (
    LEGACY_ALWAYS,
    LEGACY_ATENDIMENTO,
    normalize_path,
    resolve_legacy_redirect,
    should_consider_request,
)


# ---------------------------------------------------------------------------
# Domínio puro
# ---------------------------------------------------------------------------


def test_resolve_off_quando_flags_desligadas():
    assert (
        resolve_legacy_redirect(
            "/app/leads",
            shell_enabled=False,
            redirect_enabled=True,
            atendimento_enabled=True,
        )
        is None
    )
    assert (
        resolve_legacy_redirect(
            "/app/leads",
            shell_enabled=True,
            redirect_enabled=False,
            atendimento_enabled=True,
        )
        is None
    )


def test_resolve_app_e_vendas_paths():
    dest = resolve_legacy_redirect(
        "/app",
        shell_enabled=True,
        redirect_enabled=True,
        atendimento_enabled=False,
    )
    assert dest == "/app/loja/vendas"
    for path in ("/app/funil", "/app/financeiro", "/app/relatorios"):
        assert (
            resolve_legacy_redirect(
                path,
                shell_enabled=True,
                redirect_enabled=True,
                atendimento_enabled=False,
            )
            == "/app/loja/vendas"
        )


def test_resolve_estoque_lista_only():
    assert (
        resolve_legacy_redirect(
            "/app/estoque",
            shell_enabled=True,
            redirect_enabled=True,
            atendimento_enabled=False,
        )
        == "/app/loja/estoque"
    )
    for path in ("/app/estoque/novo", "/app/estoque/v1", "/app/estoque/abc-def"):
        assert (
            resolve_legacy_redirect(
                path,
                shell_enabled=True,
                redirect_enabled=True,
                atendimento_enabled=False,
            )
            is None
        )


def test_resolve_atendimento_exige_flag():
    assert (
        resolve_legacy_redirect(
            "/app/leads",
            shell_enabled=True,
            redirect_enabled=True,
            atendimento_enabled=False,
        )
        is None
    )
    assert (
        resolve_legacy_redirect(
            "/app/leads",
            shell_enabled=True,
            redirect_enabled=True,
            atendimento_enabled=True,
        )
        == "/app/loja/atendimento"
    )
    assert (
        resolve_legacy_redirect(
            "/app/conversas",
            shell_enabled=True,
            redirect_enabled=True,
            atendimento_enabled=True,
        )
        == "/app/loja/atendimento"
    )
    # Detalhe não redireciona
    assert (
        resolve_legacy_redirect(
            "/app/leads/l1",
            shell_enabled=True,
            redirect_enabled=True,
            atendimento_enabled=True,
        )
        is None
    )


def test_resolve_nunca_intercepta_loja():
    for path in (
        "/app/loja/vendas",
        "/app/loja/atendimento",
        "/app/loja/estoque",
        "/app/loja/estoque/veiculos",
    ):
        assert (
            resolve_legacy_redirect(
                path,
                shell_enabled=True,
                redirect_enabled=True,
                atendimento_enabled=True,
            )
            is None
        )


def test_should_consider_request_filtra_metodo_e_accept():
    assert should_consider_request("GET", "text/html") is True
    assert should_consider_request("GET", "*/*") is True
    assert should_consider_request("GET", None) is True
    assert should_consider_request("POST", "text/html") is False
    assert should_consider_request("GET", "application/json") is False
    assert should_consider_request("GET", "text/csv") is False
    assert should_consider_request("GET", "text/html, application/json") is True


def test_normalize_path_trailing_slash():
    assert normalize_path("/app/leads/") == "/app/leads"
    assert normalize_path("/app") == "/app"
    assert normalize_path("/") == "/"


def test_mapas_cobrem_paths_documentados():
    assert set(LEGACY_ALWAYS) == {
        "/app",
        "/app/funil",
        "/app/financeiro",
        "/app/relatorios",
        "/app/estoque",
    }
    assert set(LEGACY_ATENDIMENTO) == {"/app/leads", "/app/conversas"}


# ---------------------------------------------------------------------------
# HTTP (middleware)
# ---------------------------------------------------------------------------


def test_redirect_flag_off_leads_200(client, monkeypatch, chatbot_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "0")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "1")
    login(client)
    r = client.get("/app/leads", follow_redirects=False)
    assert r.status_code == 200
    assert "location" not in {k.lower() for k in r.headers.keys()} or (
        r.headers.get("location") is None
    )


def test_redirect_on_leads_303_atendimento(client, monkeypatch, chatbot_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "1")
    login(client)
    r = client.get("/app/leads", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app/loja/atendimento"


def test_redirect_on_sem_atendimento_leads_200(client, monkeypatch, chatbot_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "0")
    login(client)
    r = client.get("/app/leads", follow_redirects=False)
    assert r.status_code == 200


def test_redirect_on_app_home_303_vendas(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    login(client)
    r = client.get("/app", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app/loja/vendas"


def test_redirect_on_estoque_lista_303(client, monkeypatch, estoque_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    login(client)
    r = client.get("/app/estoque", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app/loja/estoque"


def test_redirect_on_estoque_novo_nao_redireciona(client, monkeypatch, estoque_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    login(client)
    r = client.get("/app/estoque/novo", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers.get("location") in (None, "")


def test_redirect_on_estoque_id_crud_seguro(client, monkeypatch, estoque_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    login(client)
    r = client.get("/app/estoque/v1", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers.get("location") in (None, "")


def test_redirect_off_app_mantem_dashboard(client, monkeypatch, estoque_fake):
    """Shell on + redirect off: home legada (brand Revy Loja já injetada)."""
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "0")
    login(client)
    r = client.get("/app", follow_redirects=False)
    assert r.status_code == 200
    assert "Revy Loja" in r.text


def test_redirect_shell_off_ignora_flag_redirect(client, monkeypatch, chatbot_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "1")
    login(client)
    r = client.get("/app/leads", follow_redirects=False)
    assert r.status_code == 200


def test_redirect_funil_financeiro_relatorios(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    login(client)
    for path in ("/app/funil", "/app/financeiro", "/app/relatorios"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"] == "/app/loja/vendas", path


def test_redirect_conversas_303(client, monkeypatch, chatbot_fake):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_REDIRECT_LEGACY", "1")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "1")
    login(client)
    r = client.get("/app/conversas", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app/loja/atendimento"
