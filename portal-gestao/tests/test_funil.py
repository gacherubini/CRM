from decimal import Decimal

from conftest import criar_usuario, login

from app.db import SessionLocal
from app.main import identidade_telefone
from app.models import AtendimentoAtribuicao, Venda


def criar_venda_vinculada(lead_ref, vendedor_email="dono@loja.test", loja_slug="loja-teste"):
    db = SessionLocal()
    db.add(
        Venda(
            loja_slug=loja_slug,
            lead_ref=lead_ref,
            vendedor_email=vendedor_email,
            descricao="Venda vinculada",
            preco_venda=Decimal("50000"),
            custo_veiculo=Decimal("40000"),
            status="confirmada",
        )
    )
    db.commit()
    db.close()


def criar_atribuicao(telefone, vendedor_email="dono@loja.test", loja_slug="loja-teste"):
    db = SessionLocal()
    db.add(
        AtendimentoAtribuicao(
            loja_slug=loja_slug,
            telefone_hmac=identidade_telefone(telefone),
            vendedor_email=vendedor_email,
            ativa=True,
        )
    )
    db.commit()
    db.close()


def test_funil_reconcilia_leads_handoffs_e_venda_vinculada(client, chatbot_fake):
    criar_atribuicao("5511987654321")
    criar_venda_vinculada("l1")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "Leads elegíveis" in resposta.text
    assert "<strong>2</strong><small>leads criados" in resposta.text
    assert "<strong>1</strong><small>leads elegíveis com handoff" in resposta.text
    assert "<strong>1</strong><small>vendas confirmadas" in resposta.text
    assert "não prova causalidade" in resposta.text


def test_funil_filtra_origem_declarada_sem_inferir_ausentes(client, chatbot_fake):
    criar_venda_vinculada("l1")
    login(client)
    resposta = client.get("/app/financeiro", params={"origem": "catalogo"})
    assert resposta.status_code == 200
    assert "<strong>1</strong><small>leads criados" in resposta.text
    assert "origem declarada" in resposta.text


def test_funil_filtra_vendedor_por_handoff_confiavel(client, chatbot_fake):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    criar_atribuicao("5511987654321", vendedor_email="vendedor@loja.test")
    criar_venda_vinculada("l1", vendedor_email="vendedor@loja.test")
    login(client)
    resposta = client.get("/app/financeiro", params={"vendedor": "vendedor@loja.test"})
    assert resposta.status_code == 200
    assert "<strong>1</strong><small>leads criados" in resposta.text
    assert "<strong>1</strong><small>leads elegíveis com handoff" in resposta.text
    assert "<strong>1</strong><small>vendas confirmadas" in resposta.text


def test_funil_indisponivel_sem_chatbot_mantem_financeiro_local(client, chatbot_fake):
    chatbot_fake.indisponivel = True
    criar_venda_vinculada("l1")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "R$ 50.000,00" in resposta.text
    assert "Funil indisponível" in resposta.text
    assert "Não foi possível acessar os leads agora" in resposta.text


def test_funil_indisponivel_quando_lead_nao_tem_data_confiavel(client, chatbot_fake):
    chatbot_fake.leads[0].pop("criada_em")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "Funil indisponível" in resposta.text
    assert "sem data de criação confiável" in resposta.text


def test_funil_ignora_venda_e_handoff_de_outra_loja(client, chatbot_fake):
    criar_atribuicao("5511987654321", loja_slug="outra-loja")
    criar_venda_vinculada("l1", loja_slug="outra-loja")
    login(client)
    resposta = client.get("/app/financeiro")
    assert resposta.status_code == 200
    assert "<strong>0</strong><small>leads elegíveis com handoff" in resposta.text
    assert "<strong>0</strong><small>vendas confirmadas" in resposta.text
