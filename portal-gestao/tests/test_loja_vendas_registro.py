"""Registro e confirmacao de venda DENTRO do shell Revy Loja.

Antes o vendedor so tinha o botao "Nova venda" do atendimento, caindo na tela
legada /app/vendas — fora do menu e sem volta. E confirmar era privilegio de
dono/gerente, entao a venda parava antes de disparar Control e Meta.
"""
from __future__ import annotations

from decimal import Decimal

from conftest import csrf_da_resposta, login

from app.config import settings
from app.db import SessionLocal
from app.models import Venda, agora


def _enable_shell(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)


def _criar_venda(
    *,
    status="registrada",
    vendedor_email="vendedor@loja.test",
    loja_slug="loja-teste",
    descricao="Honda Civic 2022",
):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email=vendedor_email,
        descricao=descricao,
        preco_venda=Decimal("100000.00"),
        status=status,
        confirmada_em=agora() if status == "confirmada" else None,
    )
    db.add(venda)
    db.commit()
    venda_id = venda.id
    db.close()
    return venda_id


def test_lista_de_vendas_existe_no_shell(client, monkeypatch):
    _enable_shell(monkeypatch)
    _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")

    pagina = client.get("/app/loja/vendas/lista")

    assert pagina.status_code == 200
    assert "Honda Civic 2022" in pagina.text


def test_vendedor_so_ve_as_proprias_vendas(client, monkeypatch):
    _enable_shell(monkeypatch)
    _criar_venda(vendedor_email="vendedor@loja.test", descricao="Civic do vendedor")
    _criar_venda(vendedor_email="outro@loja.test", descricao="Onix do colega")
    login(client, papel="vendedor", email="vendedor@loja.test")

    pagina = client.get("/app/loja/vendas/lista")

    assert "Civic do vendedor" in pagina.text
    assert "Onix do colega" not in pagina.text


def test_dono_ve_as_vendas_da_loja(client, monkeypatch):
    _enable_shell(monkeypatch)
    _criar_venda(vendedor_email="vendedor@loja.test", descricao="Civic do vendedor")
    login(client)

    pagina = client.get("/app/loja/vendas/lista")

    assert "Civic do vendedor" in pagina.text


def test_vendedor_confirma_venda_sem_sair_do_shell(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))

    resposta = client.post(
        f"/app/loja/vendas/{venda_id}/confirmar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/loja/vendas/lista?ok=confirmada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "confirmada"
    assert venda.confirmada_por == "vendedor@loja.test"
    db.close()


def test_confirmacao_no_shell_enfileira_evento_para_o_revy_trafego(
    client, monkeypatch
):
    """O ponto do PR: confirmar na Loja tem que disparar a cascata."""
    _enable_shell(monkeypatch)
    object.__setattr__(settings, "revy_trafego_venda_events_enabled", True)
    venda_id = _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))

    try:
        client.post(
            f"/app/loja/vendas/{venda_id}/confirmar",
            data={"csrf": csrf},
            follow_redirects=False,
        )
    finally:
        object.__setattr__(settings, "revy_trafego_venda_events_enabled", False)

    from app.models import RevyTrafegoEventOutbox

    db = SessionLocal()
    evento = (
        db.query(RevyTrafegoEventOutbox)
        .filter(RevyTrafegoEventOutbox.venda_id == venda_id)
        .one()
    )
    assert evento.event_type == "venda_confirmada"
    db.close()


def test_venda_de_outra_loja_nao_confirma_pelo_shell(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(loja_slug="outra-loja")
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))

    resposta = client.post(
        f"/app/loja/vendas/{venda_id}/confirmar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/loja/vendas/lista?erro=acao"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_registrar_venda_pela_loja_volta_para_o_shell(client, monkeypatch):
    """Sem origem=loja o vendedor era jogado na lista legada e se perdia."""
    _enable_shell(monkeypatch)
    login(client, papel="vendedor", email="vendedor@loja.test")
    pagina = client.get("/app/vendas/nova?origem=loja")

    resposta = client.post(
        "/app/vendas/nova?origem=loja",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Corolla 2023",
            "preco_venda": "120000",
        },
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/loja/vendas/lista?ok=registrada"


def test_vendedor_cancela_registro_errado_no_shell(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))

    resposta = client.post(
        f"/app/loja/vendas/{venda_id}/cancelar",
        data={"csrf": csrf, "motivo": "cliente desistiu"},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/loja/vendas/lista?ok=cancelada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "cancelada"
    assert venda.motivo_cancelamento == "cliente desistiu"
    db.close()


def test_cancelamento_no_shell_exige_motivo(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))

    resposta = client.post(
        f"/app/loja/vendas/{venda_id}/cancelar",
        data={"csrf": csrf, "motivo": "  "},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/loja/vendas/lista?erro=motivo"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_lista_do_shell_oferece_registrar_venda(client, monkeypatch):
    _enable_shell(monkeypatch)
    login(client, papel="vendedor", email="vendedor@loja.test")

    pagina = client.get("/app/loja/vendas/lista")

    assert "/app/vendas/nova?origem=loja" in pagina.text
