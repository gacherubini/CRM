from datetime import date
from decimal import Decimal

from conftest import csrf_da_resposta, login
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal
from app.main import identidade_telefone, ultimo_dia_mes
from app.models import AtendimentoAtribuicao, Meta, Venda


def criar_venda(vendedor_email, descricao, preco, status="confirmada", loja_slug="loja-teste"):
    db = SessionLocal()
    db.add(
        Venda(
            loja_slug=loja_slug,
            vendedor_email=vendedor_email,
            descricao=descricao,
            preco_venda=Decimal(preco),
            custo_veiculo=Decimal("1.00"),
            status=status,
        )
    )
    db.commit()
    db.close()


def criar_meta_individual(tipo, alvo, vendedor_email="dono@loja.test"):
    hoje = date.today()
    db = SessionLocal()
    db.add(
        Meta(
            loja_slug="loja-teste",
            escopo="vendedor",
            vendedor_email=vendedor_email,
            tipo=tipo,
            periodo_inicio=hoje.replace(day=1),
            periodo_fim=ultimo_dia_mes(hoje),
            valor_alvo=Decimal(alvo),
            ativa=True,
        )
    )
    db.commit()
    db.close()


def test_vendedor_ve_somente_vendas_proprias_sem_lucro(client):
    criar_venda("dono@loja.test", "Minha venda", "10000")
    criar_venda("outro@loja.test", "Venda de outro", "99000")
    login(client, papel="vendedor")
    resposta = client.get("/app/vendedor")
    assert resposta.status_code == 200
    assert "Minha venda" in resposta.text
    assert "R$ 10.000,00" in resposta.text
    assert "Venda de outro" not in resposta.text
    assert "R$ 99.000,00" not in resposta.text
    assert "Custo do veículo" not in resposta.text
    assert "Lucro bruto" not in resposta.text


def test_vendedor_ve_meta_individual_segura_mas_nao_meta_de_lucro(client):
    criar_venda("dono@loja.test", "Venda", "10000")
    criar_meta_individual("quantidade", "2")
    criar_meta_individual("lucro_bruto", "999999")
    login(client, papel="vendedor")
    resposta = client.get("/app/vendedor")
    assert resposta.status_code == 200
    assert "50.0%" in resposta.text
    assert "999.999,00" not in resposta.text


def test_dono_nao_acessa_dashboard_de_vendedor(client):
    login(client)
    resposta = client.get("/app/vendedor", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/financeiro"


def test_dashboard_vendedor_degrada_sem_chatbot(client, chatbot_fake):
    chatbot_fake.indisponivel = True
    criar_venda("dono@loja.test", "Venda local", "12000")
    login(client, papel="vendedor")
    resposta = client.get("/app/vendedor")
    assert resposta.status_code == 200
    assert "Venda local" in resposta.text
    assert "Chatbot desconectado" in resposta.text
    assert "atendimentos estão indisponíveis" in resposta.text


def test_handoff_bem_sucedido_registra_identidade_hmac_e_alimenta_painel(client, chatbot_fake):
    login(client, papel="vendedor")
    pagina = client.get("/app/conversas/5511987654321")
    resposta = client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "assumir"},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/app/conversas/5511987654321?ok=assumir"
    db = SessionLocal()
    atribuicao = db.query(AtendimentoAtribuicao).one()
    assert atribuicao.loja_slug == "loja-teste"
    assert atribuicao.vendedor_email == "dono@loja.test"
    assert atribuicao.telefone_hmac == identidade_telefone("5511987654321")
    assert "5511987654321" not in atribuicao.telefone_hmac
    db.close()
    painel = client.get("/app/vendedor")
    assert "Maria Silva" in painel.text
    assert "origem declarada: catalogo" in painel.text
    assert "campanha: seminovos-julho" in painel.text
    assert "•••• 4321" in painel.text


def test_devolver_encerra_atribuicao_local(client, chatbot_fake):
    login(client, papel="vendedor")
    pagina = client.get("/app/conversas/5511987654321")
    csrf = csrf_da_resposta(pagina)
    client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf, "acao": "assumir"},
        follow_redirects=False,
    )
    client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf, "acao": "devolver"},
        follow_redirects=False,
    )
    db = SessionLocal()
    atribuicao = db.query(AtendimentoAtribuicao).one()
    assert atribuicao.ativa is False
    assert atribuicao.encerrada_em is not None
    db.close()


def test_falha_no_registro_local_nao_desfaz_handoff_bem_sucedido(client, chatbot_fake, monkeypatch):
    def falha(*args, **kwargs):
        raise SQLAlchemyError("falha local")

    monkeypatch.setattr("app.main.registrar_handoff_local", falha)
    login(client, papel="vendedor")
    pagina = client.get("/app/conversas/5511987654321")
    resposta = client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "assumir"},
        follow_redirects=False,
    )
    assert chatbot_fake.handoffs == [("5511987654321", False)]
    assert resposta.headers["location"].endswith("?ok=assumir&registro=indisponivel")
    db = SessionLocal()
    assert db.query(AtendimentoAtribuicao).count() == 0
    db.close()


def test_atribuicao_de_outra_loja_nao_aparece(client):
    db = SessionLocal()
    db.add(
        AtendimentoAtribuicao(
            loja_slug="outra-loja",
            telefone_hmac=identidade_telefone("5511987654321"),
            vendedor_email="dono@loja.test",
            ativa=True,
        )
    )
    db.commit()
    db.close()
    login(client, papel="vendedor")
    resposta = client.get("/app/vendedor")
    assert "Maria Silva" not in resposta.text
    assert "Nenhum lead assumido identificado" in resposta.text
