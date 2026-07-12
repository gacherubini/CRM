from datetime import date
from decimal import Decimal

from conftest import login

from app.db import SessionLocal
from app.main import ultimo_dia_mes
from app.models import Meta, Venda, VendaCustoDireto


def criar_venda_confirmada(preco, custo=None, comissao=None, loja_slug="loja-teste"):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email="dono@loja.test",
        descricao="Venda confirmada",
        preco_venda=Decimal(preco),
        custo_veiculo=Decimal(custo) if custo is not None else None,
        status="confirmada",
    )
    if comissao is not None:
        venda.custos_diretos.append(VendaCustoDireto(categoria="comissao", valor=Decimal(comissao)))
    db.add(venda)
    db.commit()
    db.close()


def criar_meta(tipo="quantidade", alvo="4", loja_slug="loja-teste"):
    hoje = date.today()
    db = SessionLocal()
    db.add(
        Meta(
            loja_slug=loja_slug,
            escopo="loja",
            tipo=tipo,
            periodo_inicio=hoje.replace(day=1),
            periodo_fim=ultimo_dia_mes(hoje),
            valor_alvo=Decimal(alvo),
        )
    )
    db.commit()
    db.close()


def test_dono_ve_totais_reais(client):
    criar_venda_confirmada("50000", custo="40000")
    criar_venda_confirmada("30000", custo="20000", comissao="500")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "80.000,00" in resposta.text
    assert "19.500,00" in resposta.text
    assert "lucro" in resposta.text.lower()


def test_vendedor_redirecionado(client):
    login(client, papel="vendedor")
    resposta = client.get("/app/financeiro", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"


def test_estado_vazio_sem_vendas(client):
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "Nenhuma venda confirmada no período." in resposta.text


def test_atingimento_da_meta(client):
    criar_venda_confirmada("50000", custo="40000")
    criar_venda_confirmada("30000", custo="20000")
    criar_meta(tipo="quantidade", alvo="4")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "50.0%" in resposta.text


def test_venda_de_outra_loja_nao_conta(client):
    criar_venda_confirmada("50000", custo="40000", loja_slug="outra-loja")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "Nenhuma venda confirmada no período." in resposta.text
