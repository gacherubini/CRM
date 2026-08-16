"""Editar e apagar venda no shell Revy Loja (leva de 2026-08-16).

Duas coisas diferentes que o produto tratava como uma só:

- **cancelar** (já existia) é negócio desfeito — fato comercial, fica na lista;
- **excluir** (novo) é registro que nunca deveria ter existido — some da tela,
  permanece no banco com autoria e data.

Editar venda confirmada mexe só em valores: o vínculo com lead e veículo virou
snapshot de atribuição e baixa de estoque na confirmação, e reescrevê-lo
falsificaria a origem de uma venda que o Control já contabilizou.
"""
from __future__ import annotations

from decimal import Decimal

from conftest import csrf_da_resposta, login

from app.config import settings
from app.db import SessionLocal
from app.models import RevyTrafegoEventOutbox, Venda, VendaCustoDireto, agora


def _enable_shell(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)


def _criar_venda(
    *,
    status="confirmada",
    vendedor_email="vendedor@loja.test",
    loja_slug="loja-teste",
    preco="100000.00",
    custo="80000.00",
    descricao="Honda Civic 2022",
):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email=vendedor_email,
        descricao=descricao,
        preco_venda=Decimal(preco),
        custo_veiculo=Decimal(custo) if custo is not None else None,
        status=status,
        confirmada_em=agora() if status == "confirmada" else None,
    )
    db.add(venda)
    db.commit()
    venda_id = venda.id
    db.close()
    return venda_id


def _venda(venda_id):
    db = SessionLocal()
    try:
        return db.get(Venda, venda_id)
    finally:
        db.close()


def _csrf(client):
    return csrf_da_resposta(client.get("/app/loja/vendas/lista"))


# --- Excluir -----------------------------------------------------------------


def test_dono_exclui_venda_e_ela_sai_da_lista(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(descricao="Moto lancada errado")
    login(client, papel="dono", email="dono@loja.test")

    r = client.post(
        f"/app/loja/vendas/{venda_id}/excluir",
        data={"csrf": _csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    venda = _venda(venda_id)
    assert venda.status == "excluida"
    assert venda.excluida_por == "dono@loja.test"
    assert venda.excluida_em is not None

    lista = client.get("/app/loja/vendas/lista")
    assert "Moto lancada errado" not in lista.text


def test_excluir_e_diferente_de_cancelar(client, monkeypatch):
    """Cancelada continua visível: é fato comercial, não erro de digitação."""
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(status="registrada", descricao="Cliente desistiu")
    login(client, papel="dono", email="dono@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/cancelar",
        data={"csrf": _csrf(client), "motivo": "cliente desistiu"},
        follow_redirects=False,
    )
    assert _venda(venda_id).status == "cancelada"
    assert "Cliente desistiu" in client.get("/app/loja/vendas/lista").text


def test_vendedor_nao_exclui_venda(client, monkeypatch):
    """Mexer em número que já foi ao Control é poder de dono/gerente."""
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/excluir",
        data={"csrf": _csrf(client)},
        follow_redirects=False,
    )
    assert _venda(venda_id).status == "confirmada"


def test_venda_de_outra_loja_nao_e_excluivel(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(loja_slug="outra-loja")
    login(client, papel="dono", email="dono@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/excluir",
        data={"csrf": _csrf(client)},
        follow_redirects=False,
    )
    assert _venda(venda_id).status == "confirmada"


def test_exclusao_enfileira_evento_para_o_control(client, monkeypatch):
    _enable_shell(monkeypatch)
    object.__setattr__(settings, "revy_trafego_venda_events_enabled", True)
    venda_id = _criar_venda()
    login(client, papel="dono", email="dono@loja.test")
    try:
        client.post(
            f"/app/loja/vendas/{venda_id}/excluir",
            data={"csrf": _csrf(client)},
            follow_redirects=False,
        )
    finally:
        object.__setattr__(settings, "revy_trafego_venda_events_enabled", False)

    db = SessionLocal()
    try:
        eventos = (
            db.query(RevyTrafegoEventOutbox)
            .filter(RevyTrafegoEventOutbox.venda_id == venda_id)
            .all()
        )
        assert [e.event_type for e in eventos] == ["venda_atualizada"]
    finally:
        db.close()


# --- Editar ------------------------------------------------------------------


def test_dono_edita_valores_de_venda_confirmada(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(preco="100000.00", custo="80000.00")
    login(client, papel="dono", email="dono@loja.test")

    r = client.post(
        f"/app/loja/vendas/{venda_id}/editar",
        data={
            "csrf": _csrf(client),
            "preco_venda": "97000",
            "custo_veiculo": "81500",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    venda = _venda(venda_id)
    assert venda.preco_venda == Decimal("97000.00")
    assert venda.custo_veiculo == Decimal("81500.00")
    assert venda.status == "confirmada"


def test_edicao_de_venda_confirmada_nao_mexe_no_vinculo(client, monkeypatch):
    """Lead e veículo viraram snapshot de atribuição + baixa de estoque."""
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    venda.lead_ref = "lead-original"
    venda.veiculo_ref = "veiculo-original"
    db.commit()
    db.close()

    login(client, papel="dono", email="dono@loja.test")
    client.post(
        f"/app/loja/vendas/{venda_id}/editar",
        data={
            "csrf": _csrf(client),
            "preco_venda": "97000",
            "lead_ref": "lead-trocado",
            "veiculo_ref": "veiculo-trocado",
        },
        follow_redirects=False,
    )

    venda = _venda(venda_id)
    assert venda.preco_venda == Decimal("97000.00")
    assert venda.lead_ref == "lead-original"
    assert venda.veiculo_ref == "veiculo-original"


def test_venda_registrada_aceita_edicao_do_vinculo(client, monkeypatch):
    """Nada saiu da Loja ainda: pode corrigir tudo."""
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(status="registrada")
    login(client, papel="dono", email="dono@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/editar",
        data={
            "csrf": _csrf(client),
            "descricao": "Honda Civic 2023",
            "preco_venda": "105000",
            "lead_ref": "lead-novo",
        },
        follow_redirects=False,
    )

    venda = _venda(venda_id)
    assert venda.descricao == "Honda Civic 2023"
    assert venda.preco_venda == Decimal("105000.00")
    assert venda.lead_ref == "lead-novo"


def test_venda_cancelada_nao_e_editavel(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(status="cancelada", preco="100000.00")
    login(client, papel="dono", email="dono@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/editar",
        data={"csrf": _csrf(client), "preco_venda": "1"},
        follow_redirects=False,
    )
    assert _venda(venda_id).preco_venda == Decimal("100000.00")


def test_vendedor_nao_edita_venda(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda(preco="100000.00")
    login(client, papel="vendedor", email="vendedor@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/editar",
        data={"csrf": _csrf(client), "preco_venda": "1"},
        follow_redirects=False,
    )
    assert _venda(venda_id).preco_venda == Decimal("100000.00")


def test_edicao_enfileira_evento_para_o_control(client, monkeypatch):
    _enable_shell(monkeypatch)
    object.__setattr__(settings, "revy_trafego_venda_events_enabled", True)
    venda_id = _criar_venda()
    login(client, papel="dono", email="dono@loja.test")
    try:
        client.post(
            f"/app/loja/vendas/{venda_id}/editar",
            data={"csrf": _csrf(client), "preco_venda": "97000"},
            follow_redirects=False,
        )
    finally:
        object.__setattr__(settings, "revy_trafego_venda_events_enabled", False)

    db = SessionLocal()
    try:
        eventos = (
            db.query(RevyTrafegoEventOutbox)
            .filter(RevyTrafegoEventOutbox.venda_id == venda_id)
            .all()
        )
        assert [e.event_type for e in eventos] == ["venda_atualizada"]
    finally:
        db.close()


# --- Custos diretos: o que faltava para a margem fechar ----------------------


def test_dono_lanca_custo_direto_depois_da_venda(client, monkeypatch):
    """Antes só dava para lançar um custo, e só no formulário de registro."""
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    login(client, papel="dono", email="dono@loja.test")

    for categoria, valor in (("frete", "350"), ("documentacao", "1200")):
        r = client.post(
            f"/app/loja/vendas/{venda_id}/custos",
            data={"csrf": _csrf(client), "categoria": categoria, "valor": valor},
            follow_redirects=False,
        )
        assert r.status_code == 303

    db = SessionLocal()
    try:
        custos = (
            db.query(VendaCustoDireto)
            .filter(VendaCustoDireto.venda_id == venda_id)
            .all()
        )
        assert sorted((c.categoria, str(c.valor)) for c in custos) == [
            ("documentacao", "1200.00"),
            ("frete", "350.00"),
        ]
    finally:
        db.close()


def test_vendedor_nao_lanca_custo_direto(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    login(client, papel="vendedor", email="vendedor@loja.test")

    client.post(
        f"/app/loja/vendas/{venda_id}/custos",
        data={"csrf": _csrf(client), "categoria": "frete", "valor": "350"},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        assert db.query(VendaCustoDireto).count() == 0
    finally:
        db.close()


def test_dono_remove_custo_direto(client, monkeypatch):
    _enable_shell(monkeypatch)
    venda_id = _criar_venda()
    db = SessionLocal()
    custo = VendaCustoDireto(venda_id=venda_id, categoria="frete", valor=Decimal("350"))
    db.add(custo)
    db.commit()
    custo_id = custo.id
    db.close()

    login(client, papel="dono", email="dono@loja.test")
    client.post(
        f"/app/loja/vendas/{venda_id}/custos/{custo_id}/remover",
        data={"csrf": _csrf(client)},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        assert db.query(VendaCustoDireto).count() == 0
    finally:
        db.close()
