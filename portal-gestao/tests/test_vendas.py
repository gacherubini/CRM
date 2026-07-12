from decimal import Decimal

from conftest import csrf_da_resposta, login

from app.db import SessionLocal
from app.main import lucro_bruto_venda
from app.models import Venda, VendaCustoDireto


def criar_venda(loja_slug="loja-teste", status="registrada", vendedor_email="dono@loja.test", custo=None):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email=vendedor_email,
        descricao="Honda Civic 2022",
        preco_venda=Decimal("100000.00"),
        custo_veiculo=Decimal(custo) if custo is not None else None,
        status=status,
    )
    db.add(venda)
    db.commit()
    venda_id = venda.id
    db.close()
    return venda_id


def csrf_das_vendas(client):
    return csrf_da_resposta(client.get("/app/vendas"))


def test_dono_registra_venda(client):
    login(client)
    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={"csrf": csrf_da_resposta(pagina), "descricao": "Corolla 2023", "preco_venda": "120000.50", "custo_veiculo": "100000"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=registrada"
    db = SessionLocal()
    venda = db.query(Venda).first()
    assert venda.descricao == "Corolla 2023"
    assert venda.preco_venda == Decimal("120000.50")
    assert venda.custo_veiculo == Decimal("100000.00")
    assert venda.status == "registrada"
    db.close()


def test_vendedor_registra_sem_custo(client):
    login(client, papel="vendedor")
    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={"csrf": csrf_da_resposta(pagina), "descricao": "MT-03", "preco_venda": "31900", "custo_veiculo": "25000"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    db = SessionLocal()
    venda = db.query(Venda).first()
    assert venda.status == "registrada"
    assert venda.custo_veiculo is None
    db.close()


def test_vendedor_nao_confirma(client):
    venda_id = criar_venda()
    login(client, papel="vendedor")
    csrf = csrf_das_vendas(client)
    resposta = client.post(f"/app/vendas/{venda_id}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_dono_confirma_venda(client):
    venda_id = criar_venda()
    login(client)
    csrf = csrf_das_vendas(client)
    resposta = client.post(f"/app/vendas/{venda_id}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=confirmada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "confirmada"
    assert venda.confirmada_por == "dono@loja.test"
    assert venda.confirmada_em is not None
    db.close()


def test_cancelar_exige_motivo(client):
    venda_id = criar_venda()
    login(client)
    csrf = csrf_das_vendas(client)
    sem_motivo = client.post(f"/app/vendas/{venda_id}/cancelar", data={"csrf": csrf}, follow_redirects=False)
    assert sem_motivo.headers["location"] == "/app/vendas?erro=motivo"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()
    com_motivo = client.post(f"/app/vendas/{venda_id}/cancelar", data={"csrf": csrf, "motivo": "desistência"}, follow_redirects=False)
    assert com_motivo.headers["location"] == "/app/vendas?ok=cancelada"
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda.status == "cancelada"
    assert venda.motivo_cancelamento == "desistência"
    db.close()


def test_nao_cruza_loja(client):
    venda_id = criar_venda(loja_slug="outra-loja")
    login(client)
    csrf = csrf_das_vendas(client)
    resposta = client.post(f"/app/vendas/{venda_id}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert resposta.headers["location"] == "/app/vendas?erro=acao"
    db = SessionLocal()
    assert db.get(Venda, venda_id).status == "registrada"
    db.close()


def test_venda_confirmada_nao_pode_ser_apagada(client):
    venda_id = criar_venda(status="confirmada")
    login(client)
    resposta = client.delete(f"/app/vendas/{venda_id}", follow_redirects=False)
    assert resposta.status_code in (404, 405)
    db = SessionLocal()
    venda = db.get(Venda, venda_id)
    assert venda is not None
    assert venda.status == "confirmada"
    db.close()


def test_lucro_bruto_em_decimal_com_arredondamento():
    venda = Venda(descricao="x", preco_venda=Decimal("100000.00"), custo_veiculo=Decimal("80000.00"))
    venda.custos_diretos.append(VendaCustoDireto(categoria="documentacao", valor=Decimal("1500.00")))
    venda.custos_diretos.append(VendaCustoDireto(categoria="comissao", valor=Decimal("2000.50")))
    lucro = lucro_bruto_venda(venda)
    assert lucro == Decimal("16499.50")
    assert str(lucro) == "16499.50"


def test_lucro_bruto_indisponivel_sem_custo_do_veiculo():
    venda = Venda(descricao="x", preco_venda=Decimal("100000.00"), custo_veiculo=None)
    assert lucro_bruto_venda(venda) is None
