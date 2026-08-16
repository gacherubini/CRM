"""CRUD de despesas fixas da loja (módulo Financeiro, 2026-08-16).

O comportamento que mais importa aqui é o que NÃO acontece: cadastrar não
retroage sobre meses fechados, ajustar não altera o cadastro recorrente e
encerrar não apaga a linha.
"""
from __future__ import annotations

from decimal import Decimal

from conftest import csrf_da_resposta, login

from app.config import settings
from app.db import SessionLocal
from app.models import DespesaFixaAjuste, DespesaFixaLoja


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_FINANCEIRO_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)


def _csrf(client, mes="2026-08"):
    return csrf_da_resposta(client.get(f"/app/loja/financeiro/despesas?mes={mes}"))


def _despesas(loja_slug="loja-teste"):
    db = SessionLocal()
    try:
        return (
            db.query(DespesaFixaLoja)
            .filter(DespesaFixaLoja.loja_slug == loja_slug)
            .all()
        )
    finally:
        db.close()


def _cadastrar(client, *, mes="2026-08", categoria="aluguel", descricao="Aluguel", valor="6000"):
    return client.post(
        "/app/loja/financeiro/despesas",
        data={
            "csrf": _csrf(client, mes),
            "mes": mes,
            "categoria": categoria,
            "descricao": descricao,
            "valor": valor,
        },
        follow_redirects=False,
    )


def test_dono_cadastra_despesa_fixa(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")

    r = _cadastrar(client)
    assert r.status_code == 303

    despesas = _despesas()
    assert len(despesas) == 1
    assert despesas[0].valor_mensal == Decimal("6000.00")
    assert despesas[0].categoria == "aluguel"
    assert despesas[0].fim_competencia is None


def test_cadastro_vale_a_partir_do_mes_editado_e_nao_retroage(client, monkeypatch):
    """Mês já conferido pelo lojista não pode mudar sozinho."""
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")

    _cadastrar(client, mes="2026-08")
    assert _despesas()[0].inicio_competencia == "2026-08"

    julho = client.get("/app/loja/financeiro/dados?mes=2026-07")
    assert julho.json()["despesa_fixa"] == "0.00"


def test_vendedor_nao_cadastra_despesa(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="vendedor@loja.test")
    _cadastrar(client)
    assert _despesas() == []


def test_valor_invalido_nao_cadastra(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    _cadastrar(client, valor="0")
    _cadastrar(client, valor="abc")
    _cadastrar(client, categoria="inventada")
    assert _despesas() == []


def test_ajuste_muda_so_o_mes_e_preserva_o_cadastro(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    _cadastrar(client, mes="2026-08", categoria="energia", descricao="Energia", valor="1200")
    despesa_id = _despesas()[0].id

    r = client.post(
        f"/app/loja/financeiro/despesas/{despesa_id}/ajuste",
        data={"csrf": _csrf(client), "mes": "2026-08", "valor": "1850"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    assert _despesas()[0].valor_mensal == Decimal("1200.00")
    db = SessionLocal()
    try:
        ajuste = db.query(DespesaFixaAjuste).one()
        assert ajuste.competencia == "2026-08"
        assert ajuste.valor == Decimal("1850.00")
    finally:
        db.close()

    assert client.get("/app/loja/financeiro/dados?mes=2026-08").json()["despesa_fixa"] == "1850.00"
    assert client.get("/app/loja/financeiro/dados?mes=2026-09").json()["despesa_fixa"] == "1200.00"


def test_ajuste_do_mesmo_mes_sobrescreve_em_vez_de_duplicar(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    _cadastrar(client, mes="2026-08", valor="1200")
    despesa_id = _despesas()[0].id

    for valor in ("1850", "1900"):
        client.post(
            f"/app/loja/financeiro/despesas/{despesa_id}/ajuste",
            data={"csrf": _csrf(client), "mes": "2026-08", "valor": valor},
            follow_redirects=False,
        )

    db = SessionLocal()
    try:
        assert db.query(DespesaFixaAjuste).count() == 1
        assert db.query(DespesaFixaAjuste).one().valor == Decimal("1900.00")
    finally:
        db.close()


def test_encerrar_nao_apaga_e_preserva_os_meses_anteriores(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    _cadastrar(client, mes="2026-08", valor="6000")
    despesa_id = _despesas()[0].id

    r = client.post(
        f"/app/loja/financeiro/despesas/{despesa_id}/encerrar",
        data={"csrf": _csrf(client), "mes": "2026-09"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    despesas = _despesas()
    assert len(despesas) == 1, "encerrar apaga histórico se remover a linha"
    assert despesas[0].fim_competencia == "2026-09"

    assert client.get("/app/loja/financeiro/dados?mes=2026-08").json()["despesa_fixa"] == "6000.00"
    assert client.get("/app/loja/financeiro/dados?mes=2026-10").json()["despesa_fixa"] == "0.00"


def test_despesa_de_outra_loja_nao_e_ajustavel(client, monkeypatch):
    _ligar(monkeypatch)
    db = SessionLocal()
    alheia = DespesaFixaLoja(
        loja_slug="outra-loja",
        categoria="aluguel",
        descricao="Aluguel alheio",
        valor_mensal=Decimal("6000"),
        inicio_competencia="2026-01",
    )
    db.add(alheia)
    db.commit()
    alheia_id = alheia.id
    db.close()

    login(client, papel="dono", email="dono@loja.test")
    client.post(
        f"/app/loja/financeiro/despesas/{alheia_id}/ajuste",
        data={"csrf": _csrf(client), "mes": "2026-08", "valor": "1"},
        follow_redirects=False,
    )
    client.post(
        f"/app/loja/financeiro/despesas/{alheia_id}/encerrar",
        data={"csrf": _csrf(client), "mes": "2026-08"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        assert db.query(DespesaFixaAjuste).count() == 0
        assert db.get(DespesaFixaLoja, alheia_id).fim_competencia is None
    finally:
        db.close()


def test_csrf_invalido_nao_muta(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    client.post(
        "/app/loja/financeiro/despesas",
        data={
            "csrf": "invalido",
            "mes": "2026-08",
            "categoria": "aluguel",
            "descricao": "Aluguel",
            "valor": "6000",
        },
        follow_redirects=False,
    )
    assert _despesas() == []
