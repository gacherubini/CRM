from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.clients.estoque import EstoqueIndisponivel
from app.loja.copiloto.consultas_estoque import (
    EscopoLojaDivergente,
    estoque_parado,
    garantir_escopo_loja,
)
from app.loja.copiloto.tipos import CopilotoContexto

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def __init__(self, veiculos, *, slug="loja-teste", indisponivel=False):
        self.veiculos = veiculos
        self.slug = slug
        self.indisponivel = indisponivel

    def obter_loja(self):
        if self.indisponivel:
            raise EstoqueIndisponivel("estoque fora")
        return {"slug": self.slug, "nome": "Loja Teste"}

    def listar(self, **filtros):
        if self.indisponivel:
            raise EstoqueIndisponivel("estoque fora")
        return list(self.veiculos)


def _veiculo(id_, dias, preco=25000.0, status="disponivel", **extra):
    return {
        "id": id_,
        "marca": "Honda",
        "modelo": "CB 500F",
        "ano_modelo": 2020,
        "placa": f"ABC{id_}",
        "preco": preco,
        "status": status,
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        **extra,
    }


def test_lista_so_o_que_passou_do_limiar(db):
    estoque = EstoqueStub([_veiculo("v1", 70), _veiculo("v2", 10)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "ok"
    assert [i.id for i in r.itens] == ["v1"]
    assert r.itens[0].dias_parado == 70
    assert r.total == 1


def test_soma_capital_preso(db):
    estoque = EstoqueStub(
        [_veiculo("v1", 70, preco=25000.0), _veiculo("v2", 90, preco=13400.0)]
    )
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.capital_preso == Decimal("38400.00")
    assert r.total == 2


def test_ordena_do_mais_parado_para_o_menos(db):
    estoque = EstoqueStub([_veiculo("v1", 70), _veiculo("v2", 120)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert [i.id for i in r.itens] == ["v2", "v1"]


def test_vendido_e_indisponivel_nao_contam(db):
    estoque = EstoqueStub(
        [
            _veiculo("v1", 200, status="vendido"),
            _veiculo("v2", 200, status="indisponivel"),
            _veiculo("v3", 200, status="reservado"),
        ]
    )
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert [i.id for i in r.itens] == ["v3"]


def test_veiculo_sem_data_nao_vira_zero_dias_e_baixa_a_cobertura(db):
    estoque = EstoqueStub([_veiculo("v1", 70), {"id": "v2", "status": "disponivel"}])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert [i.id for i in r.itens] == ["v1"]
    assert r.cobertura_data.to_dict() == {"com_dado": 1, "total": 2}
    assert r.status == "parcial"


def test_veiculo_sem_preco_nao_inventa_capital(db):
    estoque = EstoqueStub([_veiculo("v1", 70, preco=None)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.itens[0].preco is None
    assert r.capital_preso == Decimal("0.00")


def test_estoque_fora_do_ar_e_indisponivel_nao_zero(db):
    estoque = EstoqueStub([], indisponivel=True)
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "indisponivel"
    assert r.itens == ()
    assert r.total is None
    assert r.capital_preso is None


def test_nada_parado_e_vazio(db):
    estoque = EstoqueStub([_veiculo("v1", 5)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "vazio"
    assert r.total == 0


def test_resposta_carrega_a_ressalva_de_criado_em(db):
    estoque = EstoqueStub([_veiculo("v1", 70)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert "cadastro" in r.ressalva.lower()


def test_guarda_falha_fechado_quando_o_estoque_e_de_outra_loja(db):
    estoque = EstoqueStub([_veiculo("v1", 70)], slug="outra-loja")
    with pytest.raises(EscopoLojaDivergente):
        garantir_escopo_loja(estoque, "loja-teste")


def test_estoque_parado_nao_devolve_dado_de_outra_loja(db):
    estoque = EstoqueStub([_veiculo("v1", 70)], slug="outra-loja")
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "erro"
    assert r.itens == ()
