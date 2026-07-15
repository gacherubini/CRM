import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal

from conftest import login

from app.db import SessionLocal
from app.financeiro_calc import _data
from app.models import Meta, Venda, VendaCustoDireto


def test_data_financeira_converte_utc_para_fuso_do_portal():
    virada_utc = datetime(2026, 7, 15, 1, 30, tzinfo=timezone.utc)
    assert _data(virada_utc) == date(2026, 7, 14)
    # SQLite remove o tzinfo na leitura; o valor ingênuo continua representando UTC.
    assert _data(virada_utc.replace(tzinfo=None)) == date(2026, 7, 14)


def criar_venda_confirmada(preco, custo=None, comissao=None, loja_slug="loja-teste", vendedor_email="dono@loja.test"):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email=vendedor_email,
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
    from app.main import ultimo_dia_mes
    from datetime import date

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


def totais_csv(texto: str) -> dict:
    linhas = list(csv.reader(io.StringIO(texto)))
    return {linha[0]: linha[1] for linha in linhas if len(linha) >= 2}


# --- (a) autorização: só dono/gerente ---------------------------------------

def test_vendedor_e_redirecionado_da_pagina_de_relatorios(client):
    login(client, papel="vendedor")
    resposta = client.get("/app/relatorios", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"


def test_vendedor_e_redirecionado_dos_csvs(client):
    login(client, papel="vendedor")
    for caminho in ("/app/relatorios/vendas.csv", "/app/relatorios/metas.csv", "/app/relatorios/funil.csv"):
        resposta = client.get(caminho, follow_redirects=False)
        assert resposta.status_code == 303
        assert resposta.headers["location"] == "/app"


def test_sem_sessao_e_redirecionado_ao_login(client):
    resposta = client.get("/app/relatorios", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_gerente_acessa_pagina_de_relatorios(client):
    login(client, papel="gerente", email="gerente@loja.test")
    resposta = client.get("/app/relatorios")
    assert resposta.status_code == 200
    assert "Relatórios" in resposta.text
    assert "vendas.csv" in resposta.text
    assert "metas.csv" in resposta.text
    assert "funil.csv" in resposta.text


# --- (b) CSVs com cabeçalhos e linhas corretos -------------------------------

def test_csv_vendas_tem_headers_corretos_e_linhas(client):
    criar_venda_confirmada("50000", custo="40000")
    criar_venda_confirmada("30000", custo="20000", comissao="500")
    login(client)
    resposta = client.get("/app/relatorios/vendas.csv")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert resposta.headers["content-disposition"].startswith("attachment; filename=")
    assert "vendas" in resposta.headers["content-disposition"]

    linhas = list(csv.reader(io.StringIO(resposta.text)))
    assert linhas[0] == [
        "id", "data", "vendedor_email", "descricao", "veiculo_ref",
        "preco_venda", "custo_veiculo", "custos_diretos", "lucro_bruto",
    ]
    linhas_dados = [linha for linha in linhas[1:] if linha and linha[0] not in
                    {"quantidade_vendas", "faturamento_total", "lucro_bruto_total", "lucro_completo"}]
    assert len(linhas_dados) == 2


def test_csv_metas_tem_headers_e_linha_da_meta(client):
    criar_venda_confirmada("50000", custo="40000")
    criar_venda_confirmada("30000", custo="20000")
    criar_meta(tipo="quantidade", alvo="4")
    login(client)
    resposta = client.get("/app/relatorios/metas.csv")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    linhas = list(csv.reader(io.StringIO(resposta.text)))
    assert linhas[0] == ["tipo", "alvo", "realizado", "percentual", "indisponivel"]
    assert linhas[1] == ["quantidade", "4.00", "2.00", "50.0", "nao"]


def test_csv_funil_tem_headers_e_linha_de_resumo(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/relatorios/funil.csv")
    assert resposta.status_code == 200
    linhas = list(csv.reader(io.StringIO(resposta.text)))
    assert linhas[0] == [
        "periodo_inicio", "periodo_fim", "vendedor_filtro", "origem_filtro",
        "disponivel", "leads_elegiveis", "atendidos", "vendas_vinculadas", "erro",
    ]
    assert linhas[1][4] == "sim"  # disponivel


def test_csv_funil_indisponivel_quando_chatbot_fora_do_ar(client, chatbot_fake):
    chatbot_fake.indisponivel = True
    login(client)
    resposta = client.get("/app/relatorios/funil.csv")
    assert resposta.status_code == 200
    linhas = list(csv.reader(io.StringIO(resposta.text)))
    assert linhas[1][4] == "nao"
    assert "Não foi possível acessar os leads agora" in linhas[1][8]


# --- (c) reconciliação: vendas.csv bate com /app/financeiro ------------------

def test_reconciliacao_vendas_csv_com_financeiro(client):
    criar_venda_confirmada("50000", custo="40000")
    criar_venda_confirmada("30000", custo="20000", comissao="500")
    criar_venda_confirmada("10000", loja_slug="outra-loja")  # não deve contar
    login(client)

    financeiro = client.get("/app/financeiro")
    assert financeiro.status_code == 200
    assert "80.000,00" in financeiro.text
    assert "19.500,00" in financeiro.text

    csv_resposta = client.get("/app/relatorios/vendas.csv")
    assert csv_resposta.status_code == 200
    totais = totais_csv(csv_resposta.text)
    assert totais["quantidade_vendas"] == "2"
    assert totais["faturamento_total"] == "80000.00"
    assert totais["lucro_bruto_total"] == "19500.00"
    assert totais["lucro_completo"] == "sim"


def test_reconciliacao_com_lucro_incompleto(client):
    criar_venda_confirmada("50000")  # sem custo => lucro incompleto
    criar_venda_confirmada("30000", custo="20000")
    login(client)

    financeiro = client.get("/app/financeiro")
    assert "Incompleto" in financeiro.text
    assert "Subtotal conhecido: R$ 10.000,00" in financeiro.text

    csv_resposta = client.get("/app/relatorios/vendas.csv")
    totais = totais_csv(csv_resposta.text)
    assert totais["quantidade_vendas"] == "2"
    assert totais["faturamento_total"] == "80000.00"
    assert totais["lucro_bruto_total"] == "10000.00"
    assert totais["lucro_completo"] == "nao"


def test_reconciliacao_respeita_filtro_de_periodo(client):
    from datetime import date, timedelta

    db = SessionLocal()
    venda_fora = Venda(
        loja_slug="loja-teste",
        vendedor_email="dono@loja.test",
        descricao="Venda antiga",
        preco_venda=Decimal("99999"),
        custo_veiculo=Decimal("1"),
        status="confirmada",
    )
    db.add(venda_fora)
    db.commit()
    venda_fora.criada_em = date.today() - timedelta(days=90)
    db.commit()
    db.close()

    criar_venda_confirmada("50000", custo="40000")
    login(client)

    inicio = date.today().replace(day=1).isoformat()
    fim = date.today().isoformat()
    financeiro = client.get("/app/financeiro", params={"inicio": inicio, "fim": fim})
    csv_resposta = client.get("/app/relatorios/vendas.csv", params={"inicio": inicio, "fim": fim})
    totais = totais_csv(csv_resposta.text)
    assert totais["quantidade_vendas"] == "1"
    assert totais["faturamento_total"] == "50000.00"
    assert "50.000,00" in financeiro.text
    assert "99.999,00" not in financeiro.text
