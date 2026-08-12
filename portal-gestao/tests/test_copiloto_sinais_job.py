from datetime import datetime, timedelta, timezone
from decimal import Decimal

from conftest import seed_loja_operacional

from app.copiloto_sinais_job import CopilotoSinaisWorker, avaliar_loja
from app.db import SessionLocal
from app.models import CopilotoSinal, Venda

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class EstoqueStub:
    def __init__(self, veiculos=None, slug="loja-teste"):
        self.veiculos = veiculos if veiculos is not None else []
        self.slug = slug

    def obter_loja(self):
        return {"slug": self.slug}

    def listar(self, **filtros):
        return list(self.veiculos)


class ChatbotStub:
    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        return []

    def listar_leads(self, etapa=None):
        return []


def _veiculo_parado(dias=90):
    return {
        "id": "v1",
        "marca": "Honda",
        "modelo": "CB 500F",
        "ano_modelo": 2020,
        "preco": 25000.0,
        "status": "disponivel",
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        "tem_foto": True,
    }


def test_avaliar_loja_gera_candidato_de_estoque_parado(db):
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_parado()]),
        chatbot=ChatbotStub(),
        agora=AGORA,
    )
    regras = {c.regra for c in candidatos}
    assert "estoque_parado" in regras


def test_avaliar_loja_gera_margem_incompleta(db):
    seed_loja_operacional(db)
    for i in range(4):
        db.add(
            Venda(
                loja_slug="loja-teste",
                vendedor_email="ana@loja.test",
                descricao="Moto",
                preco_venda=Decimal("20000"),
                custo_veiculo=Decimal("16000") if i == 0 else None,
                status="confirmada",
                criada_em=AGORA - timedelta(days=2),
            )
        )
    db.commit()
    candidatos = avaliar_loja(
        db, "loja-teste", estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    regras = {c.regra for c in candidatos}
    assert "margem_incompleta" in regras
    assert "atribuicao_baixa" in regras


def test_run_once_persiste_sinais_da_loja_ativa(db):
    seed_loja_operacional(db)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["lojas"] == 1
    assert db.query(CopilotoSinal).filter(CopilotoSinal.regra == "estoque_parado").count() == 1


def test_run_once_desligado_nao_toca_o_banco(db):
    seed_loja_operacional(db)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=False,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    assert worker.run_once()["ok"] is False
    assert db.query(CopilotoSinal).count() == 0


def test_loja_inativa_nao_e_avaliada(db):
    seed_loja_operacional(db, loja_slug="loja-teste", state="suspensa", version=2)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    assert worker.run_once()["lojas"] == 0
    assert db.query(CopilotoSinal).count() == 0


def test_falha_em_uma_loja_nao_derruba_o_ciclo(db):
    seed_loja_operacional(db, loja_slug="loja-teste")
    seed_loja_operacional(db, loja_slug="loja-2")
    db.commit()

    class EstoqueQuebrado(EstoqueStub):
        def listar(self, **filtros):
            raise RuntimeError("boom")

    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueQuebrado(slug="loja-teste"),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["erros"] >= 1
