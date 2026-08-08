"""Fase 5 — Equipe read-only + acessos bancários sob shell Revy Loja."""
from __future__ import annotations

from conftest import csrf_da_resposta, login

from app.config import settings
from app.db import SessionLocal
from app.loja.sales_overview import (
    build_sales_overview,
    pendencias_bancos_nao_configurados,
)
from app.auth import hash_senha
from app.models import Usuario


def _enable_shell(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)


def _disable_shell(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    object.__setattr__(settings, "revy_loja_shell_enabled", False)


def _criar_membro(
    *,
    email="vendedor@loja.test",
    nome="Vera Vendas",
    papel="vendedor",
    loja_slug="loja-teste",
    ativo=True,
):
    db = SessionLocal()
    membro = Usuario(
        email=email,
        nome=nome,
        senha_hash=hash_senha("senha-do-membro"),
        papel=papel,
        loja_slug=loja_slug,
        ativo=ativo,
    )
    db.add(membro)
    db.commit()
    membro_id = membro.id
    db.close()
    return membro_id


# ---------------------------------------------------------------------------
# Equipe com shell ON — dono gerencia; gerente só consulta
# ---------------------------------------------------------------------------


def test_shell_on_dono_pode_criar_usuario(client, monkeypatch):
    _enable_shell(monkeypatch)
    login(client)
    pagina = client.get("/app/equipe/novo")
    assert pagina.status_code == 200
    csrf = csrf_da_resposta(pagina)

    resposta = client.post(
        "/app/equipe/novo",
        data={
            "csrf": csrf,
            "nome": "Bruno Comercial",
            "email": "bruno@loja.test",
            "papel": "vendedor",
            "senha": "senha-inicial-forte",
            "senha_confirmacao": "senha-inicial-forte",
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert "ok=criado" in resposta.headers["location"]
    db = SessionLocal()
    assert db.query(Usuario).filter(Usuario.email == "bruno@loja.test").count() == 1
    db.close()


def test_shell_on_dono_pode_alterar_cargo(client, monkeypatch):
    _enable_shell(monkeypatch)
    membro_id = _criar_membro()
    login(client)
    pagina = client.get(f"/app/equipe/{membro_id}/editar")
    assert pagina.status_code == 200
    csrf = csrf_da_resposta(pagina)

    resposta = client.post(
        f"/app/equipe/{membro_id}/editar",
        data={
            "csrf": csrf,
            "nome": "Vera Gerente",
            "papel": "gerente",
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    db = SessionLocal()
    membro = db.get(Usuario, membro_id)
    assert membro.papel == "gerente"
    assert membro.nome == "Vera Gerente"
    db.close()


def test_shell_on_dono_pode_redefinir_senha_e_desativar(client, monkeypatch):
    _enable_shell(monkeypatch)
    membro_id = _criar_membro()
    login(client)
    csrf = csrf_da_resposta(client.get(f"/app/equipe/{membro_id}/senha"))

    senha = client.post(
        f"/app/equipe/{membro_id}/senha",
        data={
            "csrf": csrf,
            "senha": "nova-senha-super-segura",
            "senha_confirmacao": "nova-senha-super-segura",
        },
        follow_redirects=False,
    )
    csrf2 = csrf_da_resposta(client.get("/app/equipe"))
    desativar = client.post(
        f"/app/equipe/{membro_id}/desativar",
        data={"csrf": csrf2},
        follow_redirects=False,
    )

    assert senha.status_code == 303
    assert desativar.status_code == 303
    db = SessionLocal()
    assert db.get(Usuario, membro_id).ativo is False
    db.close()


def test_shell_on_forms_estruturais_abrem_para_dono(client, monkeypatch):
    _enable_shell(monkeypatch)
    membro_id = _criar_membro()
    login(client)

    for path in (
        "/app/equipe/novo",
        f"/app/equipe/{membro_id}/editar",
        f"/app/equipe/{membro_id}/senha",
    ):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 200, path


def test_shell_on_lista_equipe_funciona_para_dono(client, monkeypatch):
    _enable_shell(monkeypatch)
    _criar_membro()
    login(client)

    resposta = client.get("/app/equipe")
    assert resposta.status_code == 200
    assert "Vera Vendas" in resposta.text
    assert "Vendedor" in resposta.text or "vendedor" in resposta.text
    assert "Ativo" in resposta.text
    assert "Adicionar membro" in resposta.text
    assert "/app/equipe/novo" in resposta.text
    assert "Contas e cargos são geridos no Revy Control" not in resposta.text


def test_shell_on_lista_equipe_funciona_para_gerente(client, monkeypatch):
    _enable_shell(monkeypatch)
    _criar_membro()
    login(client, papel="gerente", email="gerente@loja.test")

    resposta = client.get("/app/equipe")
    assert resposta.status_code == 200
    assert "Vera Vendas" in resposta.text
    # Gerente consulta; não cria contas
    assert "Adicionar membro" not in resposta.text


def test_shell_on_rota_loja_equipe_dono_pode_adicionar(client, monkeypatch):
    _enable_shell(monkeypatch)
    _criar_membro(nome="Carla Contato", email="carla@loja.test")
    login(client)

    resposta = client.get("/app/loja/equipe")
    assert resposta.status_code == 200
    assert "Carla Contato" in resposta.text
    assert "Adicionar membro" in resposta.text
    # O que nao pode vazar e o token de convite, no corpo da pagina. O <head>
    # carrega revy-tokens.css, cujo NOME contem "token" e nao e segredo.
    corpo = resposta.text.split("<body", 1)[-1].lower()
    assert "token" not in corpo


def test_shell_off_rota_loja_equipe_404(client, monkeypatch):
    _disable_shell(monkeypatch)
    login(client)
    resposta = client.get("/app/loja/equipe")
    assert resposta.status_code == 404


def test_shell_off_dono_ainda_pode_criar_equipe(client, monkeypatch):
    """Legado offline: mutações estruturais permanecem com shell desligado."""
    _disable_shell(monkeypatch)
    login(client)
    pagina = client.get("/app/equipe/novo")
    assert pagina.status_code == 200

    resposta = client.post(
        "/app/equipe/novo",
        data={
            "csrf": csrf_da_resposta(pagina),
            "nome": "Bruno Comercial",
            "email": "bruno@loja.test",
            "papel": "vendedor",
            "senha": "senha-inicial-forte",
            "senha_confirmacao": "senha-inicial-forte",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "ok=criado" in resposta.headers["location"]


# ---------------------------------------------------------------------------
# Acessos bancários
# ---------------------------------------------------------------------------


def test_alias_configuracoes_financeiras_redireciona(client, monkeypatch, motor_fake):
    _enable_shell(monkeypatch)
    login(client)
    resposta = client.get(
        "/app/loja/vendas/configuracoes-financeiras",
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/financeiras"


def test_alias_configuracoes_financeiras_404_shell_off(client, monkeypatch):
    _disable_shell(monkeypatch)
    login(client)
    resposta = client.get("/app/loja/vendas/configuracoes-financeiras")
    assert resposta.status_code == 404


def test_vendedor_nao_acessa_financeiras_com_shell(client, monkeypatch, motor_fake):
    _enable_shell(monkeypatch)
    login(client, papel="vendedor")
    resposta = client.get("/app/financeiras")
    assert resposta.status_code == 403
    assert "SENHA-SECRETA" not in resposta.text


def test_upsert_nao_reexibe_senha_no_html(client, monkeypatch, motor_fake):
    _enable_shell(monkeypatch)
    login(client)
    pagina = client.get("/app/financeiras")
    csrf = csrf_da_resposta(pagina)
    senha = "senha-super-secreta-xyz-999"
    resposta = client.post(
        "/app/financeiras/Pan",
        data={"csrf": csrf, "usuario": "loja-nova", "senha": senha},
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    assert senha not in resposta.text
    assert "SENHA-SECRETA" not in resposta.text


def test_pendencia_bancos_nao_configurados_helper():
    itens = pendencias_bancos_nao_configurados(["Santander", "FonteCred"])
    assert len(itens) == 1
    assert itens[0].codigo == "bancos_nao_configurados"
    assert "Santander" in itens[0].texto
    assert itens[0].href == "/app/financeiras"
    assert pendencias_bancos_nao_configurados([]) == []
    assert pendencias_bancos_nao_configurados(None) == []


def test_sales_overview_inclui_pendencia_banco(client, monkeypatch):
    _enable_shell(monkeypatch)
    db = SessionLocal()
    overview = build_sales_overview(
        db,
        loja_slug="loja-teste",
        papel="dono",
        bancos_nao_configurados=["Santander"],
    )
    db.close()
    codigos = [p.codigo for p in overview.pendencias]
    assert "bancos_nao_configurados" in codigos
