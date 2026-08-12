from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.clients.chatbot import ChatbotIndisponivel
from app.clients.estoque import EstoqueIndisponivel
from app.loja.copiloto.resumo import montar_resumo_hoje
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Venda

AGORA = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def __init__(self, veiculos=None, indisponivel=False):
        self.veiculos = veiculos or []
        self.indisponivel = indisponivel

    def obter_loja(self):
        if self.indisponivel:
            raise EstoqueIndisponivel("fora")
        return {"slug": "loja-teste"}

    def listar(self, **filtros):
        if self.indisponivel:
            raise EstoqueIndisponivel("fora")
        return list(self.veiculos)


class ChatbotStub:
    def __init__(self, indisponivel=False):
        self.indisponivel = indisponivel

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("fora")
        return []

    def listar_leads(self, etapa=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("fora")
        return []


def _parado(dias=90):
    return {
        "id": "v1",
        "marca": "Honda",
        "modelo": "CB 500F",
        "preco": 25000.0,
        "status": "disponivel",
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        "tem_foto": True,
    }


def _venda(db, preco=30000):
    db.add(
        Venda(
            loja_slug="loja-teste",
            vendedor_email="ana@loja.test",
            descricao="Honda CB 500F 2020",
            preco_venda=Decimal(str(preco)),
            status="confirmada",
            criada_em=AGORA - timedelta(days=2),
        )
    )
    db.commit()


def test_resumo_traz_os_cinco_blocos(db):
    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub([_parado()]), chatbot=ChatbotStub(), agora=AGORA
    )
    assert r.vendas.qtd_vendas == 1
    assert r.ranking.status == "ok"
    assert r.origem_ultima.status == "ok"
    assert r.parado.total == 1
    assert r.leads is not None
    assert r.janela.rotulo == "agosto/2026"


def test_estoque_fora_nao_derruba_vendas(db):
    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub(indisponivel=True), chatbot=ChatbotStub(),
        agora=AGORA,
    )
    assert r.parado.status == "indisponivel"
    assert r.vendas.status == "ok"
    assert r.vendas.qtd_vendas == 1


def test_chip_de_estoque_parado_usa_numero_real(db):
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub([_parado()]), chatbot=ChatbotStub(), agora=AGORA
    )
    textos = [chip.texto for chip in r.chips]
    assert any("1 " in t and "parad" in t.lower() for t in textos)


def test_chip_de_origem_aparece_quando_ha_venda(db):
    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    perguntas = [chip.pergunta for chip in r.chips]
    assert any("última venda" in p.lower() for p in perguntas)


def test_sem_dado_nenhum_ainda_devolve_chips_base(db):
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    assert len(r.chips) >= 1


def test_to_dict_e_serializavel(db):
    import json

    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub([_parado()]), chatbot=ChatbotStub(), agora=AGORA
    )
    assert json.dumps(r.to_dict())
